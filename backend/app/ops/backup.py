"""Sauvegardes chiffrées et restauration.

Chiffrement asymétrique : le boîtier ne connaît que la clé publique. Il peut donc produire
des sauvegardes sans pouvoir les relire. Seule la clé de récupération (clé privée), remise
au dirigeant à la création et conservée hors du boîtier, permet de restaurer. Un support de
sauvegarde volé avec le boîtier reste illisible.

Format d'un fichier .babk :
  « BABK1 » | clé publique éphémère X25519 (32 octets) | blocs
  bloc = longueur (4 octets) | nonce (12 octets) | données chiffrées AES-256-GCM
  Les données authentifiées de chaque bloc contiennent son rang et un indicateur de fin :
  un fichier tronqué, réordonné ou modifié est rejeté.
Contenu (archive tar) : manifest.json, database.dump (pg_dump), data/ (documents, clés).
"""

import base64
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy.engine import make_url

from app import __version__
from app.config import get_settings

MAGIC = b"BABK1"
CHUNK = 1024 * 1024
SUFFIX = ".babk"
# Fichiers de données sauvegardés (relatifs au dossier de données).
DATA_ITEMS = ("documents", "virements", "secret.key")


class BackupError(Exception):
    pass


# --- Clés --------------------------------------------------------------------------------------


def data_dir() -> Path:
    return Path(get_settings().data_dir).resolve()


def public_key_path() -> Path:
    return data_dir() / "backup.pub"


def backup_dir() -> Path:
    configured = get_settings().backup_dir
    return Path(configured).resolve() if configured else data_dir() / "sauvegardes"


def is_distinct_medium() -> bool:
    """Le dossier de sauvegarde est-il sur un autre système de fichiers que les données ?"""
    target = backup_dir()
    probe = target if target.exists() else target.parent
    try:
        return os.stat(probe).st_dev != os.stat(data_dir()).st_dev
    except FileNotFoundError:
        return False


def format_recovery_key(raw: bytes) -> str:
    text = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(text[i : i + 4] for i in range(0, len(text), 4))


def parse_recovery_key(text: str) -> X25519PrivateKey:
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum())
    try:
        raw = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
        if len(raw) != 32:
            raise ValueError
        return X25519PrivateKey.from_private_bytes(raw)
    except ValueError as exc:
        raise BackupError("Clé de récupération illisible : vérifiez la saisie.") from exc


def create_recovery_key() -> str:
    """Génère la paire de clés ; renvoie la clé de récupération, à remettre au dirigeant."""
    private = X25519PrivateKey.generate()
    raw_private = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    path = public_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(base64.b64encode(public).decode())
    return format_recovery_key(raw_private)


def load_public_key() -> X25519PublicKey | None:
    path = public_key_path()
    if not path.exists():
        return None
    return X25519PublicKey.from_public_bytes(base64.b64decode(path.read_text()))


def key_fingerprint(public: X25519PublicKey) -> str:
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def _derive(shared: bytes, ephemeral_public: bytes) -> bytes:
    return HKDF(SHA256(), 32, salt=ephemeral_public, info=b"business-ai-box backup v1").derive(shared)


# --- Chiffrement en flux ---------------------------------------------------------------------


def encrypt_file(source: Path, target: Path, public: X25519PublicKey) -> None:
    ephemeral = X25519PrivateKey.generate()
    eph_pub = ephemeral.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aead = AESGCM(_derive(ephemeral.exchange(public), eph_pub))
    header = MAGIC + eph_pub
    size = source.stat().st_size
    with source.open("rb") as src, target.open("wb") as out:
        out.write(header)
        index, done = 0, 0
        while True:
            block = src.read(CHUNK)
            done += len(block)
            last = done >= size
            nonce = os.urandom(12)
            sealed = aead.encrypt(nonce, block, header + struct.pack(">I?", index, last))
            out.write(struct.pack(">I", len(sealed)) + nonce + sealed)
            index += 1
            if last:
                break


def decrypt_file(source: Path, target: Path, private: X25519PrivateKey) -> None:
    with source.open("rb") as src, target.open("wb") as out:
        header = src.read(len(MAGIC) + 32)
        if not header.startswith(MAGIC) or len(header) != len(MAGIC) + 32:
            raise BackupError("Ce fichier n'est pas une sauvegarde Business AI Box.")
        eph_pub = header[len(MAGIC) :]
        try:
            shared = private.exchange(X25519PublicKey.from_public_bytes(eph_pub))
        except ValueError as exc:
            raise BackupError("Sauvegarde endommagée.") from exc
        aead = AESGCM(_derive(shared, eph_pub))
        index = 0
        while True:
            raw_len = src.read(4)
            if len(raw_len) < 4:
                raise BackupError("Sauvegarde incomplète : le fichier a été tronqué.")
            (length,) = struct.unpack(">I", raw_len)
            nonce, sealed = src.read(12), src.read(length)
            for last in (False, True):
                try:
                    block = aead.decrypt(nonce, sealed, header + struct.pack(">I?", index, last))
                    break
                except InvalidTag:  # on essaie l'autre indicateur de fin
                    block = None
            if block is None:
                raise BackupError("Clé de récupération incorrecte, ou sauvegarde modifiée.")
            out.write(block)
            index += 1
            if last:
                if src.read(1):
                    raise BackupError("Données inattendues après la fin de la sauvegarde.")
                return


# --- Base de données ---------------------------------------------------------------------------


def _pg_env() -> tuple[list[str], dict[str, str]]:
    url = make_url(get_settings().database_url)
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    args = [
        "-h",
        url.host or "localhost",
        "-p",
        str(url.port or 5432),
        "-U",
        url.username or "",
        "-d",
        url.database or "",
    ]
    return args, env


def _run(cmd: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise BackupError(f"{cmd[0]} a échoué : {result.stderr.strip()[-500:]}")


# --- Sauvegarde ------------------------------------------------------------------------------


@dataclass
class BackupInfo:
    name: str
    path: Path
    created_at: str
    size: int
    version: str
    key_fingerprint: str
    sha256: str
    stats: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "created_at": self.created_at, "size": self.size, "version": self.version,
                "key_fingerprint": self.key_fingerprint, "sha256": self.sha256, "stats": self.stats}  # fmt: skip


def create_backup(reason: str = "manual") -> BackupInfo:
    public = load_public_key()
    if public is None:
        raise BackupError("Aucune clé de sauvegarde : créez d'abord la clé de récupération.")
    target_dir = backup_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"business-ai-box-{stamp}{SUFFIX}"
    with tempfile.TemporaryDirectory(dir=data_dir()) as tmp:
        tmp_path = Path(tmp)
        dump = tmp_path / "database.dump"
        args, env = _pg_env()
        _run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", *args, "-f", str(dump)], env)
        files, total = 0, 0
        archive = tmp_path / "archive.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(dump, arcname="database.dump")
            for item in DATA_ITEMS:
                source = data_dir() / item
                if source.exists():
                    tar.add(source, arcname=f"data/{item}")
                    for p in [source] if source.is_file() else source.rglob("*"):
                        if p.is_file():
                            files += 1
                            total += p.stat().st_size
            manifest = {
                "format": 1, "version": __version__, "created_at": datetime.now(UTC).isoformat(), "reason": reason,
                "database_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(), "files": files, "files_bytes": total,
            }  # fmt: skip
            data = json.dumps(manifest, indent=1).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        partial = target_dir / (name + ".partiel")
        encrypt_file(archive, partial, public)
        partial.replace(target_dir / name)  # n'apparaît qu'une fois complète
    path = target_dir / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    meta = {
        "created_at": manifest["created_at"], "size": path.stat().st_size, "version": __version__, "reason": reason,
        "key_fingerprint": key_fingerprint(public), "sha256": digest,
        "stats": {"files": files, "files_bytes": total},
    }  # fmt: skip
    (target_dir / (name + ".json")).write_text(json.dumps(meta, indent=1))
    prune()
    return BackupInfo(
        name, path, meta["created_at"], meta["size"], __version__, meta["key_fingerprint"], digest, meta["stats"]
    )


def list_backups() -> list[BackupInfo]:
    out = []
    for path in sorted(backup_dir().glob(f"*{SUFFIX}"), reverse=True):
        meta_path = path.with_name(path.name + ".json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        out.append(BackupInfo(path.name, path, meta.get("created_at", ""), path.stat().st_size, meta.get("version", "?"),
                              meta.get("key_fingerprint", "?"), meta.get("sha256", ""), meta.get("stats", {})))  # fmt: skip
    return out


def prune() -> list[str]:
    """Conserve les N sauvegardes les plus récentes."""
    removed = []
    for info in list_backups()[get_settings().backup_keep :]:
        info.path.unlink(missing_ok=True)
        info.path.with_name(info.name + ".json").unlink(missing_ok=True)
        removed.append(info.name)
    return removed


def _open(path: Path, recovery_key: str, workdir: Path) -> dict[str, Any]:
    if not path.exists():
        raise BackupError("Sauvegarde introuvable.")
    archive = workdir / "archive.tar"
    decrypt_file(path, archive, parse_recovery_key(recovery_key))
    with tarfile.open(archive) as tar:
        tar.extractall(workdir / "contenu", filter="data")
    content = workdir / "contenu"
    manifest = json.loads((content / "manifest.json").read_text())
    if hashlib.sha256((content / "database.dump").read_bytes()).hexdigest() != manifest["database_sha256"]:
        raise BackupError("La base de données contenue dans la sauvegarde est altérée.")
    return manifest


def verify_backup(path: Path, recovery_key: str) -> dict[str, Any]:
    """Déchiffre et contrôle une sauvegarde, sans rien restaurer."""
    with tempfile.TemporaryDirectory(dir=data_dir()) as tmp:
        manifest = _open(path, recovery_key, Path(tmp))
        args, env = _pg_env()
        # pg_restore --list lit tout l'index du fichier : un vidage illisible est détecté.
        _run(["pg_restore", "--list", str(Path(tmp) / "contenu" / "database.dump")], env)
        return manifest


def restore_backup(path: Path, recovery_key: str) -> dict[str, Any]:
    """Remplace la base et les documents par le contenu de la sauvegarde."""
    with tempfile.TemporaryDirectory(dir=data_dir()) as tmp:
        manifest = _open(path, recovery_key, Path(tmp))
        content = Path(tmp) / "contenu"
        args, env = _pg_env()
        _run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction",
              *args, str(content / "database.dump")], env)  # fmt: skip
        for item in DATA_ITEMS:
            source, target = content / "data" / item, data_dir() / item
            if not source.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            shutil.move(str(source), str(target))
        return manifest


STATUS_FILE = "backup-status.json"


def record_status(ok: bool, message: str) -> None:
    path = data_dir() / STATUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": ok, "message": message, "at": datetime.now(UTC).isoformat()}))


def last_status() -> dict[str, Any] | None:
    path = data_dir() / STATUS_FILE
    return json.loads(path.read_text()) if path.exists() else None


def scheduled_backup() -> None:
    if load_public_key() is None:
        return
    try:
        info = create_backup("schedule")
        record_status(True, f"Sauvegarde {info.name} créée.")
    except Exception as exc:  # noqa: BLE001 - tout échec doit apparaître dans la page Système
        record_status(False, str(exc)[:500])
