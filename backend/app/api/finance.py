import hashlib
import time
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.categories import BY_KEY, CATEGORY_KEYS
from app.config import get_settings, today
from app.db import get_db
from app.deps import Auth, company_access, get_auth
from app.finance import anomalies, engine, treasury
from app.finance.bank import import_bank, import_sales, reconcile
from app.finance.data import f, load, month_of
from app.finance.tabular import TabularError, parse_bank, parse_sales
from app.models import (
    AnomalyReview,
    BankTransaction,
    DataImport,
    Document,
    Invoice,
    Party,
    SalesDay,
)

router = APIRouter(tags=["finance"])


# --- Imports CSV -----------------------------------------------------------------------------


def import_out(i: DataImport) -> dict:
    return {
        "id": str(i.id), "kind": i.kind, "filename": i.filename, "rows_total": i.rows_total,
        "rows_added": i.rows_added, "rows_skipped": i.rows_skipped, "period_start": i.period_start,
        "period_end": i.period_end, "warnings": i.warnings, "imported_at": i.imported_at,
    }  # fmt: skip


@router.post("/companies/{company_id}/imports/{kind}", status_code=status.HTTP_201_CREATED)
async def import_file(
    company_id: uuid.UUID,
    kind: Literal["bank", "sales"],
    request: Request,
    file: Annotated[UploadFile, File()],
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True, module="finance")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Fichier trop volumineux.")
    try:
        rows, report = (parse_bank if kind == "bank" else parse_sales)(data)
    except TabularError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aucune ligne exploitable dans ce fichier.")
    dates = [getattr(r, "booked_on", None) or r.day for r in rows]
    record = DataImport(
        company_id=company.id,
        kind=kind,
        filename=(file.filename or "import.csv")[:255],
        sha256=hashlib.sha256(data).hexdigest(),
        rows_total=report.rows_total,
        rows_added=0,
        rows_skipped=report.skipped,
        period_start=min(dates),
        period_end=max(dates),
        warnings=report.warnings,
        imported_by_id=auth.user.id,
    )
    db.add(record)
    db.flush()
    if kind == "bank":
        record.rows_added = import_bank(db, company.id, record, rows)
        already = len(rows) - record.rows_added
        if already:
            record.warnings = [*record.warnings, f"{already} opération(s) déjà présente(s) n'ont pas été dupliquée(s)."]
        reconcile(db, company.id)
    else:
        record.rows_added = import_sales(db, company.id, record, rows)
    audit.record(db, request, f"import.{kind}", actor=auth.user, company_id=company.id, target=record.filename,
                 details={"rows": record.rows_total, "added": record.rows_added})  # fmt: skip
    db.commit()
    return import_out(record)


@router.get("/companies/{company_id}/imports")
def list_imports(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    return [import_out(i) for i in db.scalars(
        select(DataImport).where(DataImport.company_id == company.id).order_by(DataImport.imported_at.desc()).limit(50))]  # fmt: skip


@router.get("/companies/{company_id}/bank-transactions")
def list_transactions(
    company_id: uuid.UUID,
    request: Request,
    q: str | None = None,
    category: str | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    ids: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    query = select(BankTransaction).where(BankTransaction.company_id == company.id)
    if q:
        query = query.where(BankTransaction.label.ilike(f"%{q.strip()}%"))
    if category:
        query = query.where(BankTransaction.category == category)
    if month:
        start = date.fromisoformat(f"{month}-01")
        end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
        query = query.where(BankTransaction.booked_on >= start, BankTransaction.booked_on < end)
    if ids:
        query = query.where(BankTransaction.id.in_([int(i) for i in ids.split(",") if i.isdigit()]))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(BankTransaction.booked_on.desc(), BankTransaction.id.desc()).limit(limit).offset(offset)
    )
    parties = {p.id: p.name for p in db.scalars(select(Party).where(Party.company_id == company.id))}
    inv_docs = dict(db.execute(select(Invoice.id, Invoice.document_id).where(Invoice.company_id == company.id)).all())
    return {
        "total": total,
        "items": [{
            "id": t.id, "date": t.booked_on, "label": t.label, "amount": f(t.amount), "balance": f(t.balance),
            "category": t.category, "category_label": BY_KEY[t.category].label if t.category in BY_KEY else t.category,
            "category_source": t.category_source, "party": parties.get(t.party_id),
            "document_id": str(inv_docs[t.invoice_id]) if t.invoice_id in inv_docs else None,
        } for t in rows],
    }  # fmt: skip


class TransactionPatch(BaseModel):
    category: str


@router.patch("/companies/{company_id}/bank-transactions/{tx_id}")
def update_transaction(
    company_id: uuid.UUID, tx_id: int, body: TransactionPatch, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, write=True, module="finance")
    tx = db.scalar(select(BankTransaction).where(BankTransaction.id == tx_id, BankTransaction.company_id == company.id))
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opération introuvable.")
    if body.category not in CATEGORY_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Catégorie inconnue.")
    before = tx.category
    tx.category, tx.category_source = body.category, "user"
    audit.record(db, request, "bank.categorize", actor=auth.user, company_id=company.id, target=tx.label[:300],
                 details={"from": before, "to": body.category})  # fmt: skip
    db.commit()
    return {"id": tx.id, "category": tx.category}


# --- Analyses ----------------------------------------------------------------------------------


def _analysis(db: Session, company, *, with_alerts: bool = False):
    started = time.monotonic()
    ds = load(db, company, today())
    months = engine.build_months(ds)
    forecast = treasury.forecast(ds)
    alerts = anomalies.detect(db, ds, months, forecast) if with_alerts else None
    return ds, months, forecast, alerts, int((time.monotonic() - started) * 1000)


@router.get("/companies/{company_id}/finance/overview")
def overview(
    company_id: uuid.UUID, request: Request,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, module="finance")
    ds, months, forecast, alerts, elapsed = _analysis(db, company, with_alerts=True)
    available = engine.complete_months(ds, months)
    if not available and not months:
        return {"empty": True, "months": []}
    selected = date.fromisoformat(f"{month}-01") if month else (available[-1] if available else max(months))
    open_alerts = [a for a in alerts if a["status"] == "open"]
    return {
        "empty": False,
        "month": selected.isoformat()[:7],
        "month_label": engine.month_label(selected),
        "months": [{"value": k.isoformat()[:7], "label": engine.month_label(k)} for k in sorted(months)][::-1],
        "is_restaurant": ds.is_restaurant,
        "kpis": engine.kpis(ds, months, selected),
        "series": engine.series(ds, months),
        "breakdown": engine.breakdown(months, selected),
        "treasury": {k: forecast.get(k) for k in ("available", "reason", "as_of", "balance", "threshold", "low_point", "end_balance")},
        "alerts": {
            "open": len(open_alerts),
            "high": sum(1 for a in open_alerts if a["severity"] == "high"),
            "impact": f(sum((a["impact"] or {}).get("amount") or 0 for a in open_alerts if a["kind"] not in ("treasury_tension",))),
            "top": open_alerts[:4],
        },
        "computed_in_ms": elapsed,
    }  # fmt: skip


@router.get("/companies/{company_id}/finance/treasury")
def treasury_view(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company = company_access(db, request, auth.user, company_id, module="finance")
    _, _, forecast, _, _ = _analysis(db, company)
    return forecast


@router.get("/companies/{company_id}/finance/alerts")
def list_alerts(company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)):
    company = company_access(db, request, auth.user, company_id, module="finance")
    _, _, _, alerts, elapsed = _analysis(db, company, with_alerts=True)
    return {"items": alerts, "computed_in_ms": elapsed}


class AlertReview(BaseModel):
    fingerprint: Annotated[str, Field(min_length=3, max_length=120)]
    status: Literal["open", "acknowledged", "resolved", "dismissed"]
    note: Annotated[str, Field(max_length=500)] | None = None


@router.post("/companies/{company_id}/finance/alerts/review")
def review_alert(
    company_id: uuid.UUID, body: AlertReview, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, write=True, module="finance")
    review = db.get(AnomalyReview, (company.id, body.fingerprint))
    if body.status == "open":
        if review:
            db.delete(review)
    else:
        if review is None:
            review = AnomalyReview(company_id=company.id, fingerprint=body.fingerprint)
            db.add(review)
        review.status, review.note, review.reviewed_by_id = body.status, body.note, auth.user.id
        review.reviewed_at = func.now()
    audit.record(db, request, "alert.review", actor=auth.user, company_id=company.id, target=body.fingerprint,
                 details={"status": body.status, "note": body.note})  # fmt: skip
    db.commit()
    return {"fingerprint": body.fingerprint, "status": body.status}


@router.get("/companies/{company_id}/data/summary")
def data_summary(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company = company_access(db, request, auth.user, company_id)
    counts = dict(db.execute(select(Document.status, func.count()).where(Document.company_id == company.id)
                             .group_by(Document.status)).all())  # fmt: skip
    bank = db.execute(select(func.count(), func.min(BankTransaction.booked_on), func.max(BankTransaction.booked_on))
                      .where(BankTransaction.company_id == company.id)).one()  # fmt: skip
    sales = db.execute(select(func.count(), func.min(SalesDay.day), func.max(SalesDay.day))
                       .where(SalesDay.company_id == company.id)).one()  # fmt: skip
    unmatched = db.scalar(select(func.count()).where(
        BankTransaction.company_id == company.id, BankTransaction.category == "a_classer"))  # fmt: skip
    inv_range = db.execute(select(func.min(Invoice.issue_date), func.max(Invoice.issue_date))
                           .join(Document).where(Invoice.company_id == company.id,
                                                 Document.status.in_(("verified", "to_review", "validated")))).one()  # fmt: skip
    parties = dict(
        db.execute(select(Party.kind, func.count()).where(Party.company_id == company.id).group_by(Party.kind)).all()
    )
    now = today()
    warnings = []
    if bank[2] and (now - bank[2]).days > 10:
        warnings.append(
            f"Dernière opération bancaire le {bank[2].strftime('%d/%m/%Y')} : importez un relevé plus récent."
        )
    if sales[2] and (now - sales[2]).days > 10:
        warnings.append(
            f"Dernière journée de caisse le {sales[2].strftime('%d/%m/%Y')} : importez le journal de caisse récent."
        )
    if counts.get("to_review"):
        warnings.append(f"{counts['to_review']} facture(s) à vérifier.")
    if counts.get("failed"):
        warnings.append(f"{counts['failed']} document(s) illisible(s).")
    if unmatched:
        warnings.append(f"{unmatched} opération(s) bancaire(s) à classer.")
    month_now = month_of(now)
    return {
        "documents": {"total": sum(counts.values()), "by_status": counts},
        "invoices": {"first": inv_range[0], "last": inv_range[1]},
        "bank": {"count": bank[0], "first": bank[1], "last": bank[2], "to_classify": unmatched},
        "sales": {"days": sales[0], "first": sales[1], "last": sales[2]},
        "parties": {"suppliers": parties.get("supplier", 0), "customers": parties.get("customer", 0)},
        "warnings": warnings, "current_month": month_now.isoformat()[:7],
    }  # fmt: skip
