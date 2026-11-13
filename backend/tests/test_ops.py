"""Exploitation : sauvegardes chiffrées, restauration, mises à jour signées."""

import io
import os
import shutil
import tarfile

import pytest

from app.db import engine
from app.ops import backup, updates
from tests.conftest import PASSWORD


@pytest.fixture(autouse=True)
def clean_backup_state(data_dir):
    for path in (backup.public_key_path(), backup.data_dir() / backup.STATUS_FILE):
        path.unlink(missing_ok=True)
    shutil.rmtree(backup.backup_dir(), ignore_errors=True)
    yield


# --- Chiffrement -------------------------------------------------------------------------------


def test_recovery_key_roundtrip_and_encryption(tmp_path):
    key = backup.create_recovery_key()
    assert len(key.split("-")) == 13 and backup.parse_recovery_key(key.lower().replace("-", " "))
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(2 * backup.CHUNK + 1234))  # plusieurs blocs
    sealed, opened = tmp_path / "s.babk", tmp_path / "o.bin"
    backup.encrypt_file(source, sealed, backup.load_public_key())
    backup.decrypt_file(sealed, opened, backup.parse_recovery_key(key))
    assert opened.read_bytes() == source.read_bytes()

    other = backup.parse_recovery_key(backup.format_recovery_key(os.urandom(32)))
    with pytest.raises(backup.BackupError, match="incorrecte"):
        backup.decrypt_file(sealed, opened, other)
    tampered = bytearray(sealed.read_bytes())
    tampered[len(tampered) // 2] ^= 1
    (tmp_path / "t.babk").write_bytes(tampered)
    with pytest.raises(backup.BackupError):
        backup.decrypt_file(tmp_path / "t.babk", opened, backup.parse_recovery_key(key))
    (tmp_path / "c.babk").write_bytes(sealed.read_bytes()[: -(backup.CHUNK // 2)])
    with pytest.raises(backup.BackupError):
        backup.decrypt_file(tmp_path / "c.babk", opened, backup.parse_recovery_key(key))


# --- Sauvegarde et restauration -------------------------------------------------------------------


def test_backup_restore_full_cycle(admin, make_user, demo_files):
    base = f"/api/companies/{admin.company_id}"
    for pdf in sorted((demo_files / "factures").glob("*Primeurs*.pdf"))[:2]:
        assert admin.post(f"{base}/documents", files={"file": (pdf.name, pdf.read_bytes())}).status_code == 201

    status = admin.get("/api/system/status").json()
    assert status["backup"]["configured"] is False and status["warnings"]
    created = admin.post("/api/system/backup-key")
    assert created.status_code == 201
    key = created.json()["recovery_key"]
    assert admin.post("/api/system/backup-key").status_code == 409  # jamais remplacée par mégarde

    made = admin.post("/api/system/backups").json()
    listed = admin.get("/api/system/backups").json()
    assert [b["name"] for b in listed] == [made["name"]] and made["stats"]["files"] >= 2
    raw = (backup.backup_dir() / made["name"]).read_bytes()
    assert b"Primeurs" not in raw and b"%PDF" not in raw  # contenu chiffré

    assert admin.post(f"/api/system/backups/{made['name']}/verify", json={"recovery_key": key}).json()["ok"] is True
    bad = admin.post(f"/api/system/backups/{made['name']}/verify",
                     json={"recovery_key": backup.format_recovery_key(os.urandom(32))})  # fmt: skip
    assert bad.status_code == 422

    # Sinistre : un document supprimé du disque, un compte ajouté, une entreprise créée.
    shutil.rmtree(backup.data_dir() / "documents")
    make_user("intrus@exemple.fr")
    admin.post("/api/companies", json={"name": "Après sauvegarde"})

    engine.dispose()
    backup.restore_backup(backup.backup_dir() / made["name"], key)
    engine.dispose()

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert (
        client.post("/api/auth/login", json={"email": "dirigeante@exemple.fr", "password": PASSWORD}).status_code == 200
    )
    assert client.post("/api/auth/login", json={"email": "intrus@exemple.fr", "password": PASSWORD}).status_code == 401
    assert [c["name"] for c in client.get("/api/companies").json()] == ["Atelier Martin"]
    docs = client.get(f"{base}/documents").json()["items"]
    assert len(docs) == 2
    assert client.get(f"{base}/documents/{docs[0]['id']}/file").content.startswith(b"%PDF")


def test_system_endpoints_are_admin_only(admin, make_user):
    owner = make_user("dirigeant@exemple.fr", role="owner")
    for method, path in (
        ("get", "/api/system/status"),
        ("post", "/api/system/backups"),
        ("post", "/api/system/backup-key"),
    ):
        assert getattr(owner, method)(path).status_code == 403


def test_backup_without_key_is_refused_and_retention_applies(admin, monkeypatch):
    assert admin.post("/api/system/backups").status_code == 409
    admin.post("/api/system/backup-key")
    import time

    from app.config import get_settings

    monkeypatch.setenv("BAB_BACKUP_KEEP", "2")
    get_settings.cache_clear()
    try:
        names = []
        for _ in range(3):
            names.append(backup.create_backup().name)
            time.sleep(1.1)
        assert [b.name for b in backup.list_backups()] == names[:0:-1]
    finally:
        monkeypatch.delenv("BAB_BACKUP_KEEP")
        get_settings.cache_clear()


def test_scheduled_backup_records_failures(admin):
    backup.scheduled_backup()  # sans clé : ne fait rien
    assert backup.last_status() is None
    admin.post("/api/system/backup-key")
    backup.scheduled_backup()
    assert backup.last_status()["ok"] is True and len(backup.list_backups()) == 1


# --- Mises à jour signées -------------------------------------------------------------------------


@pytest.fixture
def publisher(tmp_path):
    private, public = updates.generate_publisher_key()
    keys = tmp_path / "cles"
    keys.mkdir()
    (keys / "editeur.pub").write_text(public)
    payload = tmp_path / "business-ai-box-images.tar"
    payload.write_bytes(os.urandom(50_000))
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    return {"private": private, "keys": keys, "files": [payload, compose], "tmp": tmp_path}


def test_signed_package_is_accepted_and_extracted(publisher):
    pkg = updates.build_package(
        "9.0.0", publisher["files"], publisher["private"], publisher["tmp"] / "maj.babmaj", "Notes"
    )
    out = publisher["tmp"] / "extrait"
    out.mkdir()
    manifest = updates.verify_package(pkg, extract_to=out, keys_dir=publisher["keys"])
    assert manifest["version"] == "9.0.0" and manifest["signer"] == "editeur"
    assert (out / "docker-compose.yml").read_text() == "services: {}\n"


def test_tampered_or_foreign_or_old_packages_are_rejected(publisher):
    tmp = publisher["tmp"]
    pkg = updates.build_package("9.0.0", publisher["files"], publisher["private"], tmp / "maj.babmaj")

    # Fichier remplacé dans le paquet (manifeste intact).
    with tarfile.open(pkg) as src, tarfile.open(tmp / "trafique.babmaj", "w") as dst:
        for m in src.getmembers():
            data = src.extractfile(m).read()
            if m.name == "docker-compose.yml":
                data = b"services: {pirate: {image: malveillant}}\n"
                m.size = len(data)
            dst.addfile(m, io.BytesIO(data))
    with pytest.raises(updates.UpdateError, match="modifié"):
        updates.verify_package(tmp / "trafique.babmaj", keys_dir=publisher["keys"])

    # Paquet signé par une autre clé.
    other_private, _ = updates.generate_publisher_key()
    foreign = updates.build_package("9.0.0", publisher["files"], other_private, tmp / "etranger.babmaj")
    with pytest.raises(updates.UpdateError, match="Signature invalide"):
        updates.verify_package(foreign, keys_dir=publisher["keys"])

    # Retour en arrière refusé.
    old = updates.build_package("0.1.0", publisher["files"], publisher["private"], tmp / "ancien.babmaj")
    with pytest.raises(updates.UpdateError, match="non plus récente"):
        updates.verify_package(old, keys_dir=publisher["keys"])

    # Sans clé d'éditeur installée, rien n'est accepté.
    empty = tmp / "vide"
    empty.mkdir()
    with pytest.raises(updates.UpdateError, match="Aucune clé"):
        updates.verify_package(pkg, keys_dir=empty)
