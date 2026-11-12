"""Exécution d'actions : niveaux de risque, autorisations, validation, journal, annulation."""

import threading
import time

import pytest
from aiosmtpd.controller import Controller
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.conftest import PASSWORD, build_bistrot, truncate_all

pytestmark = pytest.mark.shared_data

IBAN_FR = "FR7630006000011234567890189"
IBAN_DE = "DE89370400440532013000"


@pytest.fixture(scope="module")
def bistrot(data_dir, demo_files):
    client = build_bistrot(demo_files, ["documents", "finance", "conseiller"])
    yield client
    truncate_all()


def member(admin, role):
    email = f"{role}-actions@bistrot.example"
    admin.post(
        "/api/users",
        json={
            "email": email,
            "full_name": role,
            "password": PASSWORD,
            "memberships": [{"company_id": admin.company_id, "role": role}],
        },
    )
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return client


def alerts(client):
    return {a["kind"]: a for a in client.get(f"{client.base}/finance/alerts").json()["items"]}


def test_catalog_has_three_levels_and_level3_never_automatic(bistrot):
    cat = bistrot.get(f"{bistrot.base}/actions/catalog").json()
    levels = {i["key"]: i["level"] for i in cat["items"]}
    assert set(levels.values()) == {1, 2, 3}
    transfer = next(i for i in cat["items"] if i["key"] == "payment.transfer")
    assert "automatic" not in transfer["allowed_modes"]
    r = bistrot.put(f"{bistrot.base}/actions/policies", json={"action_type": "payment.transfer", "mode": "automatic"})
    assert r.status_code == 422


def test_level1_runs_automatically_and_can_be_undone(bistrot):
    r = bistrot.post(
        f"{bistrot.base}/actions",
        json={
            "action_type": "task.create",
            "title": "Créer une tâche",
            "payload": {"title": "Inventaire de la chambre froide"},
        },
    )
    action = r.json()
    assert action["status"] == "done" and action["authorization"]["mode"] == "automatic"
    assert any(t["title"] == "Inventaire de la chambre froide" for t in bistrot.get(f"{bistrot.base}/tasks").json())
    undone = bistrot.post(f"{bistrot.base}/actions/{action['id']}/undo").json()
    assert undone["status"] == "undone"
    assert not any(t["title"] == "Inventaire de la chambre froide" for t in bistrot.get(f"{bistrot.base}/tasks").json())


def test_agent_proposes_reminder_and_owner_approves(bistrot):
    alert = alerts(bistrot)["overdue_receivable"]
    assert any(p["action_type"] == "email.payment_reminder" for p in alert["proposals"])
    action = bistrot.post(
        f"{bistrot.base}/actions/from-alert",
        json={"alert": alert["fingerprint"], "action_type": "email.payment_reminder"},
    ).json()
    assert action["status"] == "pending" and action["risk_level"] == 2 and action["proposed_by"] == "agent:executif"
    assert action["payload"]["to"] == "comptabilite@delmas-conseil.example"
    assert "Anne Delmas" in action["payload"]["body"] and "BT-" in action["payload"]["subject"]
    # Proposer deux fois la même action ne crée pas de doublon.
    again = bistrot.post(
        f"{bistrot.base}/actions/from-alert",
        json={"alert": alert["fingerprint"], "action_type": "email.payment_reminder"},
    ).json()
    assert again["id"] == action["id"]

    done = bistrot.post(
        f"{bistrot.base}/actions/{action['id']}/approve",
        json={"overrides": {"body": action["payload"]["body"] + "\nMerci."}},
    ).json()
    assert done["status"] == "done", done
    assert done["authorization"]["by"] == "gerant@bistrot.example"
    assert done["authorization"]["modified_fields"] == ["body"]
    assert done["result"]["transport"] == "outbox"
    sent = bistrot.get(f"{bistrot.base}/outbox").json()[0]
    assert sent["to"] == "comptabilite@delmas-conseil.example" and sent["body"].endswith("Merci.")
    eml = bistrot.get(f"{bistrot.base}/outbox/{sent['id']}.eml")
    assert eml.status_code == 200 and b"Subject: Relance" in eml.content
    # L'action est rattachée à son alerte et à son journal.
    followed = alerts(bistrot)["overdue_receivable"]
    assert followed["actions"][0]["status"] == "done"
    # L'alerte suivie d'une action passe d'elle-même à « prise en compte ».
    assert followed["status"] == "acknowledged" and "Courriel" in followed["review_note"]
    trail = [e["action"] for e in bistrot.get("/api/audit", params={"limit": 10}).json()["items"]]
    assert {"action.propose", "action.approve", "action.execute"} <= set(trail)


def test_manager_can_propose_but_not_approve(bistrot):
    manager = member(bistrot, "manager")
    manager.base = bistrot.base
    alert = alerts(bistrot)["redundant_subscription"]
    action = manager.post(
        f"{bistrot.base}/actions/from-alert", json={"alert": alert["fingerprint"], "action_type": "email.cancellation"}
    ).json()
    assert action["status"] == "pending" and action["payload"]["to"] == "resiliation@tactilresto.example"
    refused = manager.post(f"{bistrot.base}/actions/{action['id']}/approve", json={})
    assert refused.status_code == 403
    viewer = member(bistrot, "viewer")
    assert (
        viewer.post(
            f"{bistrot.base}/actions",
            json={"action_type": "task.create", "title": "Une tâche", "payload": {"title": "Une tâche"}},
        ).status_code
        == 403
    )
    assert (
        bistrot.post(f"{bistrot.base}/actions/{action['id']}/reject", json={"reason": "Préavis à vérifier"}).json()[
            "status"
        ]
        == "rejected"
    )


def test_forbidden_policy_blocks_and_is_logged(bistrot):
    assert (
        bistrot.put(
            f"{bistrot.base}/actions/policies", json={"action_type": "email.supplier_request", "mode": "forbidden"}
        ).status_code
        == 200
    )
    try:
        r = bistrot.post(
            f"{bistrot.base}/actions",
            json={
                "action_type": "email.supplier_request",
                "title": "Écrire au primeur",
                "payload": {"to": "commandes@primeurs-du-val.example", "subject": "Test", "body": "Bonjour"},
            },
        )
        assert r.status_code == 201 and r.json()["status"] == "rejected"
        assert any(
            e["action"] == "action.blocked" and e["outcome"] == "denied"
            for e in bistrot.get("/api/audit", params={"limit": 5}).json()["items"]
        )
    finally:
        bistrot.put(
            f"{bistrot.base}/actions/policies", json={"action_type": "email.supplier_request", "mode": "approval"}
        )


def test_level3_requires_reauthentication_and_confirmation(bistrot):
    bad = bistrot.post(
        f"{bistrot.base}/actions",
        json={
            "action_type": "payment.transfer",
            "title": "Virement",
            "payload": {
                "creditor_name": "Cave des Coteaux",
                "creditor_iban": "FR7630006000011234567890188",
                "debtor_iban": IBAN_FR,
                "amount": "6754.20",
                "reference": "CC-2026-0125",
            },
        },
    )
    assert bad.status_code == 422 and "IBAN" in bad.json()["detail"]

    action = bistrot.post(
        f"{bistrot.base}/actions",
        json={
            "action_type": "payment.transfer",
            "title": "Payer la cave",
            "payload": {
                "creditor_name": "Cave des Coteaux",
                "creditor_iban": IBAN_DE,
                "debtor_iban": IBAN_FR,
                "amount": "6754.20",
                "reference": "CC-2026-0125",
            },
        },
    ).json()
    assert action["status"] == "pending" and action["risk_level"] == 3
    url = f"{bistrot.base}/actions/{action['id']}/approve"
    assert bistrot.post(url, json={"confirmation": "CONFIRMER"}).status_code == 428  # pas de réauthentification
    assert bistrot.post("/api/auth/reauth", json={"password": "faux"}).status_code == 403
    assert bistrot.post("/api/auth/reauth", json={"password": PASSWORD}).status_code == 204
    assert bistrot.post(url, json={"confirmation": "oui"}).status_code == 422  # confirmation explicite exigée
    done = bistrot.post(url, json={"confirmation": "CONFIRMER"}).json()
    assert done["status"] == "done" and done["authorization"]["reauthenticated_at"]
    xml = bistrot.get(f"{bistrot.base}/actions/{action['id']}/file")
    assert (
        xml.status_code == 200 and b"pain.001.001.03" in xml.content and b'<InstdAmt Ccy="EUR">6754.20<' in xml.content
    )


class Sink:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope)
        return "250 OK"


def test_real_smtp_delivery(bistrot, monkeypatch):
    sink = Sink()
    controller = Controller(sink, hostname="127.0.0.1", port=8025)
    controller.start()
    try:
        monkeypatch.setenv("BAB_SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("BAB_SMTP_PORT", "8025")
        monkeypatch.setenv("BAB_SMTP_STARTTLS", "false")
        monkeypatch.setenv("BAB_MAIL_FROM", "Bistrot <gerant@bistrot.example>")
        get_settings.cache_clear()
        alert = alerts(bistrot)["missing_invoice"]
        action = bistrot.post(
            f"{bistrot.base}/actions/from-alert",
            json={"alert": alert["fingerprint"], "action_type": "email.supplier_request"},
        ).json()
        assert action["payload"]["to"] == "contact@boucherie-marchand.example"
        done = bistrot.post(f"{bistrot.base}/actions/{action['id']}/approve", json={}).json()
        assert done["status"] == "done" and done["result"]["transport"] == "smtp"
        for _ in range(50):
            if sink.messages:
                break
            time.sleep(0.05)
        assert sink.messages and sink.messages[0].rcpt_tos == ["contact@boucherie-marchand.example"]
        assert b"duplicata" in sink.messages[0].content
    finally:
        controller.stop()
        get_settings.cache_clear()
    _ = threading


def test_missing_recipient_must_be_filled(bistrot):
    alert = alerts(bistrot)["unusual_invoice"]
    action = bistrot.post(
        f"{bistrot.base}/actions/from-alert",
        json={"alert": alert["fingerprint"], "action_type": "email.supplier_request"},
    ).json()
    if action["payload"]["to"].endswith(".invalid"):
        assert bistrot.post(f"{bistrot.base}/actions/{action['id']}/approve", json={}).status_code == 422
    done = bistrot.post(
        f"{bistrot.base}/actions/{action['id']}/approve", json={"overrides": {"to": "factures@volta.example"}}
    ).json()
    assert done["status"] == "done"
