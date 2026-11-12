"""Moteur de calcul : compte de résultat mensuel et indicateurs.

Tout est calculé de façon déterministe à partir des données importées ; aucun modèle d'IA
n'intervient. Chaque indicateur est livré avec sa formule, ses données d'entrée et leur
niveau de fiabilité, pour que le dirigeant puisse vérifier le chiffre affiché.
"""

import calendar
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.categories import BY_KEY, GROUP_LABELS
from app.finance.data import ZERO, Dataset, add_months, f, month_of

PNL_GROUPS = ("matieres", "externes", "impots", "personnel", "financier")


@dataclass
class Month:
    start: date
    sales_ht: Decimal = ZERO
    food_ht: Decimal = ZERO
    drinks_ht: Decimal = ZERO
    sales_ttc: Decimal = ZERO
    covers: int = 0
    days_open: int = 0
    invoiced_ht: Decimal = ZERO
    invoiced_count: int = 0
    charges: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    # Pour chaque catégorie : nombre de factures et d'opérations bancaires utilisées.
    sources: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"invoices": 0, "bank": 0}))
    estimated: set[str] = field(default_factory=set)
    to_review: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    invoice_ids: dict[str, list[uuid.UUID]] = field(default_factory=lambda: defaultdict(list))
    bank_ids: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))

    @property
    def end(self) -> date:
        return self.start.replace(day=calendar.monthrange(self.start.year, self.start.month)[1])

    @property
    def revenue(self) -> Decimal:
        return self.sales_ht + self.invoiced_ht

    def group_total(self, group: str) -> Decimal:
        return sum((v for k, v in self.charges.items() if BY_KEY[k].group == group), ZERO)

    @property
    def ebe(self) -> Decimal:
        return self.revenue - sum(self.group_total(g) for g in ("matieres", "externes", "impots", "personnel"))

    def ratio(self, numerator: Decimal, denominator: Decimal) -> Decimal | None:
        return numerator / denominator * 100 if denominator else None


def build_months(ds: Dataset) -> dict[date, Month]:
    months: dict[date, Month] = {}

    def month(d: date) -> Month:
        key = month_of(d)
        if key not in months:
            months[key] = Month(key)
        return months[key]

    for s in ds.sales:
        m = month(s.day)
        m.sales_ht += s.total_ht
        m.food_ht += s.food_ht or ZERO
        m.drinks_ht += s.drinks_ht or ZERO
        m.sales_ttc += s.total_ttc or ZERO
        m.covers += s.covers or 0
        m.days_open += 1

    invoiced_parties: set[uuid.UUID] = set()
    for inv in ds.invoices:
        if inv.issue_date is None:
            continue
        m = month(inv.issue_date)
        amount = inv.total_ht
        if amount is None and inv.total_ttc is not None:
            amount = inv.total_ttc
            m.estimated.add(inv.category or "a_classer")
        if amount is None:
            continue
        if inv.party_id:
            invoiced_parties.add(inv.party_id)
        if inv.direction == "sale":
            m.invoiced_ht += amount
            m.invoiced_count += 1
            m.invoice_ids["ventes"].append(inv.id)
            if ds.status(inv) == "to_review":
                m.to_review["ventes"] += 1
            continue
        category = inv.category if inv.category in BY_KEY else "a_classer"
        if BY_KEY[category].group not in PNL_GROUPS:
            continue
        m.charges[category] += amount
        m.sources[category]["invoices"] += 1
        m.invoice_ids[category].append(inv.id)
        if ds.status(inv) == "to_review":
            m.to_review[category] += 1

    # Charges connues uniquement par la banque (salaires, loyer, cotisations…). Les paiements
    # de fournisseurs qui envoient des factures sont exclus : la facture fait foi.
    for tx in ds.txs:
        if tx.amount >= 0 or tx.invoice_id is not None:
            continue
        if tx.party_id in invoiced_parties:
            continue
        category = tx.category if tx.category in BY_KEY else "a_classer"
        if BY_KEY[category].group not in PNL_GROUPS:
            continue
        m = month(tx.booked_on)
        m.charges[category] += -tx.amount
        m.sources[category]["bank"] += 1
        m.bank_ids[category].append(tx.id)
    return months


def complete_months(ds: Dataset, months: dict[date, Month]) -> list[date]:
    """Mois entièrement écoulés pour lesquels des données existent, du plus ancien au plus récent."""
    current = month_of(ds.today)
    return sorted(k for k in months if k < current)


def _change(current: Decimal | None, previous: Decimal | None) -> dict[str, Any]:
    if current is None or previous is None:
        return {"previous": f(previous), "change": None, "change_pct": None}
    change = current - previous
    return {
        "previous": f(previous),
        "change": f(change),
        "change_pct": f(change / abs(previous) * 100, 1) if previous else None,
    }


MONTH_NAMES = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
               "septembre", "octobre", "novembre", "décembre"]  # fmt: skip


def month_label(d: date) -> str:
    return f"{MONTH_NAMES[d.month - 1]} {d.year}"


def _quality(m: Month, categories: list[str]) -> tuple[str, list[str]]:
    notes = []
    review = sum(m.to_review.get(c, 0) for c in categories)
    if review:
        notes.append(f"{review} facture(s) de ce calcul sont encore à vérifier.")
    if any(c in m.estimated for c in categories):
        notes.append("Certains montants HT ont été remplacés par le TTC faute de mieux.")
    if review or any(c in m.estimated for c in categories):
        return "estimated", notes
    return "confirmed", notes


def _input(
    label: str,
    value: Decimal | int | None,
    unit: str,
    *,
    source: str,
    count: int | None = None,
    link: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"label": label, "value": f(value), "unit": unit, "source": source, "count": count, "link": link}


def kpis(ds: Dataset, months: dict[date, Month], selected: date) -> list[dict[str, Any]]:
    m = months.get(selected) or Month(selected)
    prev = months.get(add_months(selected, -1))
    period = month_label(selected)
    out: list[dict[str, Any]] = []
    month_link = {"month": selected.isoformat()[:7]}

    def charges_inputs(month: Month, groups: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for cat, amount in sorted(month.charges.items(), key=lambda kv: -kv[1]):
            if BY_KEY[cat].group in groups and amount:
                src = month.sources[cat]
                parts = []
                if src["invoices"]:
                    parts.append(f"{src['invoices']} facture(s)")
                if src["bank"]:
                    parts.append(f"{src['bank']} opération(s) bancaire(s)")
                rows.append(
                    _input(
                        BY_KEY[cat].label,
                        -amount,
                        "eur",
                        source=" et ".join(parts),
                        count=src["invoices"] + src["bank"],
                        link={**month_link, "category": cat},
                    )
                )
        return rows

    # Chiffre d'affaires ------------------------------------------------------------------
    rev_inputs = []
    if m.days_open:
        rev_inputs.append(
            _input(
                "Ventes de caisse HT",
                m.sales_ht,
                "eur",
                source=f"{m.days_open} journée(s) de caisse",
                count=m.days_open,
            )
        )
    if m.invoiced_count:
        rev_inputs.append(
            _input(
                "Factures de vente HT",
                m.invoiced_ht,
                "eur",
                source=f"{m.invoiced_count} facture(s)",
                count=m.invoiced_count,
                link={**month_link, "category": "ventes"},
            )
        )
    quality, notes = _quality(m, ["ventes"])
    if ds.sales and m.days_open and max(s.day for s in ds.sales if month_of(s.day) == selected) < m.end:
        quality = "partial"
        notes.append("Le journal de caisse ne couvre pas tout le mois.")
    out.append({
        "key": "revenue", "label": "Chiffre d'affaires HT", "unit": "eur", "value": f(m.revenue),
        **_change(m.revenue, prev.revenue if prev else None), "good_direction": "up",
        "formula": "Ventes de caisse HT + factures de vente HT émises dans le mois",
        "inputs": rev_inputs, "quality": quality if rev_inputs else "missing", "notes": notes, "period": period,
    })  # fmt: skip

    # EBE ------------------------------------------------------------------------------------
    used = [c for c in m.charges if BY_KEY[c].group in ("matieres", "externes", "impots", "personnel")]
    quality, notes = _quality(m, used + ["ventes"])
    notes.append(
        "Excédent brut d'exploitation : ce que l'activité dégage avant amortissements, intérêts d'emprunt "
        "et impôt sur les bénéfices. Les remboursements d'emprunt, la TVA et les investissements n'en font pas partie."
    )
    if "a_classer" in m.charges:
        notes.append("Des dépenses restent « à classer » : elles sont comptées en charges externes.")
    out.append({
        "key": "ebe", "label": "EBE estimé", "unit": "eur", "value": f(m.ebe),
        **_change(m.ebe, prev.ebe if prev else None), "good_direction": "up",
        "formula": "Chiffre d'affaires HT − achats consommés − charges externes − impôts et taxes − charges de personnel",
        "inputs": [_input("Chiffre d'affaires HT", m.revenue, "eur", source="voir indicateur")]
        + charges_inputs(m, ("matieres", "externes", "impots", "personnel")),
        "quality": quality, "notes": notes, "period": period,
        "secondary": {"label": "Marge d'EBE", "value": f(m.ratio(m.ebe, m.revenue), 1), "unit": "pct"},
    })  # fmt: skip

    if ds.is_restaurant:
        food = m.charges.get("alimentaire", ZERO)
        drinks = m.charges.get("boissons", ZERO)
        prev_food_pct = prev.ratio(prev.charges.get("alimentaire", ZERO), prev.food_ht) if prev else None
        q, n = _quality(m, ["alimentaire"])
        n.append(
            "Sans inventaire de stock, le coût matière est approché par les achats du mois : "
            "un gros réapprovisionnement peut le gonfler ponctuellement."
        )
        out.append({
            "key": "food_cost", "label": "Coût matière cuisine", "unit": "pct", "value": f(m.ratio(food, m.food_ht), 1),
            **_change(m.ratio(food, m.food_ht), prev_food_pct), "good_direction": "down",
            "formula": "Achats alimentaires HT ÷ chiffre d'affaires nourriture HT",
            "inputs": [
                _input("Achats alimentaires HT", food, "eur", source=f"{m.sources['alimentaire']['invoices']} facture(s)",
                       count=m.sources["alimentaire"]["invoices"], link={**month_link, "category": "alimentaire"}),
                _input("CA nourriture HT", m.food_ht, "eur", source=f"{m.days_open} journée(s) de caisse", count=m.days_open),
            ],
            "quality": q, "notes": n, "period": period,
        })  # fmt: skip
        q, n = _quality(m, ["boissons"])
        out.append({
            "key": "drinks_cost", "label": "Coût matière boissons", "unit": "pct", "value": f(m.ratio(drinks, m.drinks_ht), 1),
            **_change(m.ratio(drinks, m.drinks_ht), prev.ratio(prev.charges.get("boissons", ZERO), prev.drinks_ht) if prev else None),
            "good_direction": "down",
            "formula": "Achats de boissons HT ÷ chiffre d'affaires boissons HT",
            "inputs": [
                _input("Achats de boissons HT", drinks, "eur", source=f"{m.sources['boissons']['invoices']} facture(s)",
                       count=m.sources["boissons"]["invoices"], link={**month_link, "category": "boissons"}),
                _input("CA boissons HT", m.drinks_ht, "eur", source=f"{m.days_open} journée(s) de caisse", count=m.days_open),
            ],
            "quality": q, "notes": n, "period": period,
        })  # fmt: skip

    personnel = m.group_total("personnel")
    q, n = _quality(m, [c for c in m.charges if BY_KEY[c].group == "personnel"])
    n.append("Salaires nets versés et cotisations prélevées, d'après le relevé bancaire.")
    out.append({
        "key": "payroll", "label": "Masse salariale", "unit": "pct", "value": f(m.ratio(personnel, m.revenue), 1),
        **_change(m.ratio(personnel, m.revenue), prev.ratio(prev.group_total("personnel"), prev.revenue) if prev else None),
        "good_direction": "down",
        "formula": "(Salaires + rémunération du gérant + cotisations sociales) ÷ chiffre d'affaires HT",
        "inputs": charges_inputs(m, ("personnel",)) + [_input("Chiffre d'affaires HT", m.revenue, "eur", source="voir indicateur")],
        "quality": q, "notes": n, "period": period,
        "secondary": {"label": "Montant", "value": f(personnel), "unit": "eur"},
    })  # fmt: skip

    if m.covers:
        ticket = m.sales_ttc / m.covers if m.sales_ttc else None
        prev_ticket = prev.sales_ttc / prev.covers if prev and prev.covers and prev.sales_ttc else None
        out.append({
            "key": "ticket", "label": "Ticket moyen TTC", "unit": "eur", "value": f(ticket),
            **_change(ticket, prev_ticket), "good_direction": "up",
            "formula": "Ventes de caisse TTC ÷ nombre de couverts",
            "inputs": [_input("Ventes de caisse TTC", m.sales_ttc, "eur", source=f"{m.days_open} journée(s) de caisse"),
                       _input("Couverts servis", m.covers, "count", source=f"{m.days_open} journée(s) de caisse")],
            "quality": "confirmed", "notes": [], "period": period,
            "secondary": {"label": "Couverts", "value": m.covers, "unit": "count",
                          "change_pct": f((m.covers - prev.covers) / prev.covers * 100, 1) if prev and prev.covers else None},
        })  # fmt: skip
    return out


def series(ds: Dataset, months: dict[date, Month]) -> list[dict[str, Any]]:
    keys = complete_months(ds, months)[-12:]
    current = month_of(ds.today)
    if current in months:
        keys.append(current)
    out = []
    for key in keys:
        m = months[key]
        out.append({
            "month": key.isoformat()[:7], "label": month_label(key), "partial": key == current,
            "revenue": f(m.revenue), "matieres": f(m.group_total("matieres")),
            "externes": f(m.group_total("externes") + m.group_total("impots")),
            "personnel": f(m.group_total("personnel")), "ebe": f(m.ebe),
            "ebe_pct": f(m.ratio(m.ebe, m.revenue), 1),
            "food_cost_pct": f(m.ratio(m.charges.get("alimentaire", ZERO), m.food_ht), 1) if m.food_ht else None,
            "drinks_cost_pct": f(m.ratio(m.charges.get("boissons", ZERO), m.drinks_ht), 1) if m.drinks_ht else None,
            "payroll_pct": f(m.ratio(m.group_total("personnel"), m.revenue), 1),
            "covers": m.covers or None,
        })  # fmt: skip
    return out


def breakdown(months: dict[date, Month], selected: date) -> list[dict[str, Any]]:
    """Charges du mois par catégorie, comparées à la moyenne des trois mois précédents."""
    m = months.get(selected) or Month(selected)
    previous = [months[k] for k in (add_months(selected, -i) for i in (1, 2, 3)) if k in months]
    cats = set(m.charges) | {c for p in previous for c in p.charges}
    out = []
    for cat in cats:
        amount = m.charges.get(cat, ZERO)
        avg = sum((p.charges.get(cat, ZERO) for p in previous), ZERO) / len(previous) if previous else None
        if not amount and not avg:
            continue
        out.append({
            "category": cat, "label": BY_KEY[cat].label, "group": BY_KEY[cat].group,
            "group_label": GROUP_LABELS.get(BY_KEY[cat].group, ""), "amount": f(amount),
            "share_of_revenue": f(m.ratio(amount, m.revenue), 1),
            "average_3m": f(avg), "change_vs_average_pct": f((amount - avg) / avg * 100, 1) if avg else None,
            "invoices": m.sources[cat]["invoices"], "bank": m.sources[cat]["bank"],
        })  # fmt: skip
    return sorted(out, key=lambda r: -(r["amount"] or 0))
