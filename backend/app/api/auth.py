from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.api.users import user_out
from app.config import get_settings
from app.db import get_db
from app.deps import SESSION_COOKIE, Auth, check_password_policy, get_auth, now
from app.models import User, UserSession
from app.schemas import LoginIn, PasswordChange, UserOut
from app.security import hash_password, new_session_token, verify_password

router = APIRouter(prefix="/auth", tags=["authentification"])


def open_session(db: Session, request: Request, response: Response, user: User) -> None:
    settings = get_settings()
    token, token_hash = new_session_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now() + ttl,
            ip=audit.client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == body.email).with_for_update())

    if user and user.locked_until and user.locked_until > now():
        audit.record(
            db, request, "auth.login", actor=user, outcome="denied", details={"reason": "locked"}
        )
        db.commit()
        raise HTTPException(
            status.HTTP_423_LOCKED,
            "Compte temporairement verrouillé après plusieurs échecs. Réessayez plus tard.",
        )

    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or not user.is_active:
        details = {"reason": "bad_credentials"}
        if user and not password_ok:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now() + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
                details = {"reason": "bad_credentials", "locked": True}
        elif user:
            details = {"reason": "inactive"}
        audit.record(
            db,
            request,
            "auth.login",
            actor=user,
            actor_label=body.email,
            outcome="failure",
            details=details,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now()
    # Nettoyage opportuniste des sessions expirées de cet utilisateur.
    db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now())
    )
    open_session(db, request, response, user)
    audit.record(db, request, "auth.login", actor=user)
    db.commit()
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    db.delete(auth.session)
    audit.record(db, request, "auth.logout", actor=auth.user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(auth: Auth = Depends(get_auth)):
    return user_out(auth.user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    if not verify_password(auth.user.password_hash, body.current_password):
        audit.record(db, request, "auth.password_change", actor=auth.user, outcome="failure")
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Mot de passe actuel incorrect.")
    check_password_policy(body.new_password)
    auth.user.password_hash = hash_password(body.new_password)
    # Les autres appareils connectés doivent se réauthentifier.
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == auth.user.id, UserSession.id != auth.session.id
        )
    )
    audit.record(db, request, "auth.password_change", actor=auth.user)
    db.commit()
