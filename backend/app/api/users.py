import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import Auth, check_password_policy, get_admin
from app.models import Company, Membership, User, UserSession
from app.schemas import MembershipIn, MembershipOut, UserCreate, UserOut, UserPatch
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["utilisateurs"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        memberships=sorted(
            (
                MembershipOut(company_id=m.company_id, company_name=m.company.name, role=m.role)
                for m in user.memberships
            ),
            key=lambda m: m.company_name.lower(),
        ),
    )


def _set_memberships(db: Session, user: User, memberships: list[MembershipIn]) -> None:
    wanted = {m.company_id: m.role for m in memberships}
    if len(wanted) != len(memberships):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Une entreprise est listée plusieurs fois."
        )
    if wanted:
        found = set(db.scalars(select(Company.id).where(Company.id.in_(wanted))))
        if found != set(wanted):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Entreprise inconnue.")
    user.memberships = [
        Membership(company_id=company_id, role=role) for company_id, role in wanted.items()
    ]


def _other_active_admins(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.is_admin, User.is_active, User.id != user.id)
    )


@router.get("", response_model=list[UserOut])
def list_users(_: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(func.lower(User.full_name)))
    return [user_out(u) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    request: Request,
    auth: Auth = Depends(get_admin),
    db: Session = Depends(get_db),
):
    check_password_policy(body.password)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cette adresse.")
    user = User(
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
    )
    db.add(user)
    _set_memberships(db, user, body.memberships)
    audit.record(
        db,
        request,
        "user.create",
        actor=auth.user,
        target=user.email,
        details={"is_admin": user.is_admin},
    )
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserPatch,
    request: Request,
    auth: Auth = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable.")

    changes = body.model_dump(exclude_unset=True)
    loses_admin = (changes.get("is_admin") is False and user.is_admin) or (
        changes.get("is_active") is False and user.is_active and user.is_admin
    )
    if loses_admin and _other_active_admins(db, user) == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Impossible : le boîtier doit conserver au moins un administrateur actif.",
        )

    revoke_sessions = False
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.is_active is not None:
        revoke_sessions |= user.is_active and not body.is_active
        user.is_active = body.is_active
        if body.is_active:
            user.failed_logins = 0
            user.locked_until = None
    if body.password is not None:
        check_password_policy(body.password)
        user.password_hash = hash_password(body.password)
        user.failed_logins = 0
        user.locked_until = None
        revoke_sessions = True
    if body.memberships is not None:
        _set_memberships(db, user, body.memberships)
    if revoke_sessions:
        # L'administrateur qui change son propre mot de passe garde sa session en cours.
        db.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id, UserSession.id != auth.session.id
            )
        )

    # Le journal retient les champs modifiés, jamais la valeur d'un mot de passe.
    audit.record(
        db,
        request,
        "user.update",
        actor=auth.user,
        target=user.email,
        details={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(user)
    return user_out(user)
