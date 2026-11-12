import uuid
from typing import Any, Literal

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditEvent, User

Outcome = Literal["success", "denied", "failure"]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def record(
    db: Session,
    request: Request,
    action: str,
    *,
    actor: User | None = None,
    actor_label: str | None = None,
    outcome: Outcome = "success",
    company_id: uuid.UUID | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entrée au journal d'activité. L'appelant valide la transaction."""
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None,
            actor_label=actor.email if actor else actor_label,
            company_id=company_id,
            action=action,
            outcome=outcome,
            target=target,
            details=details or {},
            ip=client_ip(request),
        )
    )
