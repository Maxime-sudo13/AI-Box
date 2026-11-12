"""Détection des anomalies et opportunités, par règles explicites.

Chaque alerte cite les documents et opérations qui la justifient, détaille son calcul et,
quand c'est possible, chiffre son impact. Un impact est toujours présenté comme une
estimation, avec sa formule : le système n'invente jamais une économie.
"""

import hashlib
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.text import fold, name_key
from app.finance.data import ZERO, Dataset, f, money, month_of
from app.finance.engine import Month, month_label
from app.models import AnomalyReview, Document, Invoice

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
FIXED_CATEGORIES = {"energie", "telecom", "logiciels", "assurance", "loyer", "honoraires", "blanchisserie", "entretien"}
GENERIC_TOKENS = {
    "abonnement",
    "licence",
    "mensuel",
    "mensuelle",
    "mois",
    "maintenance",
    "assistance",
    "service",
    "services",
    "forfait",
    "pro",
    "professionnel",
    "professionnelle",
    "terminal",
    "terminaux",
    "et",
    "pour",
    "avec",
    "option",
    "options",
}


def num(v: Decimal | float | None, decimals: int = 0) -> str:
    """Nombre au format français : 1 234,56."""
    if v is None:
        return "—"
    value = Decimal(str(v))
    text = f"{abs(value):,.{decimals}f}".replace(",", "\u202f").replace(".", ",")
    return f"{'−' if value < 0 else ''}{text}"


def pct(v: Decimal | float | None, decimals: int = 1) -> str:
    return "—" if v is None else f"{num(v, decimals)} %"


def inv_ref(ds: Dataset, inv: Invoice) -> dict[str, Any]:
    return {
        "invoice_id": str(inv.id),
        "document_id": str(inv.document_id),
        "number": inv.number,
        "party": ds.party_name(inv.party_id),
        "date": inv.issue_date.isoformat() if inv.issue_date else None,
        "amount": f(inv.total_ttc),
    }


def tx_ref(tx) -> dict[str, Any]:
    return {"id": tx.id, "date": tx.booked_on.isoformat(), "label": tx.label, "amount": f(tx.amount)}


def alert(kind: str, key: str, severity: str, title: str, summary: str, **rest) -> dict[str, Any]:
    return {
        "fingerprint": f"{kind}:{key}"[:120],
        "kind": kind,
        "severity": severity,
        "title": title,
        "summary": summary,
        "details": rest.pop("details", []),
        "impact": rest.pop("impact", None),
        "figures": rest.pop("figures", []),
        "invoices": rest.pop("invoices", []),
        "transactions": rest.pop("transactions", []),
        **rest,
    }


# --- Détecteurs ------------------------------------------------------------------------------


def price_increases(ds: Dataset) -> list[dict[str, Any]]:
    today = ds.today
    groups: dict[tuple, list] = defaultdict(list)
    for inv in ds.purchases:
        if not inv.issue_date or not inv.party_id:
            continue
        for line in inv.lines:
            if line.product_key and line.unit_price and line.unit_price > 0 and line.quantity:
                groups[(inv.party_id, line.product_key, (line.unit or "").lower())].append((inv.issue_date, line, inv))
    out = []
    for (party_id, key, unit), points in groups.items():
        points.sort(key=lambda p: p[0])
        recent = [p for p in points if p[0] >= today - timedelta(days=45)]
        reference = [p for p in points if today - timedelta(days=365) <= p[0] < today - timedelta(days=90)]
        if len(recent) < 2 or len(reference) < 3:
            continue
        ref_price = Decimal(statistics.median([p[1].unit_price for p in reference]))
        new_price = Decimal(statistics.median([p[1].unit_price for p in recent]))
        change = (new_price - ref_price) / ref_price
        if change < Decimal("0.07"):
            continue
        since = next(
            (
                p[0]
                for p in points
                if p[1].unit_price >= ref_price * Decimal("1.05")
                and all(q[1].unit_price >= ref_price * Decimal("1.03") for q in points if q[0] >= p[0])
            ),
            recent[0][0],
        )
        qty_90 = sum((p[1].quantity for p in points if p[0] >= today - timedelta(days=90)), ZERO)
        annual = (new_price - ref_price) * qty_90 * Decimal(365) / Decimal(90)
        severity = "high" if annual >= 1500 else "medium" if annual >= 400 else "low"
        description = recent[-1][1].description
        party = ds.party_name(party_id)
        unit_label = f" / {unit}" if unit else ""
        out.append(
            alert(
                "price_increase",
                f"{party_id}:{key}:{since.isoformat()[:7]}",
                severity,
                f"{description} : +{f(change * 100, 0):.0f} % chez {party}",
                f"Le prix unitaire est passé de {money(ref_price, 2)} à {money(new_price, 2)}{unit_label} depuis le "
                f"{since.strftime('%d/%m/%Y')}, sans que la quantité achetée ne diminue.",
                details=[
                    f"Prix de référence : médiane de {len(reference)} achats entre 3 et 12 mois en arrière.",
                    f"Prix actuel : médiane des {len(recent)} achats des 45 derniers jours.",
                    "Piste : demander une justification, comparer avec un autre fournisseur, ou ajuster le prix de vente des plats concernés.",
                ],
                impact={
                    "amount": f(annual),
                    "label": "surcoût annuel estimé",
                    "formula": f"({money(new_price, 2)} − {money(ref_price, 2)}) × {num(qty_90, 1)}{' ' + unit if unit else ''} "
                    "(quantité achetée en 90 jours) × 365 / 90",
                },
                figures=[
                    {"label": "Prix de référence", "value": f(ref_price), "unit": "eur"},
                    {"label": "Prix actuel", "value": f(new_price), "unit": "eur"},
                    {"label": "Hausse", "value": f(change * 100, 1), "unit": "pct"},
                ],
                series=[{"date": p[0].isoformat(), "value": f(p[1].unit_price, 4)} for p in points[-30:]],
                invoices=[inv_ref(ds, p[2]) for p in recent[-4:]],
                module="achats",
            )
        )
    return out


def duplicates(db: Session, ds: Dataset) -> list[dict[str, Any]]:
    out = []
    rows = db.execute(
        select(Document, Invoice)
        .join(Invoice)
        .where(Document.company_id == ds.company.id, Document.status == "duplicate")
    ).all()
    for doc, inv in rows:
        original = db.get(Document, doc.duplicate_of_id) if doc.duplicate_of_id else None
        out.append(
            alert(
                "duplicate",
                str(doc.id),
                "low",
                f"Facture reçue deux fois : {ds.party_name(inv.party_id)} n° {inv.number}",
                f"« {doc.filename} » reprend une facture déjà importée"
                + (f" (« {original.filename} »)" if original else "")
                + ". Elle a été écartée des calculs pour ne pas la compter, ni la payer, deux fois.",
                impact={
                    "amount": f(inv.total_ttc),
                    "label": "double paiement évité",
                    "formula": "Montant TTC de la facture en double",
                },
                invoices=[inv_ref(ds, inv) | {"document_id": str(doc.id)}],
                module="documents",
            )
        )

    by_party: dict = defaultdict(list)
    for inv in ds.purchases:
        if inv.party_id and inv.total_ttc and inv.issue_date:
            by_party[inv.party_id].append(inv)
    for invoices in by_party.values():
        invoices.sort(key=lambda i: i.issue_date)
        for a, b in zip(invoices, invoices[1:], strict=False):
            if a.total_ttc == b.total_ttc and (b.issue_date - a.issue_date).days <= 3 and a.number != b.number:
                out.append(
                    alert(
                        "possible_duplicate",
                        f"{a.id}:{b.id}",
                        "medium",
                        f"Possible double facturation : {ds.party_name(a.party_id)}",
                        f"Deux factures de {money(a.total_ttc)} à moins de trois jours d'intervalle, avec des numéros différents.",
                        impact={
                            "amount": f(b.total_ttc),
                            "label": "à vérifier",
                            "formula": "Montant de la seconde facture",
                        },
                        invoices=[inv_ref(ds, a), inv_ref(ds, b)],
                        module="documents",
                    )
                )
    return out


def unusual_invoices(db: Session, ds: Dataset) -> list[dict[str, Any]]:
    out = []
    by_party: dict = defaultdict(list)
    for inv in ds.purchases:
        if inv.party_id and inv.total_ttc and inv.issue_date and inv.category != "immobilisations":
            by_party[inv.party_id].append(inv)
    for party_id, invoices in by_party.items():
        if len(invoices) < 6:
            continue
        for inv in invoices:
            if inv.issue_date < ds.today - timedelta(days=120):
                continue
            others = [
                i.total_ttc for i in invoices if i is not inv and i.issue_date >= inv.issue_date - timedelta(days=365)
            ]
            if len(others) < 5:
                continue
            median = Decimal(statistics.median(others))
            if inv.total_ttc < median * Decimal("1.5") or inv.total_ttc - median < 150:
                continue
            ratio = inv.total_ttc / median
            fixed = inv.category in FIXED_CATEGORIES
            doc = db.get(Document, inv.document_id)
            excerpt = fold((doc.extraction or {}).get("excerpt", "")) if doc else ""
            details = [f"Montant habituel : médiane de {len(others)} factures sur 12 mois."]
            if "estim" in excerpt:
                details.insert(
                    0,
                    "La facture indique une consommation estimée : un relevé réel du compteur peut la faire corriger.",
                )
            if fixed:
                details.append(
                    "Pour une charge habituellement stable, un tel écart mérite une vérification avant paiement."
                )
            else:
                details.append(
                    "S'il s'agit d'une commande exceptionnelle prévue (événement, fêtes), cette alerte peut être ignorée."
                )
            out.append(
                alert(
                    "unusual_invoice",
                    str(inv.id),
                    "medium" if fixed else "low",
                    f"Facture inhabituelle : {ds.party_name(party_id)} ({money(inv.total_ttc)})",
                    f"Cette facture du {inv.issue_date.strftime('%d/%m/%Y')} est {num(ratio, 1)} fois plus élevée que d'habitude ({money(median)}).",
                    details=details,
                    impact={
                        "amount": f(inv.total_ttc - median),
                        "label": "écart avec une facture habituelle",
                        "formula": f"{money(inv.total_ttc, 2)} − {money(median, 2)} (médiane)",
                    },
                    figures=[
                        {"label": "Montant", "value": f(inv.total_ttc), "unit": "eur"},
                        {"label": "Habituellement", "value": f(median), "unit": "eur"},
                    ],
                    invoices=[inv_ref(ds, inv)],
                    module="finance",
                )
            )
    return out


def redundant_subscriptions(ds: Dataset) -> list[dict[str, Any]]:
    """Deux fournisseurs facturent chaque mois un service de même nature."""
    recent: dict = defaultdict(list)
    for inv in ds.purchases:
        if (
            inv.category in ("logiciels", "telecom")
            and inv.issue_date
            and inv.issue_date >= ds.today - timedelta(days=70)
        ):
            recent[inv.party_id].append(inv)
    tokens: dict = {}
    for party_id, invoices in recent.items():
        if len(invoices) < 2 or party_id is None:
            continue
        party_tokens = set(name_key(ds.party_name(party_id)).split())
        words = set()
        for inv in invoices:
            for line in inv.lines:
                words |= {
                    w
                    for w in re.findall(r"[a-z]{4,}", fold(line.description))
                    if w not in GENERIC_TOKENS and w not in party_tokens
                }
        tokens[party_id] = words
    out = []
    ids = sorted(tokens, key=str)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            shared = tokens[a] & tokens[b]
            if len(shared) < 2:
                continue
            first_seen = {
                p: min(inv.issue_date for inv in ds.purchases if inv.party_id == p and inv.issue_date) for p in (a, b)
            }
            older, newer = sorted((a, b), key=lambda p: first_seen[p])
            yearly = sum(
                (
                    inv.total_ht or ZERO
                    for inv in ds.purchases
                    if inv.party_id == older and inv.issue_date and inv.issue_date >= ds.today - timedelta(days=365)
                ),
                ZERO,
            )
            monthly = yearly / 12
            nature = " ".join(sorted(shared))
            out.append(
                alert(
                    "redundant_subscription",
                    f"{older}:{newer}",
                    "medium",
                    f"Deux abonnements similaires : {ds.party_name(older)} et {ds.party_name(newer)}",
                    f"Les deux fournisseurs facturent chaque mois un service du même type ({nature}). "
                    f"{ds.party_name(newer)} est facturé depuis le {first_seen[newer].strftime('%d/%m/%Y')} ; "
                    f"{ds.party_name(older)} continue de l'être.",
                    details=[
                        "S'il s'agit d'un remplacement, l'ancien abonnement n'a peut-être pas été résilié.",
                        "Vérifiez le préavis de résiliation dans le contrat avant d'agir.",
                    ],
                    impact={
                        "amount": f(yearly),
                        "label": "économie annuelle possible (HT)",
                        "formula": f"Coût de {ds.party_name(older)} sur 12 mois (≈ {money(monthly, 2)} HT par mois)",
                    },
                    invoices=[
                        inv_ref(ds, i) for i in sorted(recent[older] + recent[newer], key=lambda i: i.issue_date)
                    ][-4:],
                    module="contrats",
                )
            )
    return out


def overdue_receivables(ds: Dataset) -> list[dict[str, Any]]:
    out = []
    for inv in ds.sales_invoices:
        if inv.paid_on or not inv.due_date or not inv.total_ttc or inv.due_date >= ds.today:
            continue
        days = (ds.today - inv.due_date).days
        severity = "high" if days > 60 or inv.total_ttc >= 2000 else "medium"
        out.append(
            alert(
                "overdue_receivable",
                str(inv.id),
                severity,
                f"Facture impayée : {ds.party_name(inv.party_id)} ({money(inv.total_ttc)})",
                f"Échue depuis {days} jours (le {inv.due_date.strftime('%d/%m/%Y')}). Aucun règlement correspondant n'apparaît dans le relevé bancaire.",
                details=[
                    "Une relance écrite est recommandée ; au-delà de 60 jours, envisagez une mise en demeure.",
                    "Pénalités de retard et indemnité forfaitaire de 40 € sont exigibles entre professionnels.",
                ],
                impact={"amount": f(inv.total_ttc), "label": "à encaisser", "formula": "Montant TTC de la facture"},
                figures=[{"label": "Retard", "value": days, "unit": "days"}],
                invoices=[inv_ref(ds, inv)],
                module="clients",
                action="reminder",
            )
        )
    return out


def missing_documents(ds: Dataset, months: dict[date, Month]) -> list[dict[str, Any]]:
    out = []
    invoiced: dict = defaultdict(list)
    for inv in ds.purchases:
        if inv.party_id:
            invoiced[inv.party_id].append(inv)
    unmatched: dict = defaultdict(list)
    for tx in ds.txs:
        if tx.amount < 0 and tx.invoice_id is None and tx.party_id in invoiced and len(invoiced[tx.party_id]) >= 3:
            unmatched[tx.party_id].append(tx)
    for party_id, txs in unmatched.items():
        invoices = invoiced[party_id]
        rates = [i.total_tva / i.total_ht for i in invoices if i.total_ht and i.total_tva]
        rate = Decimal(statistics.median(rates)) if rates else Decimal("0.2")
        total = sum((-t.amount for t in txs), ZERO)
        vat = total * rate / (1 + rate)
        key = hashlib.sha1(",".join(str(t.id) for t in txs).encode()).hexdigest()[:12]
        out.append(
            alert(
                "missing_invoice",
                f"{party_id}:{key}",
                "medium",
                f"{len(txs)} paiement(s) à {ds.party_name(party_id)} sans facture",
                f"{money(total)} payés sans facture correspondante dans le boîtier. Sans justificatif, "
                "la dépense n'est pas justifiée et la TVA ne peut pas être récupérée.",
                details=["Demandez un duplicata au fournisseur puis importez-le : le rapprochement sera automatique."],
                impact={
                    "amount": f(vat),
                    "label": "TVA non récupérable en l'état",
                    "formula": f"{money(total, 2)} TTC × {pct(rate * 100)} / (1 + {pct(rate * 100)})",
                },
                transactions=[tx_ref(t) for t in txs],
                module="documents",
            )
        )

    # Fournisseur réguliers silencieux le mois dernier.
    completed = sorted(k for k in months if k < month_of(ds.today))
    if len(completed) >= 4:
        last, previous = completed[-1], completed[-4:-1]
        for party_id, invoices in invoiced.items():
            months_seen = {month_of(i.issue_date) for i in invoices if i.issue_date}
            if all(p in months_seen for p in previous) and last not in months_seen:
                out.append(
                    alert(
                        "silent_supplier",
                        f"{party_id}:{last.isoformat()[:7]}",
                        "low",
                        f"Aucune facture de {ds.party_name(party_id)} en {month_label(last)}",
                        "Ce fournisseur facture chaque mois. La facture a peut-être été oubliée lors de l'import.",
                        module="documents",
                    )
                )
    return out


def food_cost_drift(ds: Dataset, months: dict[date, Month]) -> list[dict[str, Any]]:
    if not ds.is_restaurant:
        return []
    completed = [k for k in sorted(months) if k < month_of(ds.today) and months[k].food_ht]
    if len(completed) < 4:
        return []
    last = completed[-1]
    previous = completed[-4:-1]
    m = months[last]
    now = m.charges.get("alimentaire", ZERO) / m.food_ht * 100
    ref_food = sum((months[k].charges.get("alimentaire", ZERO) for k in previous), ZERO)
    ref_sales = sum((months[k].food_ht for k in previous), ZERO)
    if not ref_sales:
        return []
    ref = ref_food / ref_sales * 100
    drift = now - ref
    if drift < 2:
        return []
    annual = drift / 100 * m.food_ht * 12

    # Contribution de chaque fournisseur : part de ses achats dans le CA nourriture.
    def supplier_share(month_keys: list[date]) -> dict:
        totals: dict = defaultdict(lambda: ZERO)
        sales = sum((months[k].food_ht for k in month_keys), ZERO)
        for inv in ds.purchases:
            if (
                inv.category == "alimentaire"
                and inv.issue_date
                and month_of(inv.issue_date) in month_keys
                and inv.total_ht
            ):
                totals[inv.party_id] += inv.total_ht
        return {p: v / sales * 100 for p, v in totals.items()} if sales else {}

    share_now, share_ref = supplier_share([last]), supplier_share(previous)
    contributions = sorted(
        ((p, share_now.get(p, ZERO) - share_ref.get(p, ZERO)) for p in set(share_now) | set(share_ref)),
        key=lambda kv: -kv[1],
    )[:3]
    details = [f"{ds.party_name(p)} : +{num(d, 1)} point(s) de CA nourriture" for p, d in contributions if d > 0.3]
    covers_now = m.covers
    covers_ref = sum((months[k].covers for k in previous), 0) / len(previous)
    return [
        alert(
            "food_cost_drift",
            last.isoformat()[:7],
            "high" if drift >= 3 else "medium",
            f"Coût matière en hausse : {pct(now)} en {month_label(last)}",
            f"Les achats alimentaires représentent {pct(now)} du chiffre d'affaires nourriture, contre {pct(ref)} "
            "en moyenne sur les trois mois précédents.",
            details=[
                "Principales contributions à la hausse :",
                *details,
                f"Fréquentation : {covers_now} couverts contre {covers_ref:.0f} en moyenne : la hausse ne s'explique pas par l'activité."
                if covers_now <= covers_ref * 1.05
                else "La fréquentation a aussi augmenté.",
                "Pistes : vérifier les grammages et les pertes, renégocier les prix, revoir la carte.",
            ],
            impact={
                "amount": f(annual),
                "label": "coût annuel de la dérive",
                "formula": f"({pct(now)} − {pct(ref)}) × {money(m.food_ht)} de CA nourriture × 12",
            },
            figures=[
                {"label": f"Coût matière {month_label(last)}", "value": f(now, 1), "unit": "pct"},
                {"label": "Moyenne des 3 mois précédents", "value": f(ref, 1), "unit": "pct"},
            ],
            module="finance",
        )
    ]


def treasury_tension(treasury: dict[str, Any]) -> list[dict[str, Any]]:
    if not treasury.get("available"):
        return []
    low, threshold = treasury["low_point"], treasury["threshold"]
    if low["balance"] >= threshold:
        return []
    day = date.fromisoformat(low["date"])
    severity = "high" if low["balance"] < threshold / 2 else "medium"
    big = sorted(
        (e for e in treasury["events"] if e["amount"] < 0 and e["date"] <= low["date"]), key=lambda e: e["amount"]
    )[:4]
    return [
        alert(
            "treasury_tension",
            low["date"][:7],
            severity,
            f"Trésorerie tendue prévue le {day.strftime('%d/%m/%Y')}",
            f"Le solde prévu descendrait à {money(low['balance'])}, sous le seuil de vigilance de "
            f"{money(threshold)}, soit {treasury['threshold_formula']}.",
            details=[
                "Principales sorties d'ici là :",
                *[
                    f"{e['label']} : {money(e['amount'])} le {date.fromisoformat(e['date']).strftime('%d/%m')}"
                    for e in big
                ],
                "Pistes : décaler une commande non urgente, relancer les factures clients en retard, négocier un délai fournisseur.",
            ],
            impact={
                "amount": f(threshold - low["balance"]),
                "label": "manque par rapport au seuil",
                "formula": f"{money(threshold)} − {money(low['balance'])}",
            },
            module="finance",
        )
    ]


def detect(db: Session, ds: Dataset, months: dict[date, Month], treasury: dict[str, Any]) -> list[dict[str, Any]]:
    found = [
        *treasury_tension(treasury),
        *food_cost_drift(ds, months),
        *price_increases(ds),
        *overdue_receivables(ds),
        *redundant_subscriptions(ds),
        *unusual_invoices(db, ds),
        *missing_documents(ds, months),
        *duplicates(db, ds),
    ]
    reviews = {
        r.fingerprint: r for r in db.scalars(select(AnomalyReview).where(AnomalyReview.company_id == ds.company.id))
    }
    for item in found:
        review = reviews.get(item["fingerprint"])
        item["status"] = review.status if review else "open"
        item["review_note"] = review.note if review else None
        item["reviewed_at"] = review.reviewed_at.isoformat() if review else None
    found.sort(
        key=lambda a: (a["status"] != "open", SEVERITY_RANK[a["severity"]], -((a["impact"] or {}).get("amount") or 0))
    )
    return found
