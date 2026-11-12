"""Import d'un document : stockage de l'original, lecture, extraction, contrôle des doublons."""

import hashlib
import os
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction.invoice import ExtractedInvoice, parse_invoice
from app.extraction.reader import read_document
from app.finance.parties import find_or_create_party
from app.models import Company, Document, Invoice, InvoiceLine, User

ACCEPTED = {
    b"%PDF": ("application/pdf", ".pdf"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG": ("image/png", ".png"),
}

# Statuts dont les montants entrent dans les analyses.
ACTIVE_STATUSES = ("verified", "to_review", "validated")


class UnsupportedFile(ValueError):
    pass


class AlreadyImported(Exception):
    def __init__(self, document: Document):
        self.document = document


def sniff(data: bytes) -> tuple[str, str]:
    for magic, info in ACCEPTED.items():
        if data.startswith(magic):
            return info
    raise UnsupportedFile("Format non pris en charge : importez un PDF, ou une photo JPEG ou PNG.")


def document_path(company_id: uuid.UUID, sha256: str, ext: str) -> Path:
    root = Path(get_settings().data_dir).resolve()
    return root / "documents" / str(company_id) / sha256[:2] / f"{sha256}{ext}"


def _store(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o640)
    tmp.replace(path)


def normalize_number(number: str | None) -> str | None:
    return re.sub(r"[^A-Z0-9]", "", number.upper()) if number else None


def find_duplicate(db: Session, invoice: Invoice) -> Invoice | None:
    """Même tiers et même numéro de facture : c'est la même facture reçue deux fois."""
    key = normalize_number(invoice.number)
    if not key or invoice.party_id is None:
        return None
    others = db.scalars(
        select(Invoice)
        .join(Document)
        .where(
            Invoice.company_id == invoice.company_id,
            Invoice.party_id == invoice.party_id,
            Invoice.direction == invoice.direction,
            Invoice.id != invoice.id,
            Document.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Document.uploaded_at)
    ).all()
    return next((o for o in others if normalize_number(o.number) == key), None)


def apply_extraction(db: Session, company: Company, document: Document, x: ExtractedInvoice) -> Invoice:
    kind = "customer" if x.direction == "sale" else "supplier"
    party = find_or_create_party(
        db,
        company.id,
        kind,
        x.party_name,
        x.party_siren,
        category=x.category if x.direction == "purchase" else None,
    )
    sign = Decimal(-1) if x.is_credit_note else Decimal(1)

    def signed(value: Decimal | None) -> Decimal | None:
        return value * sign if value is not None else None

    category = "ventes" if x.direction == "sale" else (party.category if party and party.category else x.category)
    invoice = Invoice(
        company_id=company.id,
        document=document,
        direction=x.direction,
        party=party,
        number=x.number,
        issue_date=x.issue_date,
        due_date=x.due_date,
        category=category or "a_classer",
        total_ht=signed(x.total_ht),
        total_tva=signed(x.total_tva),
        total_ttc=signed(x.total_ttc),
        vat_breakdown=x.vat_breakdown,
        field_status=x.field_status,
        issues=x.issues,
        lines=[
            InvoiceLine(
                position=i,
                description=line.description,
                product_key=line.product_key,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                vat_rate=line.vat_rate,
                total_ht=signed(line.total_ht),
            )
            for i, line in enumerate(x.lines)
        ],
    )
    if not category:
        invoice.issues = [*invoice.issues, "Catégorie de dépense à préciser."]
    db.add(invoice)
    db.flush()

    duplicate = find_duplicate(db, invoice)
    if duplicate:
        document.status = "duplicate"
        document.duplicate_of_id = duplicate.document_id
    elif x.complete and "inconsistent" not in x.field_status.values():
        document.status = "verified"
    else:
        document.status = "to_review"
    return invoice


def ingest_document(db: Session, company: Company, user: User | None, filename: str, data: bytes) -> Document:
    content_type, ext = sniff(data)
    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.company_id == company.id, Document.sha256 == sha256))
    if existing:
        raise AlreadyImported(existing)

    path = document_path(company.id, sha256, ext)
    _store(path, data)
    document = Document(
        company_id=company.id,
        filename=Path(filename).name[:255] or f"document{ext}",
        content_type=content_type,
        size=len(data),
        sha256=sha256,
        storage_path=str(path),
        status="failed",
        uploaded_by_id=user.id if user else None,
    )
    db.add(document)

    settings = get_settings()
    try:
        read = read_document(path, content_type, ocr_lang=settings.ocr_lang)
    except Exception as exc:  # PDF corrompu ou protégé
        document.error = "Le document n'a pas pu être lu (fichier endommagé ou protégé par mot de passe)."
        document.extraction = {"exception": type(exc).__name__}
        db.flush()
        return document

    document.extraction = {
        "method": read.method,
        "pages": read.pages,
        "duration_ms": read.duration_ms,
        "excerpt": read.text[:4000],
        "read_at": datetime.now(UTC).isoformat(),
    }
    if read.method == "none" or len(read.text.strip()) < 20:
        document.error = read.warning or "Aucun texte lisible dans ce document."
        db.flush()
        return document

    extracted = parse_invoice(read, company_name=company.name, company_siren=company.siren)
    apply_extraction(db, company, document, extracted)
    db.flush()
    return document
