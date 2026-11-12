from tests.conftest import PASSWORD


def test_admin_creates_user_with_membership(admin, make_user):
    client = make_user("comptable@exemple.fr", role="manager")
    me = client.get("/api/auth/me").json()
    assert me["is_admin"] is False
    assert me["memberships"] == [{"company_id": admin.company_id, "company_name": "Atelier Martin", "role": "manager"}]
    assert len(admin.get("/api/users").json()) == 2


def test_duplicate_email_is_refused(admin, make_user):
    make_user("comptable@exemple.fr")
    again = admin.post(
        "/api/users",
        json={"email": "COMPTABLE@exemple.fr", "full_name": "Doublon", "password": PASSWORD},
    )
    assert again.status_code == 409


def test_non_admin_cannot_manage_users(admin, make_user):
    client = make_user("comptable@exemple.fr", role="owner")
    assert client.get("/api/users").status_code == 403
    assert (
        client.post(
            "/api/users",
            json={
                "email": "x@exemple.fr",
                "full_name": "X",
                "password": PASSWORD,
                "is_admin": True,
            },
        ).status_code
        == 403
    )
    assert client.patch(f"/api/users/{client.user['id']}", json={"is_admin": True}).status_code == 403
    assert client.get("/api/audit").status_code == 403

    # Le refus lui-même est historisé.
    denied = [e for e in admin.get("/api/audit").json()["items"] if e["outcome"] == "denied"]
    assert len(denied) == 4
    assert {e["actor_label"] for e in denied} == {"comptable@exemple.fr"}


def test_deactivated_user_loses_access_immediately(admin, make_user):
    client = make_user("comptable@exemple.fr")
    assert client.get("/api/auth/me").status_code == 200
    response = admin.patch(f"/api/users/{client.user['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": "comptable@exemple.fr", "password": PASSWORD}).status_code == 401
    )


def test_password_reset_by_admin_revokes_sessions(admin, make_user):
    client = make_user("comptable@exemple.fr")
    new_password = "reinitialise-par-admin"
    assert admin.patch(f"/api/users/{client.user['id']}", json={"password": new_password}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": "comptable@exemple.fr", "password": new_password}).status_code
        == 200
    )


def test_last_admin_cannot_be_removed(admin, make_user):
    me = admin.user["id"]
    assert admin.patch(f"/api/users/{me}", json={"is_admin": False}).status_code == 409
    assert admin.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 409

    second = make_user("associe@exemple.fr", is_admin=True)
    assert admin.patch(f"/api/users/{me}", json={"is_admin": False}).status_code == 200
    # Le second administrateur est désormais le dernier.
    assert second.patch(f"/api/users/{second.user['id']}", json={"is_admin": False}).status_code == 409


def test_memberships_are_replaced_and_validated(admin, make_user):
    client = make_user("comptable@exemple.fr", role="viewer")
    user_id = client.user["id"]
    unknown = admin.patch(
        f"/api/users/{user_id}",
        json={"memberships": [{"company_id": "00000000-0000-0000-0000-000000000000", "role": "viewer"}]},
    )
    assert unknown.status_code == 422
    bad_role = admin.patch(
        f"/api/users/{user_id}",
        json={"memberships": [{"company_id": admin.company_id, "role": "dieu"}]},
    )
    assert bad_role.status_code == 422

    assert admin.patch(f"/api/users/{user_id}", json={"memberships": []}).status_code == 200
    assert client.get("/api/companies").json() == []
