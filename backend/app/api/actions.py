import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.actions import engine as actions
from app.actions.catalog import CATALOG, allowed_modes
from app.actions.drafts import drafts_for_alert
from app.config import today
from app.db import get_db
from app.deps import Auth, company_access, get_auth
from app.finance import anomalies, engine, treasury
from app.finance.data import load
from app.models import Action, ActionPolicy, OutboundEmail, Party, Task

router = APIRouter(tags=["actions"])

STATUS_LABELS = {
    "pending": "En attente de validation",
    "approved": "Autorisée",
    "executing": "En cours",
    "done": "Exécutée",
    "failed": "Échec",
    "rejected": "Refusée",
    "cancelled": "Annulée avant exécution",
    "undone": "Annulée après exécution",
}


def action_out(a: Action) -> dict[str, Any]:
    kind = CATALOG.get(a.action_type)
    result = {k: v for k, v in (a.result or {}).items() if k != "file"}
    return {
        "id": str(a.id),
        "action_type": a.action_type,
        "type_label": kind.label if kind else a.action_type,
        "risk_level": a.risk_level,
        "title": a.title,
        "status": a.status,
        "status_label": STATUS_LABELS[a.status],
        "proposed_by": a.proposed_by,
        "trigger": a.trigger,
        "payload": a.payload,
        "authorization": a.authorization,
        "result": result,
        "error": a.error,
        "reversible": a.reversible and a.status == "done",
        "has_file": bool((a.result or {}).get("file")),
        "created_at": a.created_at,
        "decided_at": a.decided_at,
        "executed_at": a.executed_at,
    }


def _get(db: Session, company_id: uuid.UUID, action_id: uuid.UUID) -> Action:
    action = db.scalar(select(Action).where(Action.id == action_id, Action.company_id == company_id))
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action introuvable.")
    return action


def _refused(exc: actions.ActionRefused) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("/companies/{company_id}/actions/catalog")
def catalog(company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)):
    company = company_access(db, request, auth.user, company_id, module="finance")
    return {
        "can_edit": actions.can_approve(db, auth.user, company.id),
        "items": [
            {
                "key": t.key,
                "label": t.label,
                "level": t.level,
                "description": t.description,
                "reversible": t.reversible,
                "mode": actions.policy_mode(db, company.id, t.key),
                "allowed_modes": list(allowed_modes(t.level)),
            }
            for t in CATALOG.values()
        ],
    }


class PolicyIn(BaseModel):
    action_type: str
    mode: Literal["forbidden", "approval", "automatic"]


@router.put("/companies/{company_id}/actions/policies")
def set_policy(
    company_id: uuid.UUID,
    body: PolicyIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    if not actions.can_approve(db, auth.user, company.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul le dirigeant peut modifier les autorisations.")
    kind = CATALOG.get(body.action_type)
    if kind is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Type d'action inconnu.")
    if body.mode not in allowed_modes(kind.level):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Une opération sensible (niveau 3) ne peut jamais être automatique."
        )
    policy = db.get(ActionPolicy, (company.id, body.action_type))
    before = policy.mode if policy else kind.default_mode
    if policy is None:
        policy = ActionPolicy(company_id=company.id, action_type=body.action_type)
        db.add(policy)
    policy.mode, policy.updated_by_id, policy.updated_at = body.mode, auth.user.id, func.now()
    audit.record(
        db,
        request,
        "action.policy",
        actor=auth.user,
        company_id=company.id,
        target=kind.label,
        details={"from": before, "to": body.mode, "type": body.action_type},
    )
    db.commit()
    return {"action_type": body.action_type, "mode": body.mode}


@router.get("/companies/{company_id}/actions")
def list_actions(
    company_id: uuid.UUID,
    request: Request,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    query = select(Action).where(Action.company_id == company.id).order_by(Action.created_at.desc()).limit(200)
    if status_filter:
        query = query.where(Action.status.in_(status_filter.split(",")))
    items = [action_out(a) for a in db.scalars(query)]
    counts = dict(
        db.execute(
            select(Action.status, func.count()).where(Action.company_id == company.id).group_by(Action.status)
        ).all()
    )
    return {"items": items, "counts": counts, "can_approve": actions.can_approve(db, auth.user, company.id)}


class ProposeIn(BaseModel):
    action_type: str
    title: Annotated[str, Field(min_length=3, max_length=300)]
    payload: dict[str, Any]
    trigger: dict[str, Any] = Field(default_factory=dict)


@router.post("/companies/{company_id}/actions", status_code=status.HTTP_201_CREATED)
def propose(
    company_id: uuid.UUID,
    body: ProposeIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True, module="finance")
    try:
        action = actions.propose(
            db,
            request,
            company,
            body.action_type,
            body.payload,
            title=body.title,
            proposed_by="user",
            user=auth.user,
            trigger=body.trigger,
        )
    except actions.ActionRefused as exc:
        db.rollback()
        raise _refused(exc) from exc
    db.commit()
    return action_out(action)


@router.post("/companies/{company_id}/actions/from-alert", status_code=status.HTTP_201_CREATED)
def propose_from_alert(
    company_id: uuid.UUID,
    body: dict[str, Any],
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    """L'agent exécutif prépare l'action proposée pour une alerte ; le dirigeant la validera."""
    company = company_access(db, request, auth.user, company_id, write=True, module="finance")
    fingerprint, action_type = body.get("alert"), body.get("action_type")
    ds = load(db, company, today())
    months = engine.build_months(ds)
    alerts = {a["fingerprint"]: a for a in anomalies.detect(db, ds, months, treasury.forecast(ds))}
    alert = alerts.get(fingerprint)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerte introuvable ou déjà résolue.")
    draft = next((d for d in drafts_for_alert(db, company, alert) if d["action_type"] == action_type), None)
    if draft is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Aucune action de ce type n'est proposée pour cette alerte."
        )
    existing = [
        a
        for a in actions.existing_for_trigger(db, company.id, fingerprint)
        if a.action_type == action_type and a.status in ("pending", "done", "approved")
    ]
    if existing:
        return action_out(existing[0])
    payload = dict(draft["payload"])
    if not payload.get("to") and draft["action_type"].startswith("email."):
        payload["to"] = "a-completer@exemple.invalid"  # adresse à saisir avant validation
    try:
        action = actions.propose(
            db,
            request,
            company,
            draft["action_type"],
            payload,
            title=draft["title"],
            proposed_by="agent:executif",
            user=auth.user,
            trigger=draft["trigger"],
        )
    except actions.ActionRefused as exc:
        db.rollback()
        raise _refused(exc) from exc
    db.commit()
    return action_out(action)


class ApproveIn(BaseModel):
    overrides: dict[str, Any] | None = None
    confirmation: str | None = None
    save_recipient: bool = True


@router.post("/companies/{company_id}/actions/{action_id}/approve")
def approve(
    company_id: uuid.UUID,
    action_id: uuid.UUID,
    body: ApproveIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    action = _get(db, company.id, action_id)
    if (body.overrides or {}).get("to", action.payload.get("to", "")).endswith(".invalid"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Renseignez l'adresse e-mail du destinataire.")
    try:
        actions.approve(
            db,
            request,
            company,
            action,
            auth.user,
            auth.session,
            overrides=body.overrides,
            confirmation=body.confirmation,
        )
    except actions.ActionRefused as exc:
        db.commit()  # le refus est journalisé
        raise _refused(exc) from exc
    # L'adresse saisie est mémorisée sur la fiche du tiers pour les prochaines fois.
    party_id = action.payload.get("party_id")
    if body.save_recipient and party_id and action.payload.get("to"):
        party = db.get(Party, uuid.UUID(party_id))
        if party and party.company_id == company.id and not party.email:
            party.email = action.payload["to"]
    db.commit()
    return action_out(action)


class RejectIn(BaseModel):
    reason: Annotated[str, Field(max_length=500)] | None = None


@router.post("/companies/{company_id}/actions/{action_id}/reject")
def reject(
    company_id: uuid.UUID,
    action_id: uuid.UUID,
    body: RejectIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    try:
        action = actions.reject(db, request, company, _get(db, company.id, action_id), auth.user, body.reason)
    except actions.ActionRefused as exc:
        raise _refused(exc) from exc
    db.commit()
    return action_out(action)


@router.post("/companies/{company_id}/actions/{action_id}/undo")
def undo(
    company_id: uuid.UUID,
    action_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    try:
        action = actions.undo(db, request, company, _get(db, company.id, action_id), auth.user)
    except actions.ActionRefused as exc:
        raise _refused(exc) from exc
    db.commit()
    return action_out(action)


@router.get("/companies/{company_id}/actions/{action_id}/file")
def action_file(
    company_id: uuid.UUID,
    action_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    action = _get(db, company.id, action_id)
    path = (action.result or {}).get("file")
    if action.status != "done" or not path or not Path(path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.")
    if not actions.can_approve(db, auth.user, company.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé au dirigeant.")
    audit.record(db, request, "action.download", actor=auth.user, company_id=company.id, target=action.title)
    db.commit()
    return FileResponse(path, media_type="application/xml", filename=action.result.get("filename", "virement.xml"))


@router.get("/companies/{company_id}/tasks")
def list_tasks(company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)):
    company = company_access(db, request, auth.user, company_id)
    rows = db.scalars(
        select(Task).where(Task.company_id == company.id).order_by(Task.done, Task.created_at.desc()).limit(200)
    )
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "details": t.details,
            "done": t.done,
            "created_at": t.created_at,
            "action_id": str(t.action_id) if t.action_id else None,
        }
        for t in rows
    ]


@router.patch("/companies/{company_id}/tasks/{task_id}")
def update_task(
    company_id: uuid.UUID,
    task_id: uuid.UUID,
    body: dict[str, bool],
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True)
    task = db.scalar(select(Task).where(Task.id == task_id, Task.company_id == company.id))
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    task.done = bool(body.get("done"))
    db.commit()
    return {"id": str(task.id), "done": task.done}


@router.get("/companies/{company_id}/outbox")
def outbox(company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)):
    company = company_access(db, request, auth.user, company_id, module="finance")
    rows = db.scalars(
        select(OutboundEmail)
        .where(OutboundEmail.company_id == company.id)
        .order_by(OutboundEmail.sent_at.desc())
        .limit(100)
    )
    return [
        {
            "id": str(e.id),
            "to": e.to_address,
            "subject": e.subject,
            "body": e.body,
            "transport": e.transport,
            "sent_at": e.sent_at,
            "action_id": str(e.action_id) if e.action_id else None,
        }
        for e in rows
    ]


@router.get("/companies/{company_id}/outbox/{email_id}.eml")
def outbox_eml(
    company_id: uuid.UUID,
    email_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    e = db.scalar(select(OutboundEmail).where(OutboundEmail.id == email_id, OutboundEmail.company_id == company.id))
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Courriel introuvable.")
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"], msg["Subject"], msg["Message-ID"] = e.to_address, e.subject, e.message_id or ""
    msg.set_content(e.body)
    return Response(
        bytes(msg),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="courriel-{e.id.hex[:8]}.eml"'},
    )


class PartyPatch(BaseModel):
    email: Annotated[str, Field(max_length=254)] | None = None
    contact_name: Annotated[str, Field(max_length=200)] | None = None


@router.patch("/companies/{company_id}/parties/{party_id}")
def update_party(
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    body: PartyPatch,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True)
    party = db.scalar(select(Party).where(Party.id == party_id, Party.company_id == company.id))
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tiers introuvable.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(party, field, (value or "").strip() or None)
    audit.record(
        db,
        request,
        "party.update",
        actor=auth.user,
        company_id=company.id,
        target=party.name,
        details={"fields": sorted(body.model_dump(exclude_unset=True))},
    )
    db.commit()
    return {"id": str(party.id), "email": party.email, "contact_name": party.contact_name}
