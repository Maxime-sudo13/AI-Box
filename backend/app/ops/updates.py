"""Mises à jour signées, importées et vérifiées hors ligne.

Un paquet de mise à jour (.babmaj) est une archive tar contenant :
  manifest.json      version, date, liste des fichiers avec leur empreinte SHA-256
  manifest.sig       signature Ed25519 de manifest.json par la clé de l'éditeur
  fichiers…          images Docker (docker save), fichiers de déploiement
Le boîtier n'accepte un paquet que si la signature correspond à une clé de l'éditeur
qu'il connaît, si chaque fichier a l'empreinte annoncée, et si la version est plus récente.
Aucune donnée de l'entreprise n'est envoyée à l'éditeur : le paquet arrive sur clé USB ou
est téléchargé, puis vérifié sur place.
"""

import base64
import hashlib
import io
import json
import re
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app import __version__

KEYS_DIR = Path(__file__).parent / "cles_editeur"


class UpdateError(Exception):
    pass


def version_tuple(v: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(\.\d+){1,3}", v):
        raise UpdateError(f"Numéro de version invalide : {v}")
    return tuple(int(x) for x in v.split("."))


def generate_publisher_key() -> tuple[str, str]:
    """Paire de clés de l'éditeur : (clé privée PEM, à garder hors ligne ; clé publique)."""
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem.decode(), base64.b64encode(public).decode()


def trusted_keys(directory: Path | None = None) -> dict[str, Ed25519PublicKey]:
    keys = {}
    for path in sorted((directory or KEYS_DIR).glob("*.pub")):
        keys[path.stem] = Ed25519PublicKey.from_public_bytes(base64.b64decode(path.read_text().strip()))
    return keys


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_package(version: str, files: list[Path], private_pem: str, output: Path, notes: str = "") -> Path:
    version_tuple(version)
    private = serialization.load_pem_private_key(private_pem.encode(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise UpdateError("La clé de signature doit être une clé Ed25519.")
    manifest = {
        "format": 1, "version": version, "created_at": datetime.now(UTC).isoformat(), "notes": notes,
        "files": [{"name": f.name, "size": f.stat().st_size, "sha256": _sha256(f)} for f in files],
    }  # fmt: skip
    data = json.dumps(manifest, indent=1, ensure_ascii=False).encode()
    signature = base64.b64encode(private.sign(data))
    with tarfile.open(output, "w") as tar:
        for name, payload in (("manifest.json", data), ("manifest.sig", signature)):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        for f in files:
            tar.add(f, arcname=f.name)
    return output


def verify_package(path: Path, *, extract_to: Path | None = None, current: str = __version__,
                   allow_downgrade: bool = False, keys_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    keys = trusted_keys(keys_dir)
    if not keys:
        raise UpdateError("Aucune clé d'éditeur installée sur ce boîtier.")
    try:
        tar = tarfile.open(path)
    except (tarfile.TarError, OSError) as exc:
        raise UpdateError("Fichier illisible : ce n'est pas un paquet de mise à jour.") from exc
    with tar:
        names = tar.getnames()
        if "manifest.json" not in names or "manifest.sig" not in names:
            raise UpdateError("Paquet incomplet : manifeste ou signature absent.")
        data = tar.extractfile("manifest.json").read()
        signature = base64.b64decode(tar.extractfile("manifest.sig").read())
        signer = None
        for key_name, key in keys.items():
            try:
                key.verify(signature, data)
                signer = key_name
                break
            except InvalidSignature:
                continue
        if signer is None:
            raise UpdateError("Signature invalide : ce paquet ne provient pas de l'éditeur, ou a été modifié.")
        manifest = json.loads(data)
        if version_tuple(manifest["version"]) <= version_tuple(current) and not allow_downgrade:
            raise UpdateError(f"Version {manifest['version']} non plus récente que la version installée ({current}).")
        expected = {f["name"]: f for f in manifest["files"]}
        payload = [m for m in tar.getmembers() if m.name not in ("manifest.json", "manifest.sig")]
        if {m.name for m in payload} != set(expected) or any(not m.isfile() or "/" in m.name for m in payload):
            raise UpdateError("Le contenu du paquet ne correspond pas à son manifeste.")
        for member in payload:
            h = hashlib.sha256()
            stream = tar.extractfile(member)
            out = (extract_to / member.name).open("wb") if extract_to else None
            try:
                for block in iter(lambda s=stream: s.read(1024 * 1024), b""):
                    h.update(block)
                    if out:
                        out.write(block)
            finally:
                if out:
                    out.close()
            if h.hexdigest() != expected[member.name]["sha256"]:
                if extract_to:
                    (extract_to / member.name).unlink(missing_ok=True)
                raise UpdateError(f"Le fichier {member.name} a été modifié : empreinte incorrecte.")
    return {**manifest, "signer": signer}
