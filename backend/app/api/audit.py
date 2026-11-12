from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Auth, get_admin
from app.models import AuditEvent
from app.schemas import AuditPage

router = APIRouter(prefix="/audit", tags=["journal"])


@router.get("", response_model=AuditPage)
def list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Auth = Depends(get_admin),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(AuditEvent))
    items = db.scalars(
        select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).offset(offset)
    ).all()
    return AuditPage(items=items, total=total)
