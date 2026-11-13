import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__, audit
from app.ai.llm import get_llm
from app.config import get_settings
from app.connectors import scheduler
from app.db import get_db
from app.deps import Auth, get_admin
from app.models import Action, Connection, Document
from app.ops import backup, updates

router = APIRouter(prefix="/system", tags=["système"])


def _size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


@router.get("/status")
def system_status(_: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    settings = get_settings()
    data = backup.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(data)
    public = backup.load_public_key()
    backups = backup.list_backups()
    llm = get_llm()
    warnings = []
    if public is None:
        warnings.append("Aucune sauvegarde configurée : créez la clé de récupération.")
    elif not backup.is_distinct_medium():
        warnings.append(
            "Les sauvegardes sont sur le même disque que les données : branchez un support distinct (disque USB, NAS)."
        )
    last_status = backup.last_status()
    if last_status and not last_status["ok"]:
        warnings.append(f"Dernière sauvegarde automatique en échec : {last_status['message']}")
    if disk.free / disk.total < 0.1:
        warnings.append("Moins de 10 % d'espace disque libre.")
    errors = db.scalar(select(func.count()).select_from(Connection).where(Connection.status.in_(("error", "expired"))))
    if errors:
        warnings.append(f"{errors} connexion(s) de logiciel en erreur.")
    next_run = scheduler.next_backup()
    return {
        "version": __version__,
        "database_revision": db.scalar(text("SELECT version_num FROM alembic_version")),
        "offline_mode": settings.offline_mode,
        "scheduler_running": scheduler.running(),
        "ai": {"enabled": settings.ai_enabled, "model": settings.ai_model, "available": bool(llm and llm.available())},
        "smtp_configured": bool(settings.smtp_host) and not settings.offline_mode,
        "disk": {"total": disk.total, "free": disk.free, "used": disk.used},
        "database_bytes": db.scalar(text("SELECT pg_database_size(current_database())")),
        "documents": {
            "count": db.scalar(select(func.count()).select_from(Document)),
            "bytes": _size(data / "documents"),
        },
        "pending_actions": db.scalar(select(func.count()).select_from(Action).where(Action.status == "pending")),
        "backup": {
            "configured": public is not None,
            "key_fingerprint": backup.key_fingerprint(public) if public else None,
            "directory": str(backup.backup_dir()),
            "distinct_medium": backup.is_distinct_medium(),
            "keep": settings.backup_keep,
            "count": len(backups),
            "last": backups[0].as_dict() if backups else None,
            "last_automatic": last_status,
            "next_run": next_run.isoformat() if next_run else None,
        },
        "update_keys": len(updates.trusted_keys()),
        "warnings": warnings,
    }


@router.post("/backup-key", status_code=status.HTTP_201_CREATED)
def create_backup_key(request: Request, auth: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    """Crée la clé de récupération. Elle n'est montrée qu'une fois et n'est pas conservée sur le boîtier."""
    if backup.public_key_path().exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Une clé de sauvegarde existe déjà.")
    key = backup.create_recovery_key()
    audit.record(
        db,
        request,
        "system.backup_key",
        actor=auth.user,
        details={"fingerprint": backup.key_fingerprint(backup.load_public_key())},
    )
    db.commit()
    return {"recovery_key": key, "fingerprint": backup.key_fingerprint(backup.load_public_key())}


@router.get("/backups")
def list_backups(_: Auth = Depends(get_admin)):
    return [b.as_dict() for b in backup.list_backups()]


@router.post("/backups", status_code=status.HTTP_201_CREATED)
def backup_now(request: Request, auth: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    try:
        info = backup.create_backup("manual")
    except backup.BackupError as exc:
        audit.record(db, request, "system.backup", actor=auth.user, outcome="failure", details={"error": str(exc)})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    backup.record_status(True, f"Sauvegarde {info.name} créée.")
    audit.record(db, request, "system.backup", actor=auth.user, target=info.name, details={"size": info.size})
    db.commit()
    return info.as_dict()


def _path(name: str) -> Path:
    path = backup.backup_dir() / name
    if not name.endswith(backup.SUFFIX) or "/" in name or "\\" in name or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sauvegarde introuvable.")
    return path


class VerifyIn(BaseModel):
    recovery_key: Annotated[str, Field(min_length=20, max_length=200)]


@router.post("/backups/{name}/verify")
def verify(name: str, body: VerifyIn, request: Request, auth: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    """Contrôle complet d'une sauvegarde (déchiffrement, empreintes, lecture du vidage), sans restauration."""
    try:
        manifest = backup.verify_backup(_path(name), body.recovery_key)
    except backup.BackupError as exc:
        audit.record(
            db,
            request,
            "system.backup_verify",
            actor=auth.user,
            outcome="failure",
            target=name,
            details={"error": str(exc)},
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    audit.record(db, request, "system.backup_verify", actor=auth.user, target=name)
    db.commit()
    return {"ok": True, "manifest": manifest}


@router.get("/backups/{name}/download")
def download(name: str, request: Request, auth: Auth = Depends(get_admin), db: Session = Depends(get_db)):
    path = _path(name)
    audit.record(db, request, "system.backup_download", actor=auth.user, target=name)
    db.commit()
    return FileResponse(path, media_type="application/octet-stream", filename=name)
