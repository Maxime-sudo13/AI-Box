from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit
from app.api.auth import open_session
from app.api.users import user_out
from app.db import get_db
from app.deps import check_password_policy
from app.models import Company, Membership, User
from app.schemas import SetupIn, SetupStatus, UserOut
from app.security import hash_password

router = APIRouter(prefix="/setup", tags=["installation"])

# Clé arbitraire du verrou consultatif qui sérialise la première configuration.
_SETUP_LOCK = 4_210_001


def _initialized(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(User)) > 0


@router.get("/status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)):
    return SetupStatus(initialized=_initialized(db))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def run_setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Première configuration : crée l'administrateur et son entreprise, une seule fois."""
    check_password_policy(body.admin.password)
    # Deux navigateurs ne doivent pas pouvoir créer chacun « le premier » administrateur.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SETUP_LOCK})
    if _initialized(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Le boîtier est déjà configuré.")

    company = Company(**body.company.model_dump(), enabled_modules=body.modules)
    user = User(
        email=body.admin.email,
        full_name=body.admin.full_name,
        password_hash=hash_password(body.admin.password),
        is_admin=True,
    )
    user.memberships = [Membership(company=company, role="owner")]
    db.add(user)
    db.flush()
    open_session(db, request, response, user)
    audit.record(
        db,
        request,
        "setup.complete",
        actor=user,
        company_id=company.id,
        target=company.name,
        details={"modules": body.modules},
    )
    db.commit()
    db.refresh(user)
    return user_out(user)
