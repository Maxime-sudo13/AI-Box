"""Chiffrement des identifiants des connecteurs (AES-256-GCM).

La clé vient de BAB_SECRET_KEY ou, à défaut, d'un fichier généré une fois dans le dossier de
données (droits 0600). Une copie de la base seule ne permet donc pas de lire les secrets.
"""

import base64
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION = b"\x01"


@lru_cache
def _key() -> bytes:
    settings = get_settings()
    if settings.secret_key:
        key = base64.b64decode(settings.secret_key)
    else:
        path = Path(settings.data_dir).resolve() / "secret.key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64encode(secrets.token_bytes(32)))
        key = base64.b64decode(path.read_bytes())
    if len(key) != 32:
        raise RuntimeError("La clé de chiffrement doit faire 32 octets.")
    return key


def encrypt(data: dict[str, Any]) -> bytes:
    nonce = secrets.token_bytes(12)
    return _VERSION + nonce + AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), _VERSION)


def decrypt(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        return {}
    if blob[:1] != _VERSION:
        raise ValueError("Format de secret inconnu.")
    return json.loads(AESGCM(_key()).decrypt(blob[1:13], blob[13:], _VERSION))


def reset_key_cache() -> None:
    _key.cache_clear()
