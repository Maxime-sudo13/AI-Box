"""Connecteurs : dossier surveillé, boîte mail, Qonto ; sécurité, permissions, isolation."""

import email.message
import json
import os
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.connectors.crypto import reset_key_cache
from app.connectors.folder import import_root
from app.connectors.registry import CONNECTORS
from app.db import SessionLocal, engine
from app.models import Connection


@pytest.fixture(autouse=True)
def isolated_data(data_dir):
    reset_key_cache()
    yield


def old(path: Path) -> Path:
    past = time.time() - 60
    os.utime(path, (past, past))
    return path


@pytest.fixture
def depot(demo_files):
    folder = import_root() / "scanner"
    if folder.exists():
        for p in folder.rglob("*"):
            if p.is_file():
                p.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    pdfs = sorted((demo_files / "factures").glob("*Primeurs*.pdf"))[:2]
    for pdf in pdfs:
        (folder / pdf.name).write_bytes(pdf.read_bytes())
        old(folder / pdf.name)
    bank = folder / "releve.csv"
    bank.write_text("Date;Libellé;Montant;Solde\n02/10/2026;PRLV SEPA URSSAF;-5 912,40;18 087,60\n", encoding="utf-8")
    old(bank)
    return folder


def connect(admin, connector, **body):
    return admin.post(f"/api/companies/{admin.company_id}/connections", json={"connector": connector, **body})


def test_catalog_lists_connectors_and_planned_integrations(admin):
    cat = admin.get("/api/connectors").json()
    assert {c["key"] for c in cat["available"]} == {"folder", "imap", "qonto"}
    assert {"pennylane", "sage", "odoo", "hubspot"} <= {p["key"] for p in cat["planned"]}
    imap = next(c for c in cat["available"] if c["key"] == "imap")
    assert any(f["secret"] for f in imap["fields"])
    # Les droits d'écriture ne sont jamais accordés par défaut.
    assert all(not p["default"] for c in cat["available"] for p in c["permissions"] if p["write"])


def test_folder_outside_root_is_refused(admin):
    for path in ("/etc", "../../..", "/"):
        r = connect(admin, "folder", settings={"path": path})
        assert r.status_code == 422, path


def test_folder_imports_documents_and_csv_once(admin, depot):
    conn = connect(admin, "folder", settings={"path": "scanner"}).json()
    assert conn["permissions"] == ["read_files"] and "3 fichier" in conn["test_message"]
    url = f"/api/companies/{admin.company_id}/connections/{conn['id']}"
    run = admin.post(f"{url}/sync").json()["run"]
    assert run["status"] == "success", run
    assert run["stats"]["documents"] == 2 and run["stats"]["tables"] == 1
    docs = admin.get(f"/api/companies/{admin.company_id}/documents").json()
    assert docs["total"] == 2
    again = admin.post(f"{url}/sync").json()["run"]
    assert again["stats"]["documents"] == 0  # rien n'est importé deux fois
    # Sans la permission d'écriture, les fichiers restent où ils sont.
    assert len(list(depot.glob("*.pdf"))) == 2
    trail = [e["action"] for e in admin.get("/api/audit").json()["items"]]
    assert "connector.sync" in trail and "connector.create" in trail


def test_folder_moves_files_only_with_write_permission(admin, depot):
    conn = connect(admin, "folder", settings={"path": "scanner"}, permissions=["read_files", "move_processed"]).json()
    admin.post(f"/api/companies/{admin.company_id}/connections/{conn['id']}/sync")
    assert not list(depot.glob("*.pdf"))
    assert len(list((depot / "importes").glob("*"))) == 3


def test_managers_and_viewers_cannot_create_connections(admin, make_user, depot):
    for role in ("manager", "viewer"):
        client = make_user(f"{role}@exemple.fr", role=role)
        r = client.post(
            f"/api/companies/{admin.company_id}/connections",
            json={"connector": "folder", "settings": {"path": "scanner"}},
        )
        assert r.status_code == 403, role


# --- Boîte mail -------------------------------------------------------------------------------


class FakeImap:
    """Serveur IMAP simulé : un message avec une facture PDF en pièce jointe."""

    instances: list["FakeImap"] = []
    pdf = b""

    def __init__(self, host, port, timeout=None):
        self.host, self.readonly, self.stored, self.fetched = host, None, [], []
        FakeImap.instances.append(self)

    def login(self, user, password):
        import imaplib

        if password != "bon-mot-de-passe":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        return "OK", [b"1"]

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b"41"]
        if command == "FETCH":
            self.fetched.append(args[1])
            msg = email.message.EmailMessage()
            msg["Subject"], msg["From"] = "Votre facture", "factures@primeurs-du-val.example"
            msg.set_content("Veuillez trouver ci-joint votre facture.")
            msg.add_attachment(FakeImap.pdf, maintype="application", subtype="pdf", filename="facture.pdf")
            return "OK", [(b"41 (BODY[] {1})", msg.as_bytes()), b")"]
        if command == "STORE":
            self.stored.append(args)
            return "OK", []
        raise AssertionError(command)

    def logout(self):
        return "BYE", []


@pytest.fixture
def fake_imap(monkeypatch, demo_files):
    FakeImap.instances = []
    FakeImap.pdf = sorted((demo_files / "factures").glob("*Marée*.pdf"))[0].read_bytes()
    monkeypatch.setattr(CONNECTORS["imap"], "imap_class", FakeImap)
    return FakeImap


IMAP = {"host": "imap.exemple.fr", "port": 993, "username": "factures@bistrot.example", "folder": "Factures"}


def test_imap_wrong_password_is_refused(admin, fake_imap):
    r = connect(admin, "imap", settings=IMAP, secrets={"password": "faux"})
    assert r.status_code == 422 and "refusé" in r.json()["detail"]


def test_imap_reads_without_marking_by_default(admin, fake_imap):
    conn = connect(admin, "imap", settings=IMAP, secrets={"password": "bon-mot-de-passe"}).json()
    run = admin.post(f"/api/companies/{admin.company_id}/connections/{conn['id']}/sync").json()["run"]
    assert run["status"] == "success" and run["stats"]["verified"] == 1
    session = fake_imap.instances[-1]
    assert session.readonly is True and session.fetched == ["(BODY.PEEK[])"] and session.stored == []


def test_imap_marks_seen_only_with_permission(admin, fake_imap):
    conn = connect(
        admin,
        "imap",
        settings=IMAP,
        secrets={"password": "bon-mot-de-passe"},
        permissions=["read_attachments", "mark_seen"],
    ).json()
    admin.post(f"/api/companies/{admin.company_id}/connections/{conn['id']}/sync")
    session = fake_imap.instances[-1]
    assert session.readonly is False and session.stored and "Seen" in session.stored[0][-1]


def test_secret_is_encrypted_and_never_returned(admin, fake_imap):
    conn = connect(admin, "imap", settings=IMAP, secrets={"password": "bon-mot-de-passe"}).json()
    assert conn["secrets_set"] == ["password"] and "bon-mot-de-passe" not in json.dumps(conn)
    listed = admin.get(f"/api/companies/{admin.company_id}/connections").json()
    assert "bon-mot-de-passe" not in json.dumps(listed)
    with engine.connect() as db:
        raw = db.execute(text("SELECT secret FROM connections")).scalar()
    assert b"bon-mot-de-passe" not in bytes(raw)
    assert "bon-mot-de-passe" not in json.dumps(admin.get("/api/audit").json())


# --- Qonto ------------------------------------------------------------------------------------


class QontoApi:
    """Réponses au format documenté de l'API Qonto v2."""

    def __init__(self, key="org-slug-1234:secret-ok"):
        self.key, self.requests = key, []
        self.transactions = [
            {
                "transaction_id": f"tx-{i}",
                "amount": amount,
                "amount_cents": int(amount * 100),
                "side": side,
                "operation_type": "transfer",
                "currency": "EUR",
                "label": label,
                "reference": ref,
                "settled_at": f"2026-10-{i + 1:02d}T10:00:00.000Z",
                "emitted_at": f"2026-10-{i + 1:02d}T09:00:00.000Z",
                "status": "completed",
            }
            for i, (amount, side, label, ref) in enumerate(
                [
                    (1812.05, "credit", "REMISE CB", None),
                    (5912.40, "debit", "URSSAF RHONE-ALPES", "PRLV 10/2026"),
                    (3800.00, "debit", "SCI LES TILLEULS", "LOYER"),
                    (250.00, "credit", "ATELIER MOREL", "BT-2026-009"),
                ]
            )
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != self.key:
            return httpx.Response(401, json={"errors": [{"code": "unauthorized"}]})
        if request.url.path == "/v2/organization":
            return httpx.Response(
                200,
                json={
                    "organization": {
                        "slug": "org-slug",
                        "bank_accounts": [
                            {
                                "slug": "org-slug-bank-account-1",
                                "iban": "FR7616958000017534825738541",
                                "name": "Compte principal",
                                "balance": 21450.75,
                                "currency": "EUR",
                                "main": True,
                            }
                        ],
                    }
                },
            )
        page = int(request.url.params.get("current_page", 1))
        chunk = self.transactions[(page - 1) * 2 : page * 2]
        return httpx.Response(
            200,
            json={
                "transactions": chunk,
                "meta": {
                    "current_page": page,
                    "next_page": page + 1 if page < 2 else None,
                    "total_pages": 2,
                    "per_page": 2,
                },
            },
        )


@pytest.fixture
def qonto(monkeypatch):
    api = QontoApi()
    monkeypatch.setattr(CONNECTORS["qonto"], "transport", httpx.MockTransport(api))
    return api


def test_qonto_sync_reads_transactions_and_balance(admin, qonto):
    admin.put(f"/api/companies/{admin.company_id}/modules", json={"modules": ["finance", "documents"]})
    conn = connect(admin, "qonto", settings={"login": "org-slug-1234"}, secrets={"secret_key": "secret-ok"}).json()
    assert "Compte principal" in conn["test_message"]
    url = f"/api/companies/{admin.company_id}/connections/{conn['id']}"
    run = admin.post(f"{url}/sync").json()["run"]
    assert run["status"] == "success" and run["stats"]["transactions"] == 4
    tx_requests = [r for r in qonto.requests if r.url.path == "/v2/transactions"]
    assert [r.url.params["current_page"] for r in tx_requests] == ["1", "2"]
    assert all(r.method == "GET" for r in qonto.requests)  # lecture seule
    txs = admin.get(f"/api/companies/{admin.company_id}/bank-transactions").json()["items"]
    by_label = {t["label"]: t for t in txs}
    assert by_label["URSSAF RHONE-ALPES PRLV 10/2026"]["amount"] == -5912.40
    assert by_label["URSSAF RHONE-ALPES PRLV 10/2026"]["category"] == "charges_sociales"
    # Le solde reconstitué de la dernière opération est le solde actuel du compte.
    assert by_label["ATELIER MOREL BT-2026-009"]["balance"] == 21450.75
    assert admin.get(f"/api/companies/{admin.company_id}/finance/treasury").json()["balance"] == 21450.75
    again = admin.post(f"{url}/sync").json()["run"]
    assert again["stats"]["transactions"] == 0


def test_qonto_revoked_key_marks_connection_expired(admin, qonto):
    conn = connect(admin, "qonto", settings={"login": "org-slug-1234"}, secrets={"secret_key": "secret-ok"}).json()
    qonto.key = "org-slug-1234:nouvelle-cle"
    run = admin.post(f"/api/companies/{admin.company_id}/connections/{conn['id']}/sync").json()
    assert run["run"]["status"] == "failed" and run["connection"]["status"] == "expired"
    assert "révoquée" in run["connection"]["last_error"]


def test_offline_mode_disables_online_connectors(admin, qonto, depot, monkeypatch):
    monkeypatch.setenv("BAB_OFFLINE_MODE", "true")
    get_settings.cache_clear()
    try:
        assert admin.get("/api/connectors").json()["offline_mode"] is True
        r = connect(admin, "qonto", settings={"login": "org-slug-1234"}, secrets={"secret_key": "secret-ok"})
        assert r.status_code == 409
        assert qonto.requests == []  # aucune requête n'est partie
        assert connect(admin, "folder", settings={"path": "scanner"}).status_code == 201
    finally:
        get_settings.cache_clear()


def test_concurrent_sync_is_refused(admin, depot):
    conn = connect(admin, "folder", settings={"path": "scanner"}).json()
    from app.connectors.sync import _lock_key

    with SessionLocal() as other:
        connection = other.get(Connection, conn["id"])
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _lock_key(connection)}).scalar()
        try:
            r = admin.post(f"/api/companies/{admin.company_id}/connections/{conn['id']}/sync")
            assert r.status_code == 409
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _lock_key(connection)})


def test_a_crashing_connector_does_not_affect_others(admin, depot, monkeypatch, qonto):
    folder = connect(admin, "folder", settings={"path": "scanner"}).json()
    bank = connect(admin, "qonto", settings={"login": "org-slug-1234"}, secrets={"secret_key": "secret-ok"}).json()

    def boom(self, ctx):
        raise RuntimeError("bogue interne du connecteur")

    monkeypatch.setattr(type(CONNECTORS["folder"]), "sync", boom)
    crashed = admin.post(f"/api/companies/{admin.company_id}/connections/{folder['id']}/sync").json()
    assert crashed["connection"]["status"] == "error" and "bogue" not in crashed["connection"]["last_error"]
    ok = admin.post(f"/api/companies/{admin.company_id}/connections/{bank['id']}/sync").json()
    assert ok["run"]["status"] == "success"
    assert admin.get("/api/health").status_code == 200


def test_scheduler_picks_due_connections(admin, depot):
    from datetime import UTC, datetime, timedelta

    from app.connectors.scheduler import due_connections, tick

    connect(admin, "folder", settings={"path": "scanner"})
    with SessionLocal() as db:
        assert len(due_connections(db, datetime.now(UTC))) == 1
    tick()
    with SessionLocal() as db:
        assert due_connections(db, datetime.now(UTC)) == []
        assert due_connections(db, datetime.now(UTC) + timedelta(minutes=61))
        assert db.scalar(select(Connection.last_sync_at)) is not None


def test_pause_and_permissions_update_are_audited(admin, depot):
    conn = connect(admin, "folder", settings={"path": "scanner"}).json()
    url = f"/api/companies/{admin.company_id}/connections/{conn['id']}"
    assert admin.patch(url, json={"paused": True}).json()["status"] == "paused"
    assert admin.post(f"{url}/sync").status_code == 409
    assert admin.patch(url, json={"permissions": ["read_files", "inconnue"]}).status_code == 422
    assert admin.patch(url, json={"paused": False, "permissions": ["read_files", "move_processed"]}).json()[
        "permissions"
    ] == ["move_processed", "read_files"]
    assert admin.get("/api/audit").json()["items"][0]["action"] == "connector.update"
    assert admin.delete(url).status_code == 204
