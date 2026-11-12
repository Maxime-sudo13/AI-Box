import pytest


@pytest.fixture
def second_company(admin):
    response = admin.post("/api/companies", json={"name": "Holding Martin"})
    assert response.status_code == 201
    return response.json()["id"]


def test_users_only_see_their_companies(admin, make_user, second_company):
    assert [c["name"] for c in admin.get("/api/companies").json()] == [
        "Atelier Martin",
        "Holding Martin",
    ]
    client = make_user("comptable@exemple.fr", role="viewer")
    companies = client.get("/api/companies").json()
    assert [(c["name"], c["role"]) for c in companies] == [("Atelier Martin", "viewer")]
    # Une entreprise étrangère est indiscernable d'une entreprise inexistante.
    assert client.get(f"/api/companies/{second_company}").status_code == 404
    assert (
        client.patch(f"/api/companies/{second_company}", json={"name": "Piratée"}).status_code
        == 404
    )


@pytest.mark.parametrize("role,expected", [("owner", 200), ("manager", 403), ("viewer", 403)])
def test_only_owner_manages_company(admin, make_user, role, expected):
    client = make_user("membre@exemple.fr", role=role)
    url = f"/api/companies/{admin.company_id}"
    assert client.get(url).status_code == 200
    assert client.patch(url, json={"sector": "Menuiserie"}).status_code == expected
    assert client.put(f"{url}/modules", json={"modules": ["rh"]}).status_code == expected
    assert client.post("/api/companies", json={"name": "Nouvelle"}).status_code == 403


def test_update_company_fields(admin):
    url = f"/api/companies/{admin.company_id}"
    updated = admin.patch(url, json={"sector": "Menuiserie", "siren": None}).json()
    assert updated["sector"] == "Menuiserie"
    assert updated["siren"] is None
    assert updated["name"] == "Atelier Martin"
    assert admin.patch(url, json={"siren": "12AB"}).status_code == 422
    assert admin.patch(url, json={"name": "  "}).status_code == 422


def test_modules_catalog_and_selection(admin):
    catalog = admin.get("/api/modules").json()
    assert len(catalog) == 10
    assert {"key", "name", "description", "available"} == set(catalog[0])

    url = f"/api/companies/{admin.company_id}/modules"
    assert admin.put(url, json={"modules": ["rh", "finance", "rh"]}).json()["enabled_modules"] == [
        "finance",
        "rh",
    ]
    assert admin.put(url, json={"modules": ["inconnu"]}).status_code == 422

    event = admin.get("/api/audit").json()["items"][0]
    assert event["action"] == "company.modules"
    assert event["details"] == {"enabled": ["rh"], "disabled": ["documents"]}


def test_audit_is_paginated_and_newest_first(admin, second_company):
    page = admin.get("/api/audit", params={"limit": 1}).json()
    assert page["total"] == 2
    assert [e["action"] for e in page["items"]] == ["company.create"]
    older = admin.get("/api/audit", params={"limit": 1, "offset": 1}).json()
    assert [e["action"] for e in older["items"]] == ["setup.complete"]
