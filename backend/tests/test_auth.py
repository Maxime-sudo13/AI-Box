from datetime import timedelta

from sqlalchemy import select, update

from app.db import SessionLocal
from app.deps import SESSION_COOKIE, now
from app.models import AuditEvent, User, UserSession
from app.security import hash_token
from tests.conftest import PASSWORD

EMAIL = "dirigeante@exemple.fr"


def login(client, password=PASSWORD, email=EMAIL):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_endpoints_require_authentication(admin, anon):
    for path in ("/api/auth/me", "/api/companies", "/api/users", "/api/audit"):
        assert anon.get(path).status_code == 401, path


def test_login_logout(admin, anon):
    response = login(anon)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anon.get("/api/auth/me").status_code == 200

    token = anon.cookies[SESSION_COOKIE]
    assert anon.post("/api/auth/logout").status_code == 204
    # Le jeton est révoqué côté serveur, pas seulement effacé du navigateur.
    anon.cookies.set(SESSION_COOKIE, token)
    assert anon.get("/api/auth/me").status_code == 401


def test_only_token_hash_is_stored(admin):
    token = admin.cookies[SESSION_COOKIE]
    with SessionLocal() as db:
        stored = db.scalars(select(UserSession.token_hash)).all()
    assert stored == [hash_token(token)]
    assert token not in stored


def test_wrong_password_and_unknown_user_look_the_same(admin, anon):
    wrong = login(anon, password="mauvais-mot-de-passe")
    unknown = login(anon, email="inconnu@exemple.fr")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_account_locks_after_repeated_failures(admin, anon):
    for _ in range(5):
        assert login(anon, password="mauvais-mot-de-passe").status_code == 401
    # Même le bon mot de passe est refusé pendant le verrouillage.
    assert login(anon).status_code == 423

    with SessionLocal() as db:
        db.execute(update(User).values(locked_until=now() - timedelta(seconds=1)))
        db.commit()
    assert login(anon).status_code == 200


def test_expired_session_is_rejected(admin):
    with SessionLocal() as db:
        db.execute(update(UserSession).values(expires_at=now() - timedelta(seconds=1)))
        db.commit()
    assert admin.get("/api/auth/me").status_code == 401


def test_change_password_revokes_other_sessions(admin, anon):
    assert login(anon).status_code == 200
    new_password = "nouveau-mot-de-passe-solide"

    refused = admin.post(
        "/api/auth/password", json={"current_password": "faux", "new_password": new_password}
    )
    assert refused.status_code == 403
    too_short = admin.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "court"}
    )
    assert too_short.status_code == 422

    changed = admin.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": new_password}
    )
    assert changed.status_code == 204
    assert admin.get("/api/auth/me").status_code == 200  # session courante conservée
    assert anon.get("/api/auth/me").status_code == 401  # autre appareil déconnecté
    assert login(anon).status_code == 401
    assert login(anon, password=new_password).status_code == 200


def test_logins_are_audited_without_secrets(admin, anon):
    login(anon, password="mauvais-mot-de-passe")
    login(anon)
    with SessionLocal() as db:
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.action == "auth.login").order_by(AuditEvent.id)
        ).all()
    assert [e.outcome for e in events] == ["failure", "success"]
    assert all(e.actor_label == EMAIL for e in events)
    assert "mauvais-mot-de-passe" not in str([e.details for e in events])
