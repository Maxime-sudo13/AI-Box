import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.categories import BY_KEY, CATEGORIES, CATEGORY_KEYS
from app.config import get_settings
from app.db import get_db
from app.deps import Auth, company_access, get_auth
from app.finance.bank import reconcile
from app.finance.data import f
from app.finance.ingest import (
    ACTIVE_STATUSES,
    AlreadyImported,
    UnsupportedFile,
    find_duplicate,
    ingest_document,
)
from app.finance.parties import find_or_create_party
from app.models import BankTransaction, Document, Invoice, Party

router = APIRouter(tags=["documents"])

STATUS_LABELS = {
    "verified": "Vérifiée automatiquement", "to_review": "À vérifier", "validated": "Validée",
    "duplicate": "Doublon", "ignored": "Ignoré", "failed": "Illisible",
}  # fmt: skip


@router.get("/categories")
def list_categories(_: Auth = Depends(get_auth)):
    return [{"key": c.key, "label": c.label, "group": c.group} for c in CATEGORIES]


def invoice_summary(inv: Invoice | None) -> dict | None:
    if inv is None:
        return None
    return {
        "id": str(inv.id), "direction": inv.direction, "party": inv.party.name if inv.party else None,
        "party_id": str(inv.party_id) if inv.party_id else None, "number": inv.number,
        "issue_date": inv.issue_date, "due_date": inv.due_date, "total_ht": f(inv.total_ht),
        "total_tva": f(inv.total_tva), "total_ttc": f(inv.total_ttc), "category": inv.category,
        "category_label": BY_KEY[inv.category].label if inv.category in BY_KEY else None,
        "paid_on": inv.paid_on, "issues": inv.issues, "field_status": inv.field_status,
    }  # fmt: skip


def document_out(doc: Document) -> dict:
    return {
        "id": str(doc.id), "filename": doc.filename, "content_type": doc.content_type, "size": doc.size,
        "status": doc.status, "status_label": STATUS_LABELS[doc.status], "uploaded_at": doc.uploaded_at,
        "method": (doc.extraction or {}).get("method"), "error": doc.error,
        "duplicate_of_id": str(doc.duplicate_of_id) if doc.duplicate_of_id else None,
        "invoice": invoice_summary(doc.invoice),
    }  # fmt: skip


def _get_document(db: Session, company_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = db.scalar(
        select(Document)
        .where(Document.id == document_id, Document.company_id == company_id)
        .options(selectinload(Document.invoice).selectinload(Invoice.lines))
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable.")
    return doc


@router.post("/companies/{company_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    company_id: uuid.UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, write=True, module="documents")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Fichier trop volumineux (maximum {get_settings().max_upload_mb} Mo)."
        )
    try:
        doc = ingest_document(db, company, auth.user, file.filename or "document", data)
    except UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except AlreadyImported as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": f"Ce fichier a déjà été importé (« {exc.document.filename} »).",
                "document_id": str(exc.document.id),
            },
        ) from exc
    reconcile(db, company.id)
    audit.record(db, request, "document.import", actor=auth.user, company_id=company.id, target=doc.filename,
                 details={"status": doc.status, "method": (doc.extraction or {}).get("method")})  # fmt: skip
    db.commit()
    return document_out(_get_document(db, company.id, doc.id))


@router.get("/companies/{company_id}/documents")
def list_documents(
    company_id: uuid.UUID,
    request: Request,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    q: str | None = None,
    category: str | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    ids: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="documents")
    query = (
        select(Document)
        .outerjoin(Invoice)
        .outerjoin(Party, Invoice.party_id == Party.id)
        .where(Document.company_id == company.id)
    )
    if status_filter == "active":
        query = query.where(Document.status.in_(ACTIVE_STATUSES))
    elif status_filter:
        query = query.where(Document.status.in_(status_filter.split(",")))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Document.filename.ilike(like), Invoice.number.ilike(like), Party.name.ilike(like)))
    if category:
        query = query.where(Invoice.category == category)
    if month:
        start = date.fromisoformat(f"{month}-01")
        end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
        query = query.where(Invoice.issue_date >= start, Invoice.issue_date < end)
    if ids:
        try:
            wanted = [uuid.UUID(i) for i in ids.split(",") if i]
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Identifiants invalides.") from exc
        query = query.where(Document.id.in_(wanted))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    docs = db.scalars(
        query.options(selectinload(Document.invoice).selectinload(Invoice.party))
        .order_by(Invoice.issue_date.desc().nulls_first(), Document.uploaded_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    counts = dict(
        db.execute(
            select(Document.status, func.count()).where(Document.company_id == company.id).group_by(Document.status)
        ).all()
    )
    return {"items": [document_out(d) for d in docs], "total": total, "counts": counts}


@router.get("/companies/{company_id}/documents/{document_id}")
def get_document(
    company_id: uuid.UUID, document_id: uuid.UUID, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, module="documents")
    doc = _get_document(db, company.id, document_id)
    out = document_out(doc)
    out["extraction"] = {k: v for k, v in (doc.extraction or {}).items() if k != "excerpt"}
    inv = doc.invoice
    if inv:
        out["invoice"]["lines"] = [
            {"description": l.description, "quantity": f(l.quantity, 3), "unit": l.unit,
             "unit_price": f(l.unit_price, 4), "vat_rate": f(l.vat_rate), "total_ht": f(l.total_ht)}
            for l in inv.lines
        ]  # fmt: skip
        out["invoice"]["vat_breakdown"] = inv.vat_breakdown
        payment = db.scalar(select(BankTransaction).where(BankTransaction.invoice_id == inv.id))
        out["invoice"]["payment"] = (
            {"date": payment.booked_on, "label": payment.label, "amount": f(payment.amount)} if payment else None
        )
    if doc.duplicate_of_id:
        original = db.get(Document, doc.duplicate_of_id)
        out["duplicate_of"] = {"id": str(original.id), "filename": original.filename} if original else None
    # Document suivant à vérifier, pour enchaîner les vérifications.
    out["next_to_review"] = db.scalar(
        select(Document.id)
        .where(Document.company_id == company.id, Document.status.in_(("to_review", "failed")), Document.id != doc.id)
        .order_by(Document.uploaded_at)
        .limit(1)
    )
    return out


@router.get("/companies/{company_id}/documents/{document_id}/file")
def document_file(
    company_id: uuid.UUID, document_id: uuid.UUID, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, module="documents")
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company.id))
    if doc is None or not Path(doc.storage_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.")
    return FileResponse(
        doc.storage_path,
        media_type=doc.content_type,
        filename=doc.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


class InvoicePatch(BaseModel):
    direction: Literal["purchase", "sale"] | None = None
    party_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    number: Annotated[str, Field(max_length=60)] | None = None
    issue_date: date | None = None
    due_date: date | None = None
    category: str | None = None
    total_ht: Decimal | None = None
    total_tva: Decimal | None = None
    total_ttc: Decimal | None = None
    apply_category_to_party: bool = False
    validate_invoice: bool = Field(False, alias="validate")


@router.patch("/companies/{company_id}/documents/{document_id}/invoice")
def update_invoice(
    company_id: uuid.UUID, document_id: uuid.UUID, body: InvoicePatch, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, write=True, module="documents")
    doc = _get_document(db, company.id, document_id)
    inv = doc.invoice
    if inv is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce document n'a pas été reconnu comme une facture.")
    changes = body.model_dump(exclude_unset=True, by_alias=False)
    changes.pop("apply_category_to_party", None)
    changes.pop("validate_invoice", None)
    if body.category is not None and body.category not in CATEGORY_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Catégorie inconnue.")

    status_map = dict(inv.field_status)
    if body.direction:
        inv.direction = body.direction
    if body.party_name:
        kind = "customer" if inv.direction == "sale" else "supplier"
        inv.party = find_or_create_party(db, company.id, kind, body.party_name.strip(), None)
        status_map["party"] = "confirmed"
    for field_name in ("number", "issue_date", "due_date", "total_ht", "total_tva", "total_ttc"):
        if field_name in changes:
            setattr(inv, field_name, changes[field_name])
            status_map[field_name] = "confirmed" if changes[field_name] is not None else "missing"
    if body.category:
        inv.category = body.category
        if body.apply_category_to_party and inv.party is not None:
            inv.party.category = body.category
            others = db.scalars(select(Invoice).join(Document).where(
                Invoice.party_id == inv.party_id, Invoice.id != inv.id, Document.status != "validated"))  # fmt: skip
            for other in others:
                other.category = body.category
            for tx in db.scalars(select(BankTransaction).where(
                    BankTransaction.party_id == inv.party_id, BankTransaction.category_source != "user")):  # fmt: skip
                tx.category, tx.category_source = body.category, "party"

    if body.validate_invoice:
        missing = [label for key, label in (("party_id", "le tiers"), ("issue_date", "la date"), ("total_ttc", "le montant TTC"))
                   if getattr(inv, key) is None]  # fmt: skip
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Pour valider, renseignez {', '.join(missing)}."
            )
        if (
            inv.total_ht is not None
            and inv.total_tva is not None
            and abs(inv.total_ht + inv.total_tva - inv.total_ttc) > Decimal("0.05")
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Les montants ne se recoupent pas : HT + TVA doit être égal au TTC.",
            )
        for key in ("party", "number", "issue_date", "due_date", "total_ht", "total_tva", "total_ttc"):
            if status_map.get(key) in ("estimated", "inconsistent"):
                status_map[key] = "confirmed"
        inv.issues = []
        inv.validated_by_id, inv.validated_at = auth.user.id, datetime.now(UTC)
        duplicate = None if (doc.extraction or {}).get("not_duplicate") else find_duplicate(db, inv)
        if duplicate:
            doc.status, doc.duplicate_of_id = "duplicate", duplicate.document_id
        else:
            doc.status = "validated"
    inv.field_status = status_map
    db.flush()
    reconcile(db, company.id)
    audit.record(db, request, "invoice.validate" if body.validate_invoice else "invoice.update", actor=auth.user,
                 company_id=company.id, target=f"{inv.party.name if inv.party else '?'} {inv.number or ''}".strip(),
                 details={"fields": sorted(changes), "status": doc.status})  # fmt: skip
    db.commit()
    return get_document(company_id, document_id, request, auth, db)


class StatusAction(BaseModel):
    action: Literal["ignore", "restore", "not_duplicate"]


@router.post("/companies/{company_id}/documents/{document_id}/status")
def change_status(
    company_id: uuid.UUID, document_id: uuid.UUID, body: StatusAction, request: Request,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id, write=True, module="documents")
    doc = _get_document(db, company.id, document_id)
    inv = doc.invoice
    if body.action == "ignore":
        doc.status = "ignored"
        if inv:
            for tx in db.scalars(select(BankTransaction).where(BankTransaction.invoice_id == inv.id)):
                tx.invoice_id = None
            inv.paid_on = None
    else:
        if inv is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ce document ne contient pas de facture exploitable.")
        if body.action == "not_duplicate":
            doc.extraction = {**(doc.extraction or {}), "not_duplicate": True}
            doc.duplicate_of_id = None
        duplicate = None if (doc.extraction or {}).get("not_duplicate") else find_duplicate(db, inv)
        if duplicate:
            doc.status, doc.duplicate_of_id = "duplicate", duplicate.document_id
        elif inv.validated_at:
            doc.status = "validated"
        else:
            key_ok = all(
                inv.field_status.get(k) in ("confirmed", "estimated") for k in ("party", "number", "issue_date")
            )
            doc.status = "verified" if key_ok and inv.field_status.get("total_ttc") == "confirmed" else "to_review"
    db.flush()
    reconcile(db, company.id)
    audit.record(db, request, f"document.{body.action}", actor=auth.user, company_id=company.id, target=doc.filename,
                 details={"status": doc.status})  # fmt: skip
    db.commit()
    return document_out(_get_document(db, company.id, doc.id))


@router.get("/companies/{company_id}/parties")
def list_parties(
    company_id: uuid.UUID, request: Request, kind: Literal["supplier", "customer"] | None = None,
    auth: Auth = Depends(get_auth), db: Session = Depends(get_db),
):  # fmt: skip
    company = company_access(db, request, auth.user, company_id)
    query = select(Party).where(Party.company_id == company.id).order_by(Party.name)
    if kind:
        query = query.where(Party.kind == kind)
    return [{"id": str(p.id), "name": p.name, "kind": p.kind, "siren": p.siren, "category": p.category}
            for p in db.scalars(query)]  # fmt: skip
