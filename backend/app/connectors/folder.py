"""Dossier surveillé : les fichiers déposés (scanner, partage réseau, export comptable) sont
importés automatiquement. Fonctionne sans Internet."""

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

from app.config import get_settings

from .base import (
    Connector,
    ConnectorError,
    DocumentRecord,
    Permission,
    SettingField,
    SyncContext,
    SyncResult,
    TableRecord,
)

DOCUMENT_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
TABLE_EXT = {".csv"}
PROCESSED = "importes"
MAX_FILES = 500
MAX_BYTES = 25 * 1024 * 1024


def import_root() -> Path:
    settings = get_settings()
    return Path(settings.import_root or Path(settings.data_dir) / "depot").resolve()


def resolve_folder(raw: str) -> Path:
    """Dossier demandé, obligatoirement à l'intérieur de la racine autorisée."""
    root = import_root()
    candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise ConnectorError(f"Le dossier doit se trouver dans {root} (racine des dépôts du boîtier).")
    if not candidate.is_dir():
        raise ConnectorError("Dossier introuvable.")
    return candidate


class FolderConnector(Connector):
    key = "folder"
    name = "Dossier surveillé"
    category = "Documents"
    description = "Importe automatiquement les factures (PDF, photos) et exports CSV déposés dans un dossier partagé."
    online = False
    fields = (
        SettingField(
            "path", "Dossier", hint="Chemin relatif à la racine des dépôts du boîtier, par exemple « scanner »."
        ),
    )
    permissions = (
        Permission("read_files", "Lire les fichiers déposés", default=True),
        Permission("move_processed", f"Déplacer les fichiers importés dans « {PROCESSED} »", write=True),
    )
    data_notice = "Les fichiers restent sur le réseau de l'entreprise ; une copie est conservée sur le boîtier."

    def test(self, settings: dict[str, Any], secrets: dict[str, Any]) -> str:
        folder = resolve_folder(settings.get("path", ""))
        count = sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DOCUMENT_EXT | TABLE_EXT)
        return f"Dossier accessible : {count} fichier(s) importable(s)."

    def sync(self, ctx: SyncContext) -> SyncResult:
        if not ctx.allowed("read_files"):
            raise ConnectorError("La lecture des fichiers n'est pas autorisée pour cette connexion.")
        folder = resolve_folder(ctx.settings.get("path", ""))
        result = SyncResult()
        paths: dict[str, Path] = {}
        now = time.time()
        for path in sorted(folder.iterdir())[:MAX_FILES]:
            ext = path.suffix.lower()
            if not path.is_file() or ext not in DOCUMENT_EXT | TABLE_EXT:
                continue
            stat = path.stat()
            if now - stat.st_mtime < 10:
                continue  # fichier peut-être encore en cours d'écriture par le scanner
            if stat.st_size > MAX_BYTES:
                result.notes.append(f"{path.name} ignoré : plus de 25 Mo.")
                continue
            external_id = hashlib.sha256(f"{path.name}|{stat.st_size}|{int(stat.st_mtime)}".encode()).hexdigest()
            paths[external_id] = path
            if ctx.seen(external_id):
                continue
            record_cls = TableRecord if ext in TABLE_EXT else DocumentRecord
            target = result.tables if ext in TABLE_EXT else result.documents
            target.append(record_cls(external_id, path.name, path.read_bytes()))

        def finalize(done: set[str]) -> None:
            if not ctx.allowed("move_processed"):
                return
            destination = folder / PROCESSED
            destination.mkdir(exist_ok=True)
            for external_id in done:
                path = paths.get(external_id)
                if path and path.exists():
                    shutil.move(str(path), destination / path.name)

        result.finalize = finalize
        return result
