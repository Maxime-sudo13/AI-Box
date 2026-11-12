"""Moteur d'exécution : proposition, autorisation, exécution, annulation.

Règles appliquées ici, quel que soit le client (interface, agent, script) :
- une action interdite par la règle du dirigeant est refusée et journalisée ;
- une action de niveau 2 ou 3 ne s'exécute qu'après validation d'un dirigeant (rôle
  « Dirigeant » ou administrateur), sauf règle « automatique » choisie pour le niveau 2 ;
- une action de niveau 3 exige en plus une confirmation explicite et la saisie récente du
  mot de passe ; elle n'est jamais automatique ;
- chaque étape est enregistrée dans l'action et dans le journal d'activité.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.deps import company_role
from app.models import Action, ActionPolicy, Company, User, UserSession

from .catalog import CATALOG, PayloadError, allowed_modes
from .executors import EXECUTORS, ExecutionError

CONFIRMATION_WORD = "CONFIRMER"


class ActionRefused(Exception):
    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return datetime.now(UTC)


def policy_mode(db: Session, company_id: uuid.UUID, action_type: str) -> str:
    policy = db.get(ActionPolicy, (company_id, action_type))
    mode = policy.mode if policy else CATALOG[action_type].default_mode
    # Garde-fou : même une règle corrompue ne peut rendre automatique un niveau 3.
    return mode if mode in allowed_modes(CATALOG[action_type].level) else "approval"


def can_approve(db: Session, user: User, company_id: uuid.UUID) -> bool:
    return user.is_admin or company_role(db, user, company_id) == "owner"


def _record(
    db: Session,
    request: Request | None,
    action: Action,
    event: str,
    user: User | None,
    outcome: str = "success",
    **details: Any,
) -> None:
    if request is None:
        return
    audit.record(
        db,
        request,
        f"action.{event}",
        actor=user,
        actor_label=action.proposed_by if user is None else None,
        outcome=outcome,
        company_id=action.company_id,
        target=action.title[:300],
        details={"action_id": str(action.id), "type": action.action_type, "level": action.risk_level, **details},
    )


def propose(
    db: Session,
    request: Request | None,
    company: Company,
    action_type: str,
    payload: dict[str, Any],
    *,
    title: str,
    proposed_by: str,
    user: User | None,
    trigger: dict[str, Any] | None = None,
) -> Action:
    if action_type not in CATALOG:
        raise ActionRefused("Type d'action inconnu.", 422)
    kind = CATALOG[action_type]
    try:
        clean = kind.validate(dict(payload))
    except PayloadError as exc:
        raise ActionRefused(str(exc), 422) from exc
    action = Action(
        company_id=company.id,
        action_type=action_type,
        risk_level=kind.level,
        title=title[:300],
        status="pending",
        proposed_by=proposed_by,
        proposed_by_user_id=user.id if user else None,
        trigger=trigger or {},
        payload=clean,
        reversible=kind.reversible,
    )
    db.add(action)
    db.flush()
    _record(db, request, action, "propose", user, origin=proposed_by)

    mode = policy_mode(db, company.id, action_type)
    if mode == "forbidden":
        action.status, action.decided_at = "rejected", now()
        action.authorization = {"mode": "forbidden", "decision": "refusée par vos autorisations"}
        action.error = "Ce type d'action est interdit par les autorisations de l'entreprise."
        _record(db, request, action, "blocked", user, outcome="denied")
    elif mode == "automatic":
        action.status, action.decided_at = "approved", now()
        action.authorization = {
            "mode": "automatic",
            "decision": "autorisée par une règle automatique",
            "at": now().isoformat(),
        }
        execute(db, request, company, action, user)
    return action


def approve(
    db: Session,
    request: Request | None,
    company: Company,
    action: Action,
    user: User,
    session: UserSession | None,
    *,
    overrides: dict[str, Any] | None = None,
    confirmation: str | None = None,
) -> Action:
    if action.status != "pending":
        raise ActionRefused("Cette action n'est plus en attente.", 409)
    if not can_approve(db, user, company.id):
        _record(db, request, action, "approve", user, outcome="denied", reason="role")
        raise ActionRefused("Seul le dirigeant de l'entreprise peut autoriser une action.")
    if policy_mode(db, company.id, action.action_type) == "forbidden":
        raise ActionRefused("Ce type d'action est interdit par les autorisations de l'entreprise.")
    kind = CATALOG[action.action_type]
    reauth = None
    if kind.level == 3:
        fresh = (
            session
            and session.reauth_at
            and session.reauth_at > now() - timedelta(minutes=get_settings().reauth_minutes)
        )
        if not fresh:
            _record(db, request, action, "approve", user, outcome="denied", reason="reauth")
            raise ActionRefused("Opération sensible : confirmez d'abord votre mot de passe.", 428)
        if (confirmation or "").strip().upper() != CONFIRMATION_WORD:
            raise ActionRefused(f"Opération sensible : tapez « {CONFIRMATION_WORD} » pour valider.", 422)
        reauth = session.reauth_at.isoformat()
    if overrides:
        edited = {
            **action.payload,
            **{k: v for k, v in overrides.items() if k in action.payload or k in ("to", "subject", "body")},
        }
        try:
            edited = kind.validate(edited)
        except PayloadError as exc:
            raise ActionRefused(str(exc), 422) from exc
        modified = sorted(k for k in edited if edited.get(k) != action.payload.get(k))
        action.payload = edited
    else:
        modified = []
    action.status, action.decided_at = "approved", now()
    action.authorization = {
        "mode": "approval",
        "decision": "validée",
        "by": user.email,
        "by_user_id": str(user.id),
        "at": now().isoformat(),
        "reauthenticated_at": reauth,
        "modified_fields": modified,
    }
    _record(db, request, action, "approve", user, modified=modified)
    execute(db, request, company, action, user)
    return action


def execute(db: Session, request: Request | None, company: Company, action: Action, user: User | None) -> None:
    run, _ = EXECUTORS[action.action_type]
    action.status = "executing"
    db.flush()
    try:
        with db.begin_nested():
            action.result = run(db, company, action)
        action.status, action.error = "done", None
    except (ExecutionError, OSError) as exc:
        action.status, action.error = "failed", str(exc)[:1000]
    action.executed_at = now()
    _record(
        db,
        request,
        action,
        "execute",
        user,
        outcome="success" if action.status == "done" else "failure",
        error=action.error,
    )


def reject(
    db: Session, request: Request | None, company: Company, action: Action, user: User, reason: str | None
) -> Action:
    if action.status != "pending":
        raise ActionRefused("Cette action n'est plus en attente.", 409)
    if not can_approve(db, user, company.id) and action.proposed_by_user_id != user.id:
        raise ActionRefused("Seul le dirigeant peut refuser une action proposée par un tiers.")
    action.status, action.decided_at = ("cancelled" if action.proposed_by_user_id == user.id else "rejected"), now()
    action.authorization = {
        "mode": "approval",
        "decision": "refusée",
        "by": user.email,
        "at": now().isoformat(),
        "reason": reason,
    }
    _record(db, request, action, "reject", user, reason=reason)
    return action


def undo(db: Session, request: Request | None, company: Company, action: Action, user: User) -> Action:
    _, revert = EXECUTORS[action.action_type]
    if action.status != "done" or not action.reversible or revert is None:
        raise ActionRefused("Cette action ne peut pas être annulée.", 409)
    if not can_approve(db, user, company.id):
        raise ActionRefused("Seul le dirigeant peut annuler une action.")
    with db.begin_nested():
        revert(db, company, action)
    action.status = "undone"
    action.result = {**action.result, "undone_by": user.email, "undone_at": now().isoformat()}
    _record(db, request, action, "undo", user)
    return action


def existing_for_trigger(db: Session, company_id: uuid.UUID, fingerprint: str) -> list[Action]:
    return list(
        db.scalars(
            select(Action)
            .where(Action.company_id == company_id, Action.trigger["alert"].astext == fingerprint)
            .order_by(Action.created_at.desc())
        )
    )
