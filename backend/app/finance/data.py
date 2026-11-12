"""Chargement, en une fois, des données d'une entreprise utiles aux calculs."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.finance.ingest import ACTIVE_STATUSES
from app.models import BankTransaction, Company, Document, Invoice, Party, SalesDay


@dataclass
class Dataset:
    company: Company
    today: date
    invoices: list[Invoice]
    sales: list[SalesDay]
    txs: list[BankTransaction]
    parties: dict[uuid.UUID, Party]
    doc_status: dict[uuid.UUID, str] = field(default_factory=dict)

    @property
    def purchases(self) -> list[Invoice]:
        return [i for i in self.invoices if i.direction == "purchase"]

    @property
    def sales_invoices(self) -> list[Invoice]:
        return [i for i in self.invoices if i.direction == "sale"]

    def party_name(self, party_id: uuid.UUID | None) -> str:
        party = self.parties.get(party_id) if party_id else None
        return party.name if party else "Tiers non identifié"

    def status(self, invoice: Invoice) -> str:
        return self.doc_status.get(invoice.document_id, "verified")

    @property
    def is_restaurant(self) -> bool:
        return any(s.food_ht is not None for s in self.sales)


def load(db: Session, company: Company, today: date) -> Dataset:
    rows = db.execute(
        select(Invoice, Document.status)
        .join(Document)
        .where(Invoice.company_id == company.id, Document.status.in_(ACTIVE_STATUSES))
        .options(selectinload(Invoice.lines))
    ).all()
    return Dataset(
        company=company,
        today=today,
        invoices=[inv for inv, _ in rows],
        doc_status={inv.document_id: status for inv, status in rows},
        sales=list(db.scalars(select(SalesDay).where(SalesDay.company_id == company.id).order_by(SalesDay.day))),
        txs=list(
            db.scalars(
                select(BankTransaction)
                .where(BankTransaction.company_id == company.id)
                .order_by(BankTransaction.booked_on, BankTransaction.id)
            )
        ),
        parties={p.id: p for p in db.scalars(select(Party).where(Party.company_id == company.id))},
    )


ZERO = Decimal(0)


def month_of(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def f(value: Decimal | float | int | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def money(v: Decimal | float | None, decimals: int = 0) -> str:
    """Montant au format français : « 1 234 € » ou « 24,90 € »."""
    if v is None:
        return "—"
    value = Decimal(str(v))
    text = f"{abs(value):,.{decimals}f}".replace(",", "\u202f").replace(".", ",")
    return f"{'−' if value < 0 else ''}{text} €"
