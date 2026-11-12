from tests.conftest import PASSWORD, SETUP


def test_health(anon):
    assert anon.get("/api/health").json()["status"] == "ok"


def test_setup_creates_admin_company_and_session(anon):
    assert anon.get("/api/setup/status").json() == {"initialized": False}

    response = anon.post("/api/setup", json=SETUP)
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "dirigeante@exemple.fr"  # normalisée
    assert user["is_admin"] is True
    assert user["memberships"][0]["role"] == "owner"
    assert "password" not in response.text

    assert anon.get("/api/setup/status").json() == {"initialized": True}
    # La session est ouverte dès la fin de l'installation.
    assert anon.get("/api/auth/me").json()["email"] == "dirigeante@exemple.fr"
    company = anon.get("/api/companies").json()[0]
    assert company["name"] == "Atelier Martin"
    assert company["enabled_modules"] == ["documents", "finance"]


def test_setup_runs_only_once(admin, anon):
    second = {**SETUP, "admin": {**SETUP["admin"], "email": "intrus@exemple.fr"}}
    response = anon.post("/api/setup", json=second)
    assert response.status_code == 409
    assert anon.post("/api/auth/login", json={"email": "intrus@exemple.fr", "password": PASSWORD}).status_code == 401


def test_setup_rejects_weak_password_and_unknown_module(anon):
    weak = {**SETUP, "admin": {**SETUP["admin"], "password": "court"}}
    assert anon.post("/api/setup", json=weak).status_code == 422
    unknown = {**SETUP, "modules": ["finance", "telepathie"]}
    assert anon.post("/api/setup", json=unknown).status_code == 422
    assert anon.get("/api/setup/status").json() == {"initialized": False}
