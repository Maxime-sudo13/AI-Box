"""Relevé bancaire : catégorisation des opérations et rapprochement avec les factures."""

import re
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.extraction.text import fold, name_key
from app.finance.ingest import ACTIVE_STATUSES
from app.finance.tabular import BankRow, SalesRow
from app.models import BankTransaction, DataImport, Document, Invoice, Party, SalesDay

# Règles appliquées au libellé (sans accents, minuscules). La première qui correspond gagne.
# Les noms d'organismes cités ne servent qu'à reconnaître les libellés bancaires usuels.
RULES: list[tuple[str, str, str]] = [
    # (sens : "+", "-" ou "*", motif, catégorie)
    ("+", r"remise cb|remise carte|telecollecte|rem cb|encaissement cb", "encaissement_cb"),
    ("+", r"versement especes|depot especes|vrst esp|versement esp", "encaissement_especes"),
    (
        "+",
        r"titres? restaurant|tickets? restaurant|cheques? dej|edenred|swile|pluxee|sodexo|up dejeuner|\bcrt\b",
        "encaissement_titres",
    ),
    ("-", r"commission|frais|cotisation carte|agios|tenue de compte", "frais_bancaires"),
    ("-", r"interets? debiteurs?|interets? d.emprunt", "interets"),
    ("-", r"\bsalaires?\b|\bpaie\b|acompte salaire", "salaires"),
    ("-", r"remuneration gerant|remuneration du gerant|remuneration dirigeant", "remuneration_gerant"),
    ("-", r"urssaf|retraite|prevoyance|mutuelle|agirc|arrco|\bssi\b|cotisations? sociales", "charges_sociales"),
    ("-", r"dgfip.*\btva\b|\btva\b", "tva"),
    ("-", r"dgfip.*\bis\b|impot sur les societes|\bis acompte\b", "impot_societes"),
    ("-", r"dgfip|\bcfe\b|tresor public|impots?|taxe", "impots_taxes"),
    ("-", r"echeance pret|remboursement pret|ech pret|\bpret\b|emprunt", "emprunt"),
    ("*", r"compte courant", "compte_courant"),
    ("-", r"\bloyer\b|\bsci\b|bail", "loyer"),
    ("-", r"assurance|mutuelles? du|\baxa\b|\bmaaf\b|allianz|\bmma\b|generali|groupama|hiscox", "assurance"),
    ("-", r"electricite|energie|\bgaz\b|\beau\b", "energie"),
    ("-", r"telecom|orange|\bsfr\b|bouygues|\bfree\b|fibre", "telecom"),
    ("-", r"ambiance sonore|musique|sacem|spre|abonnement|netflix|spotify|deezer", "logiciels"),
    ("*", r"virement interne|vir interne|epargne", "virement_interne"),
]

_GENERIC_WORDS = {
    "sepa",
    "vir",
    "prlv",
    "fact",
    "facture",
    "sarl",
    "sas",
    "france",
    "services",
    "service",
    "societe",
    "les",
    "des",
    "pro",
    "distribution",
    "groupe",
    "lyon",
    "paris",
    "rhone",
}


def _significant_tokens(key: str) -> list[str]:
    return [t for t in key.split() if len(t) >= 4 and t not in _GENERIC_WORDS]


def match_party(label: str, parties: list[Party]) -> Party | None:
    folded = name_key(label)
    words = set(folded.split())
    best, best_score = None, 0.0
    for party in parties:
        tokens = _significant_tokens(party.name_key)
        if not tokens:
            continue
        if party.name_key and f" {party.name_key} " in f" {folded} ":
            score = 1.0
        else:
            score = sum(1 for t in tokens if t in words) / len(tokens)
        if score > best_score:
            best, best_score = party, score
    return best if best_score >= 0.6 else None


def categorize(label: str, amount: Decimal, party: Party | None) -> tuple[str, str]:
    """Retourne (catégorie, origine de la catégorie)."""
    if party is not None and party.kind == "supplier" and amount < 0 and party.category:
        return party.category, "party"
    if party is not None and party.kind == "customer" and amount > 0:
        return "ventes", "party"
    folded = fold(label)
    for sign, pattern, category in RULES:
        if (sign == "*" or (sign == "+") == (amount > 0)) and re.search(pattern, folded):
            return category, "rule"
    return ("autres_recettes" if amount > 0 else "a_classer"), "rule"


def import_bank(db: Session, company_id: uuid.UUID, data_import: DataImport, rows: list[BankRow]) -> int:
    parties = db.scalars(select(Party).where(Party.company_id == company_id)).all()
    values = []
    for row in rows:
        party = match_party(row.label, list(parties))
        category, source = categorize(row.label, row.amount, party)
        values.append(
            dict(
                company_id=company_id,
                import_id=data_import.id,
                booked_on=row.booked_on,
                label=row.label,
                amount=row.amount,
                balance=row.balance,
                category=category,
                category_source=source,
                party_id=party.id if party else None,
                fingerprint=row.fingerprint,
            )
        )
    if not values:
        return 0
    added = 0
    for start in range(0, len(values), 1000):
        result = db.execute(
            insert(BankTransaction)
            .values(values[start : start + 1000])
            .on_conflict_do_nothing(constraint="uq_bank_transactions_company_fingerprint")
            .returning(BankTransaction.id)
        )
        added += len(result.all())
    return added


def import_sales(db: Session, company_id: uuid.UUID, data_import: DataImport, rows: list[SalesRow]) -> int:
    """Journées de caisse : une journée réimportée remplace la précédente (correction de Z)."""
    for start in range(0, len(rows), 1000):
        chunk = rows[start : start + 1000]
        stmt = insert(SalesDay).values(
            [
                dict(
                    company_id=company_id,
                    day=r.day,
                    import_id=data_import.id,
                    covers=r.covers,
                    food_ht=r.food_ht,
                    drinks_ht=r.drinks_ht,
                    total_ht=r.total_ht,
                    total_tva=r.total_tva,
                    total_ttc=r.total_ttc,
                    card=r.card,
                    cash=r.cash,
                    meal_vouchers=r.meal_vouchers,
                )
                for r in chunk
            ]
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[SalesDay.company_id, SalesDay.day],
                set_={
                    c: stmt.excluded[c]
                    for c in (
                        "import_id",
                        "covers",
                        "food_ht",
                        "drinks_ht",
                        "total_ht",
                        "total_tva",
                        "total_ttc",
                        "card",
                        "cash",
                        "meal_vouchers",
                    )
                },  # fmt: skip
            )
        )
    return len(rows)


def reconcile(db: Session, company_id: uuid.UUID) -> int:
    """Rapproche les opérations bancaires des factures et met à jour les dates de paiement.

    Une opération est rattachée à une facture non payée du même montant TTC, du même tiers
    si le libellé permet de l'identifier, dans une fenêtre de dates plausible. À montant égal,
    le numéro de facture cité dans le libellé, puis l'échéance la plus proche, départagent.
    Le rapprochement est idempotent : il peut être relancé après chaque import.
    """
    parties = list(db.scalars(select(Party).where(Party.company_id == company_id)))

    # Rattache aux tiers les opérations importées avant que le tiers n'existe.
    for tx in db.scalars(
        select(BankTransaction).where(BankTransaction.company_id == company_id, BankTransaction.party_id.is_(None))
    ):
        party = match_party(tx.label, parties)
        if party:
            tx.party_id = party.id
            if tx.category_source == "rule" and tx.category in ("a_classer", "autres_recettes"):
                tx.category, tx.category_source = categorize(tx.label, tx.amount, party)

    open_invoices = list(
        db.scalars(
            select(Invoice)
            .join(Document)
            .where(
                Invoice.company_id == company_id,
                Invoice.paid_on.is_(None),
                Invoice.total_ttc.is_not(None),
                Document.status.in_(ACTIVE_STATUSES),
            )
        )
    )
    linked_ids = set(
        db.scalars(
            select(BankTransaction.invoice_id).where(
                BankTransaction.company_id == company_id, BankTransaction.invoice_id.is_not(None)
            )
        )
    )
    open_invoices = [i for i in open_invoices if i.id not in linked_ids]

    matched = 0
    txs = db.scalars(
        select(BankTransaction)
        .where(BankTransaction.company_id == company_id, BankTransaction.invoice_id.is_(None))
        .order_by(BankTransaction.booked_on, BankTransaction.id)
    ).all()
    for tx in txs:
        direction = "purchase" if tx.amount < 0 else "sale"
        target = abs(tx.amount)
        label_key = re.sub(r"[^A-Z0-9]", "", tx.label.upper())
        candidates = [
            inv for inv in open_invoices
            if inv.direction == direction and abs(abs(inv.total_ttc) - target) <= Decimal("0.01")
            and inv.issue_date is not None
            and inv.issue_date - timedelta(days=5) <= tx.booked_on <= inv.issue_date + timedelta(days=150)
        ]  # fmt: skip
        if tx.party_id:
            same_party = [i for i in candidates if i.party_id == tx.party_id]
            candidates = same_party
        elif len(candidates) > 1:
            continue  # ambigu sans tiers identifié : on ne devine pas
        if not candidates:
            continue

        def rank(inv: Invoice):
            cited = bool(inv.number) and re.sub(r"[^A-Z0-9]", "", inv.number.upper()) in label_key
            due = inv.due_date or inv.issue_date
            return (not cited, abs((tx.booked_on - due).days))

        invoice = min(candidates, key=rank)
        tx.invoice_id = invoice.id
        invoice.paid_on = tx.booked_on
        if tx.party_id is None:
            tx.party_id = invoice.party_id
        if invoice.category and tx.category_source != "user":
            tx.category, tx.category_source = invoice.category, "invoice"
        open_invoices.remove(invoice)
        matched += 1
    db.flush()
    return matched
