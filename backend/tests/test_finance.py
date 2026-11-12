"""Parcours complet sur le restaurant de démonstration : import, analyses, alertes, vérification.

Le jeu de données est construit une seule fois pour le module (environ 30 secondes).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PASSWORD, build_bistrot, truncate_all

pytestmark = pytest.mark.shared_data


@pytest.fixture(scope="module")
def bistrot(data_dir, demo_files):
    client = build_bistrot(demo_files, ["documents", "finance"])
    yield client
    truncate_all()


def viewer_client(admin: TestClient, role: str = "viewer") -> TestClient:
    email = f"{role}@bistrot.example"
    r = admin.post(
        "/api/users",
        json={
            "email": email,
            "full_name": role,
            "password": PASSWORD,
            "memberships": [{"company_id": admin.company_id, "role": role}],
        },
    )
    assert r.status_code in (201, 409)
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return client


def test_documents_are_classified(bistrot):
    counts = bistrot.get(f"{bistrot.base}/documents", params={"limit": 1}).json()["counts"]
    # Le bon de livraison n'est pas une facture complète : il attend une vérification humaine.
    assert counts == {"verified": counts["verified"], "duplicate": 1, "to_review": 1}
    assert counts["verified"] > 300


def test_same_file_twice_is_rejected(bistrot, demo_files):
    path = sorted((demo_files / "factures").iterdir())[0]
    r = bistrot.post(f"{bistrot.base}/documents", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 409
    assert "déjà été importé" in r.json()["detail"]["message"]


def test_unsupported_and_forbidden_uploads(bistrot):
    r = bistrot.post(f"{bistrot.base}/documents", files={"file": ("x.exe", b"MZ\x90\x00")})
    assert r.status_code == 415
    viewer = viewer_client(bistrot)
    assert viewer.post(f"{bistrot.base}/documents", files={"file": ("a.pdf", b"%PDF-1.4")}).status_code == 403
    # La consultation reste possible.
    assert viewer.get(f"{bistrot.base}/finance/overview").status_code == 200


def test_document_detail_and_original_file(bistrot):
    items = bistrot.get(f"{bistrot.base}/documents", params={"q": "Marée", "limit": 1}).json()["items"]
    doc = bistrot.get(f"{bistrot.base}/documents/{items[0]['id']}").json()
    inv = doc["invoice"]
    assert inv["party"] == "Marée Atlantique" and inv["category"] == "alimentaire"
    assert inv["lines"] and all(line["unit_price"] for line in inv["lines"])
    assert all(v == "confirmed" for k, v in inv["field_status"].items() if k != "due_date")
    file = bistrot.get(f"{bistrot.base}/documents/{items[0]['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF")
    assert file.headers["content-disposition"].startswith("inline")


def test_overview_kpis_are_explained(bistrot):
    data = bistrot.get(f"{bistrot.base}/finance/overview").json()
    assert data["is_restaurant"] is True
    kpis = {k["key"]: k for k in data["kpis"]}
    assert {"revenue", "ebe", "food_cost", "drinks_cost", "payroll", "ticket"} <= set(kpis)
    revenue = kpis["revenue"]
    assert revenue["value"] > 30000 and revenue["formula"] and revenue["inputs"]
    assert 20 < kpis["food_cost"]["value"] < 40
    # L'EBE se recompose exactement à partir de ses données d'entrée.
    ebe = kpis["ebe"]
    assert abs(sum(i["value"] for i in ebe["inputs"]) - ebe["value"]) < 0.05
    assert len(data["series"]) >= 12
    assert data["treasury"]["available"] is True


def test_alerts_find_the_planted_situations(bistrot):
    alerts = bistrot.get(f"{bistrot.base}/finance/alerts").json()["items"]
    kinds = {a["kind"] for a in alerts}
    expected = {
        "food_cost_drift",
        "overdue_receivable",
        "redundant_subscription",
        "price_increase",
        "unusual_invoice",
        "missing_invoice",
        "duplicate",
        "treasury_tension",
    }
    assert expected <= kinds, expected - kinds
    titles = " | ".join(a["title"] for a in alerts)
    assert "saumon" in titles and "Delmas Conseil" in titles and "TactilResto" in titles
    for a in alerts:
        if a["impact"]:
            assert a["impact"]["formula"] and a["impact"]["label"]


def test_alert_review_is_persisted_and_audited(bistrot):
    alert = bistrot.get(f"{bistrot.base}/finance/alerts").json()["items"][0]
    r = bistrot.post(
        f"{bistrot.base}/finance/alerts/review",
        json={"fingerprint": alert["fingerprint"], "status": "acknowledged", "note": "Vu avec le fournisseur"},
    )
    assert r.status_code == 200
    again = {a["fingerprint"]: a for a in bistrot.get(f"{bistrot.base}/finance/alerts").json()["items"]}
    assert again[alert["fingerprint"]]["status"] == "acknowledged"
    assert again[alert["fingerprint"]]["review_note"] == "Vu avec le fournisseur"
    assert bistrot.get("/api/audit").json()["items"][0]["action"] == "alert.review"
    bistrot.post(f"{bistrot.base}/finance/alerts/review", json={"fingerprint": alert["fingerprint"], "status": "open"})


def test_review_flow_for_delivery_note(bistrot):
    doc = bistrot.get(f"{bistrot.base}/documents", params={"status": "to_review"}).json()["items"][0]
    assert "BL" in doc["filename"]
    url = f"{bistrot.base}/documents/{doc['id']}"
    refused = bistrot.patch(f"{url}/invoice", json={"validate": True})
    assert refused.status_code == 422
    ignored = bistrot.post(f"{url}/status", json={"action": "ignore"}).json()
    assert ignored["status"] == "ignored"
    assert bistrot.post(f"{url}/status", json={"action": "restore"}).json()["status"] == "to_review"


def test_manual_correction_and_validation(bistrot):
    items = bistrot.get(f"{bistrot.base}/documents", params={"q": "Hygiène", "limit": 1}).json()["items"]
    url = f"{bistrot.base}/documents/{items[0]['id']}"
    inconsistent = bistrot.patch(f"{url}/invoice", json={"total_ht": 1, "validate": True})
    assert inconsistent.status_code == 422
    inv = bistrot.get(url).json()["invoice"]
    ok = bistrot.patch(f"{url}/invoice", json={"total_ht": inv["total_ht"], "category": "entretien", "validate": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "validated"


def test_bank_reimport_adds_nothing(bistrot, demo_files):
    path = next((demo_files / "banque").glob("*.csv"))
    r = bistrot.post(f"{bistrot.base}/imports/bank", files={"file": (path.name, path.read_bytes())}).json()
    assert r["rows_added"] == 0
    summary = bistrot.get(f"{bistrot.base}/data/summary").json()
    assert summary["bank"]["count"] > 600 and summary["bank"]["to_classify"] == 0


def test_module_must_be_enabled(bistrot):
    bistrot.put(f"/api/companies/{bistrot.company_id}/modules", json={"modules": ["documents"]})
    try:
        r = bistrot.get(f"{bistrot.base}/finance/overview")
        assert r.status_code == 403 and "module" in r.json()["detail"]
    finally:
        bistrot.put(f"/api/companies/{bistrot.company_id}/modules", json={"modules": ["documents", "finance"]})


def test_other_company_documents_are_invisible(bistrot):
    other = bistrot.post("/api/companies", json={"name": "Autre société"}).json()
    doc = bistrot.get(f"{bistrot.base}/documents", params={"limit": 1}).json()["items"][0]
    assert bistrot.get(f"/api/companies/{other['id']}/documents/{doc['id']}").status_code in (403, 404)
