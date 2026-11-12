"""Exécution d'une synchronisation : appel du connecteur, import par le circuit habituel,
traçabilité. Une erreur de connecteur n'affecte que sa connexion."""

import hashlib
import logging
import traceback
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.finance.bank import import_bank, import_sales, reconcile
from app.finance.ingest import AlreadyImported, UnsupportedFile, ingest_document
from app.finance.tabular import BankRow, TabularError, parse_bank, parse_sales
from app.models import Company, Connection, ConnectorItem, DataImport, SyncRun, User

from .base import AuthError, ConnectorError, SyncContext
from .crypto import decrypt
from .registry import CONNECTORS

logger = logging.getLogger(__name__)


class SyncBusy(Exception):
    pass


def _lock_key(connection: Connection) -> int:
    return int.from_bytes(hashlib.sha256(f"sync:{connection.id}".encode()).digest()[:8], "big", signed=True)


def _sniff_kind(data: bytes) -> str | None:
    head = data[:4000].decode("utf-8", errors="ignore").lower()
    if any(w in head for w in ("couverts", "nourriture", "boissons ht", "journal de caisse")):
        return "sales"
    if any(w in head for w in ("libell", "solde", "débit", "debit", "crédit", "credit")):
        return "bank"
    return None


def run_sync(
    db: Session, connection: Connection, trigger: str, *, request: Request | None = None, user: User | None = None
) -> SyncRun:
    connector = CONNECTORS[connection.connector]
    if connector.online and get_settings().offline_mode:
        raise ConnectorError("Mode « zéro communication externe » actif : les connecteurs en ligne sont désactivés.")
    key = _lock_key(connection)
    # Verrou consultatif : deux synchronisations de la même connexion ne tournent jamais ensemble
    # (planificateur et bouton « Synchroniser » simultanés, ou plusieurs processus).
    if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
        raise SyncBusy()
    run = SyncRun(connection_id=connection.id, trigger=trigger, status="running", stats={})
    db.add(run)
    db.commit()
    company = db.get(Company, connection.company_id)
    stats = {
        "documents": 0,
        "verified": 0,
        "to_review": 0,
        "duplicates": 0,
        "failed": 0,
        "transactions": 0,
        "tables": 0,
    }
    done: set[str] = set()
    finalize = None
    try:
        ctx = SyncContext(
            settings=connection.settings,
            secrets=decrypt(connection.secret),
            permissions=frozenset(connection.permissions),
            cursor=connection.cursor or {},
            seen=lambda ext: (
                db.scalar(
                    select(ConnectorItem.id).where(
                        ConnectorItem.connection_id == connection.id, ConnectorItem.external_id == ext
                    )
                )
                is not None
            ),
        )
        result = connector.sync(ctx)
        finalize = result.finalize

        for doc in result.documents:
            outcome, document_id = "failed", None
            try:
                with db.begin_nested():
                    document = ingest_document(db, company, None, doc.filename, doc.data)
                outcome, document_id = document.status, document.id
                stats["documents"] += 1
                if document.status == "duplicate":
                    stats["duplicates"] += 1
                elif document.status in ("verified", "validated"):
                    stats["verified"] += 1
                elif document.status == "to_review":
                    stats["to_review"] += 1
                else:
                    stats["failed"] += 1
            except AlreadyImported as exc:
                outcome, document_id = "already_imported", exc.document.id
                stats["duplicates"] += 1
            except UnsupportedFile:
                outcome = "unsupported"
                stats["failed"] += 1
            db.add(
                ConnectorItem(
                    connection_id=connection.id, external_id=doc.external_id, document_id=document_id, outcome=outcome
                )
            )
            db.commit()
            done.add(doc.external_id)

        for table in result.tables:
            kind = _sniff_kind(table.data)
            try:
                if kind is None:
                    raise TabularError("Export CSV non reconnu.")
                rows, report = (parse_bank if kind == "bank" else parse_sales)(table.data)
                if rows:
                    dates = [getattr(r, "booked_on", None) or r.day for r in rows]
                    record = DataImport(
                        company_id=company.id,
                        kind=kind,
                        filename=f"{connection.label} — {table.filename}"[:255],
                        sha256=hashlib.sha256(table.data).hexdigest(),
                        rows_total=report.rows_total,
                        rows_added=0,
                        rows_skipped=report.skipped,
                        period_start=min(dates),
                        period_end=max(dates),
                        warnings=report.warnings,
                    )
                    db.add(record)
                    db.flush()
                    record.rows_added = (import_bank if kind == "bank" else import_sales)(db, company.id, record, rows)
                outcome = kind
                stats["tables"] += 1
            except TabularError:
                outcome = "unsupported"
                stats["failed"] += 1
            db.add(ConnectorItem(connection_id=connection.id, external_id=table.external_id, outcome=outcome))
            db.commit()
            done.add(table.external_id)

        if result.transactions:
            dates = [t.booked_on for t in result.transactions]
            record = DataImport(
                company_id=company.id,
                kind="bank",
                filename=f"{connection.label} — synchronisation du {datetime.now(UTC):%d/%m/%Y %H:%M}"[:255],
                sha256="api",
                rows_total=len(result.transactions),
                rows_added=0,
                rows_skipped=0,
                period_start=min(dates),
                period_end=max(dates),
                warnings=[],
            )
            db.add(record)
            db.flush()
            rows = [
                BankRow(t.booked_on, t.label, t.amount, t.balance, hashlib.sha256(t.external_id.encode()).hexdigest())
                for t in result.transactions
            ]
            record.rows_added = import_bank(db, company.id, record, rows)
            stats["transactions"] = record.rows_added

        reconcile(db, company.id)
        connection.cursor = result.cursor or connection.cursor
        connection.status, connection.last_error = "active", None
        run.status = "partial" if stats["failed"] else "success"
        run.stats = {**stats, "notes": result.notes}
    except (ConnectorError, OSError) as exc:
        db.rollback()
        connection.status = "expired" if isinstance(exc, AuthError) else "error"
        connection.last_error = (
            str(exc)[:1000] if isinstance(exc, ConnectorError) else "Erreur d'accès au système de fichiers."
        )
        run.status, run.error, run.stats = "failed", connection.last_error, stats
    except Exception:
        db.rollback()
        logger.error("Synchronisation %s en échec :\n%s", connection.id, traceback.format_exc())
        connection.status, connection.last_error = (
            "error",
            "Erreur inattendue du connecteur : consultez le journal technique.",
        )
        run.status, run.error, run.stats = "failed", connection.last_error, stats
    finally:
        if finalize:
            try:
                finalize(done)
            except Exception:  # une écriture facultative ne doit pas faire échouer l'import
                logger.warning("Finalisation du connecteur %s en échec", connection.id, exc_info=True)
        connection.last_sync_at = run.finished_at = datetime.now(UTC)
        if request is not None:
            audit.record(
                db,
                request,
                "connector.sync",
                actor=user,
                company_id=connection.company_id,
                target=connection.label,
                outcome="success" if run.status != "failed" else "failure",
                details={"trigger": trigger, "status": run.status, **{k: v for k, v in stats.items()}},
            )
        db.commit()
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        db.commit()
    return run
