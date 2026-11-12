"""Prévision de trésorerie à 90 jours.

La prévision part du dernier solde bancaire connu et ajoute, jour par jour :
- les factures connues (fournisseurs à payer, clients à encaisser) à leur échéance ;
- les prélèvements récurrents détectés dans le relevé (salaires, loyer, cotisations…) ;
- les recettes attendues, d'après la moyenne des 8 dernières semaines pour chaque jour ;
- les achats futurs des fournisseurs réguliers, au rythme des 90 derniers jours et payés
  selon le délai habituellement constaté.
Chaque composante est indiquée séparément pour que l'hypothèse puisse être discutée.
"""

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.categories import BY_KEY
from app.extraction.text import name_key
from app.finance.data import ZERO, Dataset, f, money
from app.models import BankTransaction

HORIZON = 90
RECEIPT_CATEGORIES = ("encaissement_cb", "encaissement_especes", "encaissement_titres")
MONTH_WORDS = {
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
    "sepa",
    "vir",
    "prlv",
    "fact",
    "facture",
    "ech",
    "echeance",
}


def signature(label: str) -> str:
    words = [w for w in name_key(label).split() if not re.search(r"\d", w) and w not in MONTH_WORDS]
    return " ".join(words[:4])


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    import calendar

    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def recurring_charges(ds: Dataset, as_of: date, excluded_parties: set) -> list[dict[str, Any]]:
    """Prélèvements et virements récurrents (mensuels ou trimestriels) sans facture associée."""
    groups: dict[tuple[str, str], list[BankTransaction]] = defaultdict(list)
    for tx in ds.txs:
        if tx.amount >= 0 or tx.invoice_id is not None or tx.party_id in excluded_parties:
            continue
        if tx.booked_on < as_of - timedelta(days=200):
            continue
        groups[(tx.category, signature(tx.label))].append(tx)
    out = []
    for (category, sig), txs in groups.items():
        if len(txs) < 3 or not sig:
            continue
        dates = sorted({t.booked_on for t in txs})
        if len(dates) < 3:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        gap = statistics.median(gaps)
        if 25 <= gap <= 35:
            period = 1
        elif 80 <= gap <= 100:
            period = 3
        else:
            continue
        last_amounts = [-t.amount for t in sorted(txs, key=lambda t: t.booked_on)[-3:]]
        amount = Decimal(statistics.median(last_amounts)).quantize(Decimal("0.01"))
        if dates[-1] < as_of - timedelta(days=45 * period):
            continue  # n'apparaît plus : probablement arrêté
        out.append(
            {
                "category": category,
                "label": txs[-1].label,
                "signature": sig,
                "amount": amount,
                "period_months": period,
                "last_date": dates[-1],
                "occurrences": len(txs),
            }
        )
    return out


def forecast(ds: Dataset) -> dict[str, Any]:
    with_balance = [t for t in ds.txs if t.balance is not None]
    if not with_balance:
        return {
            "available": False,
            "reason": "Importez un relevé bancaire contenant une colonne « Solde » pour calculer la trésorerie.",
        }
    last = max(with_balance, key=lambda t: (t.booked_on, t.id))
    as_of, balance = last.booked_on, last.balance
    end = as_of + timedelta(days=HORIZON)
    notes: list[str] = []

    # Historique : solde de fin de journée sur 120 jours.
    closing: dict[date, Decimal] = {}
    for t in with_balance:
        closing[t.booked_on] = t.balance  # les opérations sont triées : la dernière du jour gagne
    history, running = [], None
    for i in range(120, -1, -1):
        d = as_of - timedelta(days=i)
        running = closing.get(d, running)
        if running is not None:
            history.append({"date": d.isoformat(), "balance": f(running)})

    inflow: dict[date, Decimal] = defaultdict(lambda: ZERO)
    outflow: dict[date, Decimal] = defaultdict(lambda: ZERO)
    events: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []

    def event(day: date, label: str, amount: Decimal, kind: str, certainty: str, **ref) -> None:
        if not (as_of < day <= end):
            return
        (inflow if amount > 0 else outflow)[day] += abs(amount)
        events.append(
            {"date": day.isoformat(), "label": label, "amount": f(amount), "kind": kind, "certainty": certainty, **ref}
        )

    # 1. Recettes courantes (caisse) ---------------------------------------------------------
    window_start = as_of - timedelta(days=55)
    receipts = [t for t in ds.txs if t.amount > 0 and t.category in RECEIPT_CATEGORIES and t.booked_on >= window_start]
    by_weekday: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for t in receipts:
        by_weekday[t.booked_on.weekday()] += t.amount
    weeks = Decimal(8)
    projected_receipts = ZERO
    for i in range(1, HORIZON + 1):
        d = as_of + timedelta(days=i)
        amount = by_weekday[d.weekday()] / weeks
        inflow[d] += amount
        projected_receipts += amount
    components.append(
        {
            "key": "receipts",
            "label": "Encaissements de caisse attendus",
            "amount": f(projected_receipts),
            "certainty": "estimated",
            "detail": f"Moyenne par jour de la semaine des {len(receipts)} encaissements (carte, espèces, titres) des 8 dernières semaines.",
        }
    )
    if receipts:
        notes.append("Les recettes futures reprennent le niveau des 8 dernières semaines, sans effet de saison.")

    # 2. Factures clients à encaisser -------------------------------------------------------
    receivable_total, risky = ZERO, []
    for inv in ds.sales_invoices:
        if inv.paid_on or not inv.total_ttc or not inv.due_date:
            continue
        overdue = (as_of - inv.due_date).days
        if overdue > 30:
            risky.append(
                {
                    "invoice_id": str(inv.id),
                    "document_id": str(inv.document_id),
                    "number": inv.number,
                    "party": ds.party_name(inv.party_id),
                    "amount": f(inv.total_ttc),
                    "overdue_days": overdue,
                }
            )
            continue
        when = inv.due_date if inv.due_date > as_of else as_of + timedelta(days=7)
        receivable_total += inv.total_ttc
        event(
            when,
            f"Règlement attendu : {ds.party_name(inv.party_id)} ({inv.number})",
            inv.total_ttc,
            "receivable",
            "known",
            document_id=str(inv.document_id),
        )
    components.append(
        {
            "key": "receivables",
            "label": "Factures clients à encaisser",
            "amount": f(receivable_total),
            "certainty": "known",
            "detail": "À leur échéance ; une semaine de délai si l'échéance est passée de moins de 30 jours.",
        }
    )
    if risky:
        total = sum((Decimal(str(r["amount"])) for r in risky), ZERO)
        notes.append(
            f"{len(risky)} facture(s) client en retard de plus de 30 jours ({money(total)}) ne sont pas comptées : "
            "leur encaissement est incertain."
        )

    # 3. Factures fournisseurs à payer ---------------------------------------------------------
    payable_total = ZERO
    for inv in ds.purchases:
        if inv.paid_on or not inv.total_ttc or inv.total_ttc <= 0:
            continue
        due = inv.due_date or (inv.issue_date + timedelta(days=30) if inv.issue_date else None)
        if due is None or (inv.issue_date and inv.issue_date < as_of - timedelta(days=180)):
            continue  # trop ancienne pour être encore due : probablement réglée autrement
        when = due if due > as_of else as_of + timedelta(days=1)
        payable_total += inv.total_ttc
        event(
            when,
            f"{ds.party_name(inv.party_id)} ({inv.number or 'sans numéro'})",
            -inv.total_ttc,
            "invoice",
            "known",
            document_id=str(inv.document_id),
        )
    components.append(
        {
            "key": "payables",
            "label": "Factures fournisseurs à payer",
            "amount": f(-payable_total),
            "certainty": "known",
            "detail": "Factures importées non encore rapprochées d'un paiement, à leur échéance.",
        }
    )

    # 4. Achats futurs des fournisseurs réguliers ----------------------------------------------
    regular: dict = defaultdict(list)
    for inv in ds.purchases:
        if inv.issue_date and inv.total_ttc and inv.party_id and inv.category != "immobilisations":
            if as_of - timedelta(days=90) < inv.issue_date <= as_of:
                regular[inv.party_id].append(inv)
    projected_purchases = ZERO
    supplier_rows = []
    for party_id, invoices in regular.items():
        if len(invoices) < 3:
            continue
        everything = [i for i in ds.purchases if i.party_id == party_id]
        delays = [(i.paid_on - i.issue_date).days for i in everything if i.paid_on and i.issue_date]
        if not delays:
            delays = [(i.due_date - i.issue_date).days for i in everything if i.due_date and i.issue_date]
        delay = int(statistics.median(delays)) if delays else 30
        rate = sum((i.total_ttc for i in invoices), ZERO) / 90
        total = rate * max(0, HORIZON - delay)
        for i in range(delay + 1, HORIZON + 1):
            outflow[as_of + timedelta(days=i)] += rate
        projected_purchases += total
        supplier_rows.append({"party": ds.party_name(party_id), "monthly": f(rate * 30), "delay_days": delay})
    components.append(
        {
            "key": "purchases",
            "label": "Achats futurs des fournisseurs réguliers",
            "amount": f(-projected_purchases),
            "certainty": "estimated",
            "suppliers": sorted(supplier_rows, key=lambda r: -(r["monthly"] or 0)),
            "detail": "Rythme d'achat des 90 derniers jours, payé selon le délai habituel de chaque fournisseur.",
        }
    )

    # 5. Charges récurrentes sans facture --------------------------------------------------------
    recurring_total = ZERO
    recurring = recurring_charges(ds, as_of, excluded_parties=set(regular))
    for rec in recurring:
        nxt = _add_months(rec["last_date"], rec["period_months"])
        while nxt <= as_of:
            nxt = _add_months(nxt, rec["period_months"])
        while nxt <= end:
            label = BY_KEY[rec["category"]].label if rec["category"] in BY_KEY else rec["label"]
            who = re.sub(r"^(PRLV|VIR|PRELEVEMENT|VIREMENT)( SEPA)?\s+", "", rec["label"], flags=re.I)
            who = re.sub(r"\s+\S*\d\S*$", "", who)[:40]
            event(nxt, f"{label} · {who}", -rec["amount"], "recurring", "estimated")
            recurring_total += rec["amount"]
            nxt = _add_months(nxt, rec["period_months"])
    components.append(
        {
            "key": "recurring",
            "label": "Charges récurrentes (salaires, loyer, cotisations…)",
            "amount": f(-recurring_total),
            "certainty": "estimated",
            "count": len(recurring),
            "detail": "Opérations mensuelles ou trimestrielles repérées dans le relevé, au montant médian des trois dernières.",
        }
    )

    # Solde jour par jour ----------------------------------------------------------------------
    points, running = [], balance
    low = (as_of, balance)
    for i in range(1, HORIZON + 1):
        d = as_of + timedelta(days=i)
        running = running + inflow[d] - outflow[d]
        points.append({"date": d.isoformat(), "balance": f(running), "inflow": f(inflow[d]), "outflow": f(outflow[d])})
        if running < low[1]:
            low = (d, running)

    recent_out = sum((-t.amount for t in ds.txs if t.amount < 0 and t.booked_on > as_of - timedelta(days=90)), ZERO)
    daily_out = recent_out / 90
    threshold = (daily_out * 10 / 100).quantize(Decimal(1)) * 100

    events.sort(key=lambda e: e["date"])
    stale = (ds.today - as_of).days
    if stale > 7:
        notes.insert(
            0,
            f"Le dernier relevé bancaire date du {as_of.strftime('%d/%m/%Y')} : importez un relevé plus récent pour fiabiliser la prévision.",
        )
    return {
        "available": True,
        "as_of": as_of.isoformat(),
        "balance": f(balance),
        "horizon_days": HORIZON,
        "threshold": f(threshold),
        "threshold_formula": f"10 jours de dépenses moyennes ({money(daily_out)} par jour sur les 90 derniers jours)",
        "history": history,
        "forecast": points,
        "low_point": {"date": low[0].isoformat(), "balance": f(low[1])},
        "end_balance": f(running),
        "components": components,
        "events": events,
        "notes": notes,
        "risky_receivables": risky,
    }
