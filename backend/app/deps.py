import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.db import get_db
from app.models import Company, Membership, User, UserSession
from app.security import hash_token

SESSION_COOKIE = "bab_session"


@dataclass
class Auth:
    user: User
    session: UserSession


def now() -> datetime:
    return datetime.now(UTC)


def check_password_policy(password: str) -> None:
    minimum = get_settings().password_min_length
    if len(password) < minimum:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Le mot de passe doit contenir au moins {minimum} caractères.",
        )


def get_auth(request: Request, db: Session = Depends(get_db)) -> Auth:
    token = request.cookies.get(SESSION_COOKIE)
    session = None
    if token:
        session = db.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token), UserSession.expires_at > now())
        )
    if session is None or not session.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")
    return Auth(user=session.user, session=session)


def get_admin(request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> Auth:
    if not auth.user.is_admin:
        audit.record(
            db,
            request,
            "access.admin",
            actor=auth.user,
            outcome="denied",
            target=f"{request.method} {request.url.path}",
        )
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs du boîtier.")
    return auth


def company_role(db: Session, user: User, company_id: uuid.UUID) -> str | None:
    return db.scalar(select(Membership.role).where(Membership.user_id == user.id, Membership.company_id == company_id))


def get_company_for(
    db: Session, request: Request, user: User, company_id: uuid.UUID, *, manage: bool = False
) -> tuple[Company, str | None]:
    """Charge une entreprise si l'utilisateur y a accès.

    `manage=True` exige le rôle de dirigeant (owner) ou d'administrateur du boîtier.
    Une entreprise à laquelle l'utilisateur n'est pas rattaché est signalée comme
    introuvable, pour ne pas révéler son existence.
    """
    company = db.get(Company, company_id)
    role = company_role(db, user, company_id) if company else None
    if company is None or (role is None and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entreprise introuvable.")
    if manage and not (user.is_admin or role == "owner"):
        audit.record(
            db,
            request,
            "access.company",
            actor=user,
            outcome="denied",
            company_id=company.id,
            target=f"{request.method} {request.url.path}",
        )
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Votre rôle ne permet pas de modifier cette entreprise.")
    return company, role


WRITE_ROLES = ("owner", "manager")


def company_access(
    db: Session,
    request: Request,
    user: User,
    company_id: uuid.UUID,
    *,
    write: bool = False,
    module: str | None = None,
) -> Company:
    """Contrôle d'accès aux données d'une entreprise.

    Lecture : tout membre. Écriture (import, validation) : dirigeant ou gestionnaire.
    `module` : le module correspondant doit être activé pour l'entreprise.
    """
    company, role = get_company_for(db, request, user, company_id)
    if module and module not in company.enabled_modules:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Ce module n'est pas activé pour cette entreprise. Activez-le dans « Entreprise et modules ».",
        )
    if write and not (user.is_admin or role in WRITE_ROLES):
        audit.record(
            db,
            request,
            "access.data",
            actor=user,
            outcome="denied",
            company_id=company.id,
            target=f"{request.method} {request.url.path}",
        )
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Votre rôle ne permet que la consultation.")
    return company
