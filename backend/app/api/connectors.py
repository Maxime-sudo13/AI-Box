import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.connectors.base import ConnectorError
from app.connectors.crypto import decrypt, encrypt
from app.connectors.folder import import_root
from app.connectors.registry import CONNECTORS, PLANNED
from app.connectors.sync import SyncBusy, run_sync
from app.db import get_db
from app.deps import Auth, company_access, get_auth, get_company_for
from app.models import Connection, SyncRun

router = APIRouter(tags=["connecteurs"])


@router.get("/connectors")
def catalog(_: Auth = Depends(get_auth)):
    offline = get_settings().offline_mode
    return {
        "offline_mode": offline,
        "import_root": str(import_root()),
        "available": [
            {
                "key": c.key,
                "name": c.name,
                "category": c.category,
                "description": c.description,
                "online": c.online,
                "hosts": list(c.hosts),
                "data_notice": c.data_notice,
                "disabled_reason": "Mode « zéro communication externe » actif." if offline and c.online else None,
                "fields": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "kind": f.kind,
                        "secret": f.secret,
                        "required": f.required,
                        "hint": f.hint,
                        "default": f.default,
                    }
                    for f in c.fields
                ],
                "permissions": [
                    {"key": p.key, "label": p.label, "write": p.write, "default": p.default} for p in c.permissions
                ],
            }
            for c in CONNECTORS.values()
        ],
        "planned": [
            {"key": p.key, "name": p.name, "category": p.category, "description": p.description} for p in PLANNED
        ],
    }


def connection_out(c: Connection, last_run: SyncRun | None = None) -> dict[str, Any]:
    connector = CONNECTORS.get(c.connector)
    secret_keys = sorted(decrypt(c.secret)) if c.secret else []
    return {
        "id": str(c.id),
        "connector": c.connector,
        "connector_name": connector.name if connector else c.connector,
        "category": connector.category if connector else "",
        "label": c.label,
        "status": c.status,
        "settings": c.settings,
        "secrets_set": secret_keys,
        "permissions": c.permissions,
        "interval_minutes": c.interval_minutes,
        "last_sync_at": c.last_sync_at,
        "last_error": c.last_error,
        "created_at": c.created_at,
        "last_run": run_out(last_run) if last_run else None,
    }


def run_out(r: SyncRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "trigger": r.trigger,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "status": r.status,
        "stats": r.stats,
        "error": r.error,
    }


def _manage(db: Session, request: Request, auth: Auth, company_id: uuid.UUID):
    company = company_access(db, request, auth.user, company_id)
    get_company_for(db, request, auth.user, company_id, manage=True)  # dirigeant ou administrateur
    return company


def _get(db: Session, company_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
    c = db.scalar(select(Connection).where(Connection.id == connection_id, Connection.company_id == company_id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connexion introuvable.")
    return c


@router.get("/companies/{company_id}/connections")
def list_connections(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company = company_access(db, request, auth.user, company_id)
    out = []
    for c in db.scalars(select(Connection).where(Connection.company_id == company.id).order_by(Connection.created_at)):
        last = db.scalar(select(SyncRun).where(SyncRun.connection_id == c.id).order_by(SyncRun.id.desc()).limit(1))
        out.append(connection_out(c, last))
    return out


class ConnectionIn(BaseModel):
    connector: str
    label: Annotated[str, Field(max_length=200)] | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    permissions: list[str] | None = None
    interval_minutes: Annotated[int, Field(ge=5, le=1440)] = 60


def _split(connector, values: dict[str, Any], secrets: dict[str, str], *, partial: bool = False) -> tuple[dict, dict]:
    settings, secret = {}, {}
    for f in connector.fields:
        value = secrets.get(f.key) if f.secret else values.get(f.key, f.default)
        if isinstance(value, str):
            value = value.strip()
        if f.required and not value and not partial:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"« {f.label} » est obligatoire.")
        if value not in (None, ""):
            (secret if f.secret else settings)[f.key] = value
    return settings, secret


def _check_permissions(connector, wanted: list[str] | None) -> list[str]:
    known = {p.key for p in connector.permissions}
    if wanted is None:
        return [p.key for p in connector.permissions if p.default]
    unknown = set(wanted) - known
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Permission inconnue pour ce connecteur.")
    return sorted(set(wanted))


@router.post("/companies/{company_id}/connections", status_code=status.HTTP_201_CREATED)
def create_connection(
    company_id: uuid.UUID,
    body: ConnectionIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = _manage(db, request, auth, company_id)
    connector = CONNECTORS.get(body.connector)
    if connector is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connecteur inconnu.")
    if connector.online and get_settings().offline_mode:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Mode « zéro communication externe » actif : ce connecteur en ligne est désactivé.",
        )
    settings, secret = _split(connector, body.settings, body.secrets)
    try:
        message = connector.test(settings, secret)
    except ConnectorError as exc:
        audit.record(
            db,
            request,
            "connector.create",
            actor=auth.user,
            outcome="failure",
            company_id=company.id,
            target=connector.name,
            details={"error": str(exc)},
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Connexion impossible : {exc}") from exc
    connection = Connection(
        company_id=company.id,
        connector=connector.key,
        label=(body.label or connector.name)[:200],
        settings=settings,
        secret=encrypt(secret) if secret else None,
        permissions=_check_permissions(connector, body.permissions),
        interval_minutes=body.interval_minutes,
        created_by_id=auth.user.id,
    )
    db.add(connection)
    db.flush()
    audit.record(
        db,
        request,
        "connector.create",
        actor=auth.user,
        company_id=company.id,
        target=connection.label,
        details={"connector": connector.key, "permissions": connection.permissions},
    )
    db.commit()
    return {**connection_out(connection), "test_message": message}


class ConnectionPatch(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    permissions: list[str] | None = None
    interval_minutes: Annotated[int, Field(ge=5, le=1440)] | None = None
    paused: bool | None = None
    settings: dict[str, Any] | None = None
    secrets: dict[str, str] | None = None


@router.patch("/companies/{company_id}/connections/{connection_id}")
def update_connection(
    company_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: ConnectionPatch,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = _manage(db, request, auth, company_id)
    c = _get(db, company.id, connection_id)
    connector = CONNECTORS[c.connector]
    changes = sorted(body.model_dump(exclude_unset=True))
    if body.label:
        c.label = body.label
    if body.permissions is not None:
        c.permissions = _check_permissions(connector, body.permissions)
    if body.interval_minutes:
        c.interval_minutes = body.interval_minutes
    if body.paused is not None:
        c.status = "paused" if body.paused else "active"
    if body.settings is not None or body.secrets is not None:
        settings, secret = _split(connector, {**c.settings, **(body.settings or {})}, body.secrets or {}, partial=True)
        merged_secret = {**decrypt(c.secret), **secret}
        try:
            connector.test(settings, merged_secret)
        except ConnectorError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Connexion impossible : {exc}") from exc
        c.settings, c.secret = settings, encrypt(merged_secret) if merged_secret else None
        c.status, c.last_error = "active", None
    audit.record(
        db,
        request,
        "connector.update",
        actor=auth.user,
        company_id=company.id,
        target=c.label,
        details={"fields": changes, "permissions": c.permissions},
    )
    db.commit()
    return connection_out(c)


@router.delete("/companies/{company_id}/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    company_id: uuid.UUID,
    connection_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = _manage(db, request, auth, company_id)
    c = _get(db, company.id, connection_id)
    audit.record(db, request, "connector.delete", actor=auth.user, company_id=company.id, target=c.label)
    db.delete(c)  # les identifiants chiffrés disparaissent ; les données importées restent
    db.commit()


@router.post("/companies/{company_id}/connections/{connection_id}/sync")
def sync_now(
    company_id: uuid.UUID,
    connection_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True)
    c = _get(db, company.id, connection_id)
    if c.status == "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, "Connexion en pause : reprenez-la avant de synchroniser.")
    try:
        run = run_sync(db, c, "manual", request=request, user=auth.user)
    except SyncBusy as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Une synchronisation est déjà en cours pour cette connexion."
        ) from exc
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"run": run_out(run), "connection": connection_out(c, run)}


@router.get("/companies/{company_id}/connections/{connection_id}/runs")
def list_runs(
    company_id: uuid.UUID,
    connection_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id)
    c = _get(db, company.id, connection_id)
    return [
        run_out(r)
        for r in db.scalars(select(SyncRun).where(SyncRun.connection_id == c.id).order_by(SyncRun.id.desc()).limit(30))
    ]
