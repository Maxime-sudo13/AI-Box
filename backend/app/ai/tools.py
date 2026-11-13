"""Outils d'analyse des agents spécialisés.

Chaque outil lit le résultat du moteur de calcul (jamais les documents bruts), enregistre
les faits qu'il utilise et rédige quelques phrases. Le conseiller assemble ces phrases ; le
modèle de langage, s'il est disponible, ne fait que les reformuler.
"""

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.categories import BY_KEY
from app.finance.data import ZERO, Dataset, add_months, month_of
from app.finance.engine import Month, month_label

from .facts import Composer

D = Decimal


@dataclass
class Context:
    ds: Dataset
    months: dict[date, Month]
    treasury: dict[str, Any]
    alerts: list[dict[str, Any]]
    month: date  # mois analysé

    @property
    def complete(self) -> list[date]:
        return sorted(k for k in self.months if k < month_of(self.ds.today))

    def m(self, key: date) -> Month:
        return self.months.get(key) or Month(key)

    @property
    def open_alerts(self) -> list[dict[str, Any]]:
        return [a for a in self.alerts if a["status"] == "open"]


def de(label: str) -> str:
    """« de septembre 2026 », « d’octobre 2026 », « d’août 2026 »."""
    return f"d’{label}" if label[:1] in "aeiouyhâéèêàù" else f"de {label}"


def _link_month(month: date) -> str:
    return f"/?mois={month.isoformat()[:7]}"


def _ratio(a: Decimal, b: Decimal) -> Decimal | None:
    return a / b * 100 if b else None


def _pct_change(new: Decimal, old: Decimal) -> Decimal | None:
    return (new - old) / abs(old) * 100 if old else None


# --- Agent financier -------------------------------------------------------------------------


def month_summary(c: Composer, ctx: Context, **_: Any) -> None:
    key = ctx.month
    m, prev = ctx.m(key), ctx.m(add_months(key, -1))
    label = month_label(key)
    link = _link_month(key)
    lines = [
        f"Chiffre d'affaires HT {de(label)} : {c.fact(f'rev:{key}', f'Chiffre d’affaires HT {label}', m.revenue, source='journal de caisse et factures de vente', link=link)}"
        + (
            f", contre {c.fact(f'rev:{prev.start}', f'Chiffre d’affaires HT {month_label(prev.start)}', prev.revenue, link=_link_month(prev.start))} le mois précédent."
            if prev.revenue
            else "."
        ),
        f"EBE estimé : {c.fact(f'ebe:{key}', f'EBE estimé {label}', m.ebe, source='compte de résultat du mois : caisse, factures et relevé bancaire', link=link)}, soit une marge de "
        f"{c.fact(f'ebe_pct:{key}', f'Marge d’EBE {label}', _ratio(m.ebe, m.revenue), 'pct', link=link)}.",
    ]
    if m.food_ht:
        food = _ratio(m.charges.get("alimentaire", ZERO), m.food_ht)
        lines.append(
            f"Coût matière cuisine : {c.fact(f'food:{key}', f'Coût matière cuisine {label}', food, 'pct', source='factures alimentaires ÷ CA nourriture du journal de caisse', link=link)}."
        )
    if m.drinks_ht:
        drinks = _ratio(m.charges.get("boissons", ZERO), m.drinks_ht)
        lines.append(
            f"Coût matière boissons : {c.fact(f'drinks:{key}', f'Coût matière boissons {label}', drinks, 'pct', source='factures de boissons ÷ CA boissons du journal de caisse', link=link)}."
        )
    payroll = m.group_total("personnel")
    lines.append(
        f"Masse salariale : {c.fact(f'pay:{key}', f'Masse salariale {label}', payroll, source='relevé bancaire : salaires, rémunération du gérant et cotisations', link=link)}, soit "
        f"{c.fact(f'paypct:{key}', f'Masse salariale en % du CA {label}', _ratio(payroll, m.revenue), 'pct', link=link)} du chiffre d'affaires."
    )
    if m.covers:
        lines.append(
            f"{c.fact(f'cov:{key}', f'Couverts servis {label}', m.covers, 'count', source='journal de caisse')} couverts, ticket moyen de "
            f"{c.fact(f'ticket:{key}', f'Ticket moyen TTC {label}', m.sales_ttc / m.covers, source='journal de caisse')}."
        )
    c.section(f"Le mois {de(label)}", lines)


def profit_change(c: Composer, ctx: Context, **kwargs: Any) -> None:
    key, prev_key = ctx.month, add_months(ctx.month, -1)
    m, p = ctx.m(key), ctx.m(prev_key)
    if not p.revenue:
        return c.section("Évolution du résultat", ["Pas de mois précédent pour comparer."])
    delta = m.ebe - p.ebe
    verb = "baisse" if delta < 0 else "hausse"
    question = kwargs.get("question", "")
    lines = []
    if delta > 0 and re.search(r"diminu|baiss|chut|recul", question):
        lines.append(
            f"Bonne nouvelle : l’EBE {de(month_label(key))} n’a pas baissé, il a augmenté par rapport au mois précédent."
        )
    elif delta < 0 and re.search(r"augment|hausse|progress", question):
        lines.append(
            f"Attention : l’EBE {de(month_label(key))} n’a pas augmenté, il a baissé par rapport au mois précédent."
        )
    lines += [
        f"L'EBE passe de {c.fact(f'ebe:{prev_key}', f'EBE estimé {month_label(prev_key)}', p.ebe)} en {month_label(prev_key)} à "
        f"{c.fact(f'ebe:{key}', f'EBE estimé {month_label(key)}', m.ebe)} en {month_label(key)}, "
        f"une {verb} de {c.fact('ebe_delta', 'Variation de l’EBE', abs(delta))}."
    ]
    contributions: list[tuple[str, Decimal]] = [("Chiffre d'affaires", m.revenue - p.revenue)]
    for cat in set(m.charges) | set(p.charges):
        if BY_KEY[cat].group in ("matieres", "externes", "impots", "personnel"):
            contributions.append((BY_KEY[cat].label, -(m.charges.get(cat, ZERO) - p.charges.get(cat, ZERO))))
    contributions.sort(key=lambda kv: kv[1] if delta < 0 else -kv[1])
    for i, (name, effect) in enumerate(contributions[:4]):
        if abs(effect) < 50:
            continue
        direction = "pèse" if effect < 0 else "contribue positivement"
        lines.append(f"{name} : {direction} pour {c.fact(f'contrib:{i}', f'Effet sur l’EBE : {name}', abs(effect))}.")
    c.section("Pourquoi le résultat a changé", lines)


def compare_months(c: Composer, ctx: Context, n: int = 3, **_: Any) -> None:
    keys = ctx.complete[-n:]
    lines = []
    for k in keys:
        m = ctx.m(k)
        parts = [
            f"CA {c.fact(f'rev:{k}', f'Chiffre d’affaires HT {month_label(k)}', m.revenue, link=_link_month(k))}",
            f"EBE {c.fact(f'ebe:{k}', f'EBE estimé {month_label(k)}', m.ebe, link=_link_month(k))}",
        ]
        if m.food_ht:
            parts.append(
                f"coût matière {c.fact(f'food:{k}', f'Coût matière cuisine {month_label(k)}', _ratio(m.charges.get('alimentaire', ZERO), m.food_ht), 'pct')}"
            )
        lines.append(f"{month_label(k).capitalize()} : " + ", ".join(parts) + ".")
    if len(keys) >= 2:
        first, last = ctx.m(keys[0]), ctx.m(keys[-1])
        change = _pct_change(last.revenue, first.revenue)
        if change is not None:
            lines.append(
                f"Sur la période, le chiffre d'affaires évolue de {c.fact('rev_trend', 'Évolution du CA sur la période', change, 'pct')}."
            )
    c.section(f"Les {len(keys)} derniers mois", lines)


def year_summary(c: Composer, ctx: Context, **_: Any) -> None:
    keys = ctx.complete[-12:]
    if not keys:
        return
    revenue = sum((ctx.m(k).revenue for k in keys), ZERO)
    ebe = sum((ctx.m(k).ebe for k in keys), ZERO)
    best = max(keys, key=lambda k: ctx.m(k).ebe)
    worst = min(keys, key=lambda k: ctx.m(k).ebe)
    period = f"{month_label(keys[0])} à {month_label(keys[-1])}"
    c.section(
        f"Réalisé sur les 12 derniers mois ({period})",
        [
            f"Chiffre d'affaires HT réalisé : {c.fact('rev12', 'Chiffre d’affaires HT réalisé sur les 12 derniers mois', revenue)}.",
            f"EBE réalisé : {c.fact('ebe12', 'EBE estimé sur 12 mois', ebe)}, soit {c.fact('ebe12pct', 'Marge d’EBE sur 12 mois', _ratio(ebe, revenue), 'pct')} du chiffre d'affaires.",
            f"Meilleur mois : {month_label(best)} ({c.fact(f'ebe:{best}', f'EBE estimé {month_label(best)}', ctx.m(best).ebe)}) ; "
            f"mois le plus faible : {month_label(worst)} ({c.fact(f'ebe:{worst}', f'EBE estimé {month_label(worst)}', ctx.m(worst).ebe)}).",
        ],
    )


def _levers(ctx: Context) -> list[tuple[dict[str, Any], Decimal]]:
    """Gains annuels chiffrés par les alertes ouvertes, sans double comptage."""
    levers = [
        a
        for a in ctx.open_alerts
        if a["impact"] and a["kind"] in ("food_cost_drift", "price_increase", "redundant_subscription")
    ]
    drift = any(a["kind"] == "food_cost_drift" for a in levers)
    return [
        (a, D(str(a["impact"]["amount"])))
        for a in sorted(levers, key=lambda a: -(a["impact"]["amount"] or 0))
        if not (drift and a["kind"] == "price_increase")  # déjà compris dans la dérive du coût matière
    ]


def forecast(c: Composer, ctx: Context, **_: Any) -> None:
    """Prévision de l'année civile en cours et de l'année suivante, sans puis avec les améliorations.

    Méthode volontairement simple et explicable : chaque mois à venir reprend le même mois de
    l'année précédente, corrigé de la tendance récente quand l'historique le permet (6 derniers
    mois comparés aux mêmes mois un an plus tôt, bornée à ±15 %). L'EBE varie avec le chiffre
    d'affaires, diminué du coût des matières.
    """
    keys = ctx.complete
    if len(keys) < 12:
        c.section(
            "Prévision annuelle",
            [f"Il faut au moins 12 mois complets pour prévoir une année (saisonnalité) ; {len(keys)} disponible(s)."],
        )
        return
    last12 = keys[-12:]
    rev12 = sum((ctx.m(k).revenue for k in last12), ZERO)
    ebe12 = sum((ctx.m(k).ebe for k in last12), ZERO)
    mat12 = sum((ctx.m(k).group_total("matieres") for k in last12), ZERO)
    margin = 1 - mat12 / rev12 if rev12 else D(1)  # part de chaque euro de CA qui reste après les matières

    growth = ZERO
    recent, before = keys[-6:], [add_months(k, -12) for k in keys[-6:]]
    prev_rev = sum((ctx.m(k).revenue for k in before), ZERO)
    has_trend = all(k in ctx.months and ctx.m(k).revenue for k in before) and prev_rev
    if has_trend:
        growth = max(D("-0.15"), min(D("0.15"), sum((ctx.m(k).revenue for k in recent), ZERO) / prev_rev - 1))
    hyp = (
        f"tendance des 6 derniers mois : {c.fact('fc_growth', 'Évolution du CA des 6 derniers mois par rapport aux mêmes mois un an plus tôt', growth * 100, 'pct', quality='estimated', source='journal de caisse et factures')}"
        if has_trend
        else "activité identique à celle des 12 derniers mois (moins de 18 mois d'historique : pas encore de tendance mesurable)"
    )

    def project(month: date) -> tuple[Decimal, Decimal] | None:
        """(CA, EBE) prévus pour un mois, d'après le même mois de l'année précédente."""
        ref = add_months(month, -12)
        if ref not in ctx.months or not ctx.m(ref).revenue:
            return None
        rev = ctx.m(ref).revenue * (1 + growth)
        return rev, ctx.m(ref).ebe + (rev - ctx.m(ref).revenue) * margin

    lines = [f"Méthode : chaque mois à venir reprend le même mois de l'an passé ; {hyp}."]

    # Année civile en cours : mois réalisés + mois restants estimés.
    year = keys[-1].year
    done = [k for k in keys if k.year == year]
    todo = [date(year, m, 1) for m in range(1, 13) if date(year, m, 1) not in done]
    projected = [project(m) for m in todo]
    if done and all(projected):
        cal_rev = sum((ctx.m(k).revenue for k in done), ZERO) + sum((p[0] for p in projected if p), ZERO)
        cal_ebe = sum((ctx.m(k).ebe for k in done), ZERO) + sum((p[1] for p in projected if p), ZERO)
        detail = (
            f" ({len(done)} mois réalisés, {len(todo)} estimé(s) d'après les mêmes mois de {year - 1})" if todo else ""
        )
        lines.append(
            f"Année {year} complète{detail} : chiffre d'affaires HT prévu "
            f"{c.fact('fc_cal_rev', f'Prévision du chiffre d’affaires HT {year}', cal_rev, quality='hypothesis', source='mois réalisés + mois restants estimés')}, "
            f"EBE prévu {c.fact('fc_cal_ebe', f'Prévision de l’EBE {year}', cal_ebe, quality='hypothesis', source='mois réalisés + mois restants estimés')}."
        )

    # Année suivante : sans rien changer, puis avec les améliorations détectées.
    nxt = year + 1
    base_rev = rev12 * (1 + growth)
    base_ebe = ebe12 + (base_rev - rev12) * margin
    lines.append(
        f"Année {nxt}, sans rien changer : chiffre d'affaires HT "
        f"{c.fact('fc_next_rev', f'Prévision du chiffre d’affaires HT {nxt}', base_rev, quality='hypothesis', source='12 derniers mois × tendance')}, "
        f"EBE {c.fact('fc_next_ebe', f'Prévision de l’EBE {nxt} sans changement', base_ebe, quality='hypothesis', source='EBE 12 mois + variation du CA × part restant après matières')} "
        f"(marge de {c.fact('fc_next_pct', f'Prévision de la marge d’EBE {nxt} sans changement', _ratio(base_ebe, base_rev), 'pct', quality='hypothesis')})."
    )
    levers = _levers(ctx)
    gains = sum((amount for _, amount in levers), ZERO)
    if levers:
        names = " ; ".join(
            f"{a['title']} ({c.fact(f'alert:{a["fingerprint"]}', a['impact']['label'].capitalize() + ' — ' + a['title'], amount, quality='estimated', source=a['impact']['formula'], link='/alertes#' + a['fingerprint'])})"
            for a, amount in levers
        )
        improved = base_ebe + gains
        lines.append(f"Améliorations détectées et chiffrées : {names}.")
        lines.append(
            f"Année {nxt}, avec ces améliorations menées dès janvier : EBE "
            f"{c.fact('fc_next_ebe_plus', f'Prévision de l’EBE {nxt} avec les améliorations', improved, quality='hypothesis', source='EBE prévu sans changement + gains des améliorations')}, "
            f"soit {c.fact('fc_next_gain', f'Gain d’EBE {nxt} des améliorations', gains, quality='estimated', source='somme des améliorations, sans double comptage')} de plus "
            f"(marge de {c.fact('fc_next_pct_plus', f'Prévision de la marge d’EBE {nxt} avec les améliorations', _ratio(improved, base_rev), 'pct', quality='hypothesis')})."
        )
    covers = sum((ctx.m(k).covers for k in last12), 0)
    if covers:
        lines.append(
            f"Décision tarifaire en plus, si vous la prenez : +1 € TTC par couvert à fréquentation égale ajouterait "
            f"{c.fact('price_lever', 'Gain annuel d’une hausse de 1 € TTC par couvert', D(covers) / D('1.1'), quality='hypothesis', source='couverts sur 12 mois × 1 € ÷ 1,10 (TVA)')} d'EBE."
        )
    lines.append(
        "Ce sont des estimations : elles supposent une saisonnalité semblable, aucun événement exceptionnel, "
        "et des améliorations effectivement mises en œuvre. À revoir chaque mois avec les chiffres réels."
    )
    c.section("Prévision annuelle", lines)


def treasury(c: Composer, ctx: Context, **_: Any) -> None:
    t = ctx.treasury
    if not t.get("available"):
        return c.section("Trésorerie", [t.get("reason", "Trésorerie non disponible.")])
    low_date = date.fromisoformat(t["low_point"]["date"])
    lines = [
        f"Solde bancaire au {date.fromisoformat(t['as_of']).strftime('%d/%m/%Y')} : {c.fact('balance', 'Solde bancaire', t['balance'], source='relevé bancaire', link='/tresorerie')}.",
        f"Point bas prévu le {low_date.strftime('%d/%m/%Y')} : {c.fact('low', 'Point bas prévu à 90 jours', t['low_point']['balance'], quality='estimated', source='prévision de trésorerie', link='/tresorerie')} "
        f"(seuil de vigilance : {c.fact('threshold', 'Seuil de vigilance', t['threshold'], source=t['threshold_formula'], link='/tresorerie')}).",
        f"Solde prévu dans 90 jours : {c.fact('end', 'Solde prévu à 90 jours', t['end_balance'], quality='estimated', source='prévision de trésorerie', link='/tresorerie')}.",
    ]
    big = sorted(
        (e for e in t["events"] if e["amount"] < 0 and e["date"] <= t["low_point"]["date"]), key=lambda e: e["amount"]
    )[:3]
    for i, e in enumerate(big):
        lines.append(
            f"Sortie importante d'ici là : {e['label']}, {c.fact(f'out:{i}', e['label'], -e['amount'], quality='estimated' if e['certainty'] != 'known' else 'confirmed', source='échéancier')} le {date.fromisoformat(e['date']).strftime('%d/%m')}."
        )
    c.section("Trésorerie", lines)


def investment_capacity(c: Composer, ctx: Context, **_: Any) -> None:
    t = ctx.treasury
    if not t.get("available"):
        return c.section("Capacité d'investissement", [t.get("reason", "")])
    capacity = D(str(t["low_point"]["balance"])) - D(str(t["threshold"]))
    if capacity > 0:
        line = (
            f"Vous pouvez mobiliser jusqu'à {c.fact('capacity', 'Montant mobilisable sans passer sous le seuil de vigilance', capacity, quality='estimated', source='point bas prévu − seuil de vigilance', link='/tresorerie')} "
            "aujourd'hui sans que la trésorerie prévue ne passe sous le seuil de vigilance dans les 90 jours."
        )
    else:
        line = (
            f"Aucune marge pour l'instant : le point bas prévu est déjà sous le seuil de vigilance de "
            f"{c.fact('shortfall', 'Manque par rapport au seuil de vigilance', -capacity, quality='estimated', source='seuil de vigilance − point bas prévu', link='/tresorerie')}. "
            "Un investissement devrait être financé (emprunt, crédit-bail) ou décalé."
        )
    c.section(
        "Capacité d'investissement",
        [
            line,
            f"Calcul : point bas prévu {c.fact('low', 'Point bas prévu à 90 jours', t['low_point']['balance'], quality='estimated', source='prévision de trésorerie', link='/tresorerie')} "
            f"moins seuil de vigilance {c.fact('threshold', 'Seuil de vigilance', t['threshold'], source=t['threshold_formula'], link='/tresorerie')}.",
            "Cette marge ne tient pas compte de la saisonnalité ni d'éventuelles dépenses exceptionnelles non encore facturées.",
        ],
    )


def top_charges(c: Composer, ctx: Context, **_: Any) -> None:
    m = ctx.m(ctx.month)
    label = month_label(ctx.month)
    rows = sorted(
        ((k, v) for k, v in m.charges.items() if BY_KEY[k].group in ("matieres", "externes", "personnel", "impots")),
        key=lambda kv: -kv[1],
    )[:5]
    lines = [
        f"{BY_KEY[k].label} : {c.fact(f'charge:{k}:{ctx.month}', f'{BY_KEY[k].label} {label}', v, link=f'/donnees?month={ctx.month.isoformat()[:7]}&category={k}')} "
        f"({c.fact(f'chargepct:{k}', f'{BY_KEY[k].label} en % du CA {label}', _ratio(v, m.revenue), 'pct')} du CA)."
        for k, v in rows
    ]
    c.section(f"Principaux postes de dépense en {label}", lines)


def losses(c: Composer, ctx: Context, **_: Any) -> None:
    leaks = [
        a
        for a in ctx.open_alerts
        if a["impact"]
        and a["kind"]
        in (
            "food_cost_drift",
            "price_increase",
            "redundant_subscription",
            "missing_invoice",
            "unusual_invoice",
            "overdue_receivable",
        )
        and not (a["kind"] == "unusual_invoice" and a["severity"] == "low")
    ]
    leaks.sort(key=lambda a: -(a["impact"]["amount"] or 0))
    lines = [
        f"{a['title']} : {c.fact(f'alert:{a["fingerprint"]}', a['impact']['label'].capitalize() + ' — ' + a['title'], a['impact']['amount'], quality='estimated', source=a['impact']['formula'], link='/alertes#' + a['fingerprint'])}."
        for a in leaks[:5]
    ]
    c.section("Où l'argent se perd ou reste bloqué", lines or ["Aucune fuite identifiée dans les données actuelles."])


def priorities(c: Composer, ctx: Context, n: int = 5, **_: Any) -> None:
    labels = {"high": "prioritaire", "medium": "important", "low": "à noter"}
    lines = []
    for a in ctx.open_alerts[:n]:
        impact = ""
        if a["impact"] and a["impact"]["amount"]:
            impact = (
                " — "
                + a["impact"]["label"]
                + " : "
                + c.fact(
                    f"alert:{a['fingerprint']}",
                    a["impact"]["label"].capitalize() + " — " + a["title"],
                    a["impact"]["amount"],
                    quality="estimated",
                    source=a["impact"]["formula"],
                    link="/alertes#" + a["fingerprint"],
                )
            )
        lines.append(f"({labels[a['severity']]}) {a['title']}{impact}.")
    c.section(f"Les {len(lines)} points prioritaires", lines or ["Aucune alerte ouverte."])


def hiring(c: Composer, ctx: Context, amount: Decimal | None = None, **_: Any) -> None:
    keys = ctx.complete[-12:]
    if not keys:
        return
    revenue = sum((ctx.m(k).revenue for k in keys), ZERO)
    ebe = sum((ctx.m(k).ebe for k in keys), ZERO)
    payroll = sum((ctx.m(k).group_total("personnel") for k in keys), ZERO)
    matieres = sum((ctx.m(k).group_total("matieres") for k in keys), ZERO)
    monthly = amount or D(2800)
    hyp = "valeur indiquée dans votre question" if amount else "hypothèse par défaut, à ajuster"
    annual = monthly * 12
    needed = annual / (1 - matieres / revenue) if revenue and matieres < revenue else None
    lines = [
        f"Coût employeur retenu : {c.fact('hire_cost', 'Coût employeur mensuel du recrutement', monthly, quality='hypothesis', source=hyp)} par mois, "
        f"soit {c.fact('hire_annual', 'Coût employeur annuel du recrutement', annual, quality='hypothesis', source='coût mensuel × 12')} par an.",
        f"EBE des 12 derniers mois : {c.fact('ebe12', 'EBE estimé sur 12 mois', ebe)} ; il passerait à "
        f"{c.fact('ebe_after', 'EBE annuel après recrutement', ebe - annual, quality='hypothesis', source='EBE 12 mois − coût annuel')} à activité égale.",
        f"La masse salariale passerait de {c.fact('pay12pct', 'Masse salariale en % du CA sur 12 mois', _ratio(payroll, revenue), 'pct')} à "
        f"{c.fact('pay_after', 'Masse salariale après recrutement', _ratio(payroll + annual, revenue), 'pct', quality='hypothesis', source='(masse salariale + coût annuel) ÷ CA')} du chiffre d'affaires.",
    ]
    if needed:
        lines.append(
            f"Pour rester à EBE constant, il faudrait environ {c.fact('hire_breakeven', 'Chiffre d’affaires HT supplémentaire nécessaire par an', needed, quality='hypothesis', source='coût annuel ÷ (1 − part des achats consommés dans le CA)')} "
            "de chiffre d'affaires HT supplémentaire par an."
        )
    t = ctx.treasury
    if t.get("available"):
        after = D(str(t["low_point"]["balance"])) - monthly * 3
        lines.append(
            f"Effet sur la trésorerie : sur trois mois, le point bas prévu descendrait vers {c.fact('hire_low', 'Point bas prévu après trois mois de salaire supplémentaire', after, quality='hypothesis', source='point bas prévu − 3 × coût mensuel', link='/tresorerie')}."
        )
    c.section("Simulation d'un recrutement", lines)


def profit_target(c: Composer, ctx: Context, pct: Decimal | None = None, **_: Any) -> None:
    keys = ctx.complete[-12:]
    if not keys:
        return
    target_pct = pct or D(10)
    ebe = sum((ctx.m(k).ebe for k in keys), ZERO)
    target = ebe * target_pct / 100
    lines = [
        f"Objectif : +{c.fact('target_pct', 'Hausse visée de l’EBE', target_pct, 'pct', quality='hypothesis', source='votre question')} sur un EBE de "
        f"{c.fact('ebe12', 'EBE estimé sur 12 mois', ebe)}, soit {c.fact('target', 'Gain d’EBE annuel visé', target, quality='hypothesis', source='EBE 12 mois × objectif')} par an."
    ]
    total = ZERO
    levers = [
        a
        for a in ctx.open_alerts
        if a["impact"] and a["kind"] in ("food_cost_drift", "price_increase", "redundant_subscription")
    ]
    drift = any(a["kind"] == "food_cost_drift" for a in levers)
    for a in sorted(levers, key=lambda a: -(a["impact"]["amount"] or 0)):
        amount = D(str(a["impact"]["amount"]))
        ref = c.fact(
            f"alert:{a['fingerprint']}",
            a["impact"]["label"].capitalize() + " — " + a["title"],
            amount,
            quality="estimated",
            source=a["impact"]["formula"],
            link="/alertes#" + a["fingerprint"],
        )
        if drift and a["kind"] == "price_increase":
            # Déjà compris dans la dérive du coût matière : pas de double comptage.
            lines.append(f"Levier : {a['title']} — {ref} par an, déjà inclus dans la dérive du coût matière.")
            continue
        total += amount
        lines.append(f"Levier : {a['title']} — jusqu'à {ref} par an.")
    covers = sum((ctx.m(k).covers for k in keys), 0)
    if covers:
        price_lever = D(covers) / D("1.1")
        total += price_lever
        lines.append(
            f"Levier : +1 € TTC sur le ticket moyen, à fréquentation égale, rapporterait {c.fact('price_lever', 'Gain annuel d’une hausse de 1 € TTC par couvert', price_lever, quality='hypothesis', source='couverts sur 12 mois × 1 € ÷ 1,10 (TVA)')} HT par an."
        )
    lines.append(
        f"Total des leviers identifiés : {c.fact('levers_total', 'Total des leviers identifiés', total, quality='estimated', source='somme des leviers')}"
        + (
            ", ce qui couvre l'objectif."
            if total >= target
            else ", insuffisant à lui seul : d'autres pistes sont nécessaires."
        )
    )
    c.section("Comment augmenter l'EBE", lines)


def plan_90(c: Composer, ctx: Context, **_: Any) -> None:
    horizon = {
        "overdue_receivable": "Semaine 1",
        "treasury_tension": "Semaine 1",
        "missing_invoice": "Semaine 1",
        "unusual_invoice": "Semaine 1",
        "duplicate": "Semaine 1",
        "redundant_subscription": "Semaines 2 à 4",
        "price_increase": "Mois 1",
        "possible_duplicate": "Semaine 1",
        "silent_supplier": "Semaines 2 à 4",
        "food_cost_drift": "Mois 1 à 3",
    }
    action = {
        "overdue_receivable": "relancer le client, puis mettre en demeure au-delà de 60 jours",
        "treasury_tension": "décaler les dépenses non urgentes et sécuriser les encaissements",
        "missing_invoice": "demander les duplicatas au fournisseur",
        "unusual_invoice": "faire vérifier la facture avant paiement",
        "duplicate": "vérifier qu'elle n'a pas été payée deux fois",
        "redundant_subscription": "résilier l'abonnement devenu inutile",
        "price_increase": "demander une justification et comparer avec un autre fournisseur",
        "food_cost_drift": "contrôler grammages et pertes, puis ajuster la carte",
        "silent_supplier": "retrouver la facture manquante",
        "possible_duplicate": "vérifier la double facturation",
    }
    lines = []
    for step in ("Semaine 1", "Semaines 2 à 4", "Mois 1", "Mois 1 à 3"):
        for a in ctx.open_alerts:
            if horizon.get(a["kind"]) != step:
                continue
            impact = ""
            if a["impact"] and a["impact"]["amount"]:
                impact = f" (enjeu : {c.fact(f'alert:{a["fingerprint"]}', a['impact']['label'].capitalize() + ' — ' + a['title'], a['impact']['amount'], quality='estimated', source=a['impact']['formula'], link='/alertes#' + a['fingerprint'])})"
            lines.append(f"{step} — {a['title']} : {action.get(a['kind'], 'traiter')}{impact}.")
    c.section(
        "Plan d'action sur 90 jours", lines or ["Aucune action urgente : les données ne signalent pas de problème."]
    )


# --- Agent achats ----------------------------------------------------------------------------


def suppliers(c: Composer, ctx: Context, **_: Any) -> None:
    today = ctx.ds.today
    recent: dict = defaultdict(lambda: ZERO)
    before: dict = defaultdict(lambda: ZERO)
    for inv in ctx.ds.purchases:
        if not inv.issue_date or not inv.total_ht or inv.category == "immobilisations":
            continue
        if today - timedelta(days=90) <= inv.issue_date < today:
            recent[inv.party_id] += inv.total_ht
        elif today - timedelta(days=180) <= inv.issue_date < today - timedelta(days=90):
            before[inv.party_id] += inv.total_ht
    lines = []
    for i, (party, amount) in enumerate(sorted(recent.items(), key=lambda kv: -kv[1])[:5]):
        name = ctx.ds.party_name(party)
        change = _pct_change(amount, before[party]) if before[party] else None
        trend = (
            f", {c.fact(f'supchg:{i}', f'Évolution des achats {name} vs 90 jours précédents', change, 'pct')} par rapport aux 90 jours précédents"
            if change is not None
            else ""
        )
        lines.append(
            f"{name} : {c.fact(f'sup:{i}', f'Achats HT {name} sur 90 jours', amount, link='/donnees?q=' + name)}{trend}."
        )
    for a in ctx.open_alerts:
        if a["kind"] == "price_increase":
            lines.append(f"Hausse de prix : {a['title']}.")
    c.section("Fournisseurs (90 derniers jours)", lines)


def subscriptions(c: Composer, ctx: Context, **_: Any) -> None:
    today = ctx.ds.today
    totals: dict = defaultdict(lambda: ZERO)
    for inv in ctx.ds.purchases:
        if (
            inv.category in ("logiciels", "telecom", "energie", "blanchisserie", "entretien", "honoraires")
            and inv.issue_date
            and inv.issue_date >= today - timedelta(days=365)
            and inv.total_ht
        ):
            totals[inv.party_id] += inv.total_ht
    lines = [
        f"{ctx.ds.party_name(p)} : {c.fact(f'sub:{i}', f'Coût HT sur 12 mois {ctx.ds.party_name(p)}', v)} sur 12 mois."
        for i, (p, v) in enumerate(sorted(totals.items(), key=lambda kv: -kv[1])[:8])
    ]
    for a in ctx.open_alerts:
        if a["kind"] == "redundant_subscription":
            lines.append(
                f"À examiner : {a['title']} — {c.fact(f'alert:{a["fingerprint"]}', a['impact']['label'].capitalize() + ' — ' + a['title'], a['impact']['amount'], quality='estimated', source=a['impact']['formula'], link='/alertes#' + a['fingerprint'])}."
            )
    c.section("Abonnements et contrats récurrents", lines or ["Aucun abonnement identifié."])


# --- Agent commercial ------------------------------------------------------------------------


def sales(c: Composer, ctx: Context, **_: Any) -> None:
    month_summary(c, ctx)
    days = [s for s in ctx.ds.sales if s.day >= ctx.ds.today - timedelta(days=56)]
    if days:
        by_wd: dict = defaultdict(list)
        for s in days:
            by_wd[s.day.weekday()].append(s.total_ht)
        names = ["lundis", "mardis", "mercredis", "jeudis", "vendredis", "samedis", "dimanches"]
        avg = {wd: D(statistics.mean(v)) for wd, v in by_wd.items()}
        best, worst = max(avg, key=avg.get), min(avg, key=avg.get)  # type: ignore[arg-type]
        c.section(
            "Rythme de la semaine (8 dernières semaines)",
            [
                f"Meilleurs jours : les {names[best]}, {c.fact('bestday', f'CA HT moyen des {names[best]}', avg[best], source='journal de caisse')} en moyenne.",
                f"Jours les plus calmes : les {names[worst]}, {c.fact('worstday', f'CA HT moyen des {names[worst]}', avg[worst], source='journal de caisse')}.",
            ],
        )


def customers(c: Composer, ctx: Context, **_: Any) -> None:
    """Clients facturés sur 12 mois : classement, part du chiffre d'affaires, paiement, inactivité."""
    today = ctx.ds.today
    since = today - timedelta(days=365)
    by_party: dict = defaultdict(list)
    for inv in ctx.ds.sales_invoices:
        if inv.issue_date and inv.issue_date >= since and inv.total_ht and inv.party_id:
            by_party[inv.party_id].append(inv)
    if not by_party:
        c.section(
            "Clients",
            [
                "Aucune facture de vente à un client identifié sur les 12 derniers mois : les ventes viennent de la "
                "caisse (clients de passage), qui ne permet pas de distinguer les clients. Importez vos factures de "
                "vente pour obtenir un classement."
            ],
        )
        return

    totals = {p: sum((i.total_ht for i in invs), ZERO) for p, invs in by_party.items()}
    ranking = sorted(totals, key=lambda p: -totals[p])
    invoiced = sum(totals.values(), ZERO)
    start = month_of(since)
    revenue = sum((m.revenue for k, m in ctx.months.items() if start <= k < month_of(today)), ZERO)

    def overdue(party: Any) -> list:
        return [i for i in by_party[party] if not i.paid_on and i.due_date and i.due_date < today and i.total_ttc]

    def delay(party: Any) -> Decimal | None:
        days = [(i.paid_on - i.issue_date).days for i in by_party[party] if i.paid_on and i.issue_date]
        return D(statistics.mean(days)) if days else None

    lines = []
    share = _ratio(invoiced, revenue) if revenue >= invoiced else None
    lines.append(
        f"Ventes facturées à des clients identifiés sur 12 mois : {c.fact('cust:total', 'Ventes HT facturées aux clients identifiés (12 mois)', invoiced, source='factures de vente', link='/donnees?direction=sale')}"
        + (
            f", soit {c.fact('cust:share', 'Part des ventes facturées dans le chiffre d’affaires (12 mois)', share, 'pct')} du chiffre d'affaires ; "
            "le reste vient de la caisse (clients de passage, non identifiés)."
            if share is not None
            else "."
        )
    )

    best = ranking[0]
    name = ctx.ds.party_name(best)
    best_line = (
        f"Votre premier client est **{name}** : {c.fact('cust:0', f'Ventes HT {name} (12 mois)', totals[best], source='factures de vente', link='/donnees?q=' + name)}"
        f" sur 12 mois en {c.fact('cust:0:n', f'Factures émises à {name} (12 mois)', len(by_party[best]), 'count')} facture(s), "
        f"soit {c.fact('cust:0:share', f'Part de {name} dans les ventes facturées', _ratio(totals[best], invoiced), 'pct')} de vos ventes facturées."
    )
    if (d := delay(best)) is not None:
        best_line += f" Il paie en moyenne {c.fact('cust:0:delay', f'Délai moyen de paiement {name}', d, 'days', source='factures et relevé bancaire')} après la facture."
    lines.append(best_line)
    if late := overdue(best):
        amount = sum((i.total_ttc for i in late), ZERO)
        lines.append(
            f"Attention : {name} a aussi {c.fact('cust:0:late', f'Factures échues impayées {name} (TTC)', amount, source='factures de vente et relevé bancaire', link='/alertes')} "
            "de factures échues non réglées. Un bon client en volume n'est pas forcément un bon payeur : relancez avant d'accepter une nouvelle commande importante."
        )
        paid = {p: sum((i.total_ht for i in by_party[p] if i.paid_on), ZERO) for p in ranking}
        best_paid = max(ranking, key=lambda p: paid[p])
        if best_paid != best and paid[best_paid] > paid[best]:
            n = ctx.ds.party_name(best_paid)
            lines.append(
                f"Si l'on ne compte que l'argent réellement encaissé, votre meilleur client est **{n}** : "
                f"{c.fact('cust:paid', f'Ventes HT payées par {n} (12 mois)', paid[best_paid], source='factures de vente et relevé bancaire', link='/donnees?q=' + n)}"
                f" réglés, contre {c.fact('cust:0:paid', f'Ventes HT payées par {name} (12 mois)', paid[best], source='factures de vente et relevé bancaire')} pour {name}."
            )
    if (s0 := _ratio(totals[best], invoiced)) is not None and s0 >= 40 and len(ranking) > 1:
        lines.append(
            "Dépendance : ce client pèse lourd dans vos ventes facturées. Perdre ce client se verrait immédiatement ; diversifiez vos clients professionnels."
        )

    others = []
    for i, party in enumerate(ranking[1:5], start=1):
        n = ctx.ds.party_name(party)
        extra = " (factures échues non réglées)" if overdue(party) else ""
        others.append(
            f"{n} : {c.fact(f'cust:{i}', f'Ventes HT {n} (12 mois)', totals[party], source='factures de vente', link='/donnees?q=' + n)}{extra}"
        )
    if others:
        lines.append("Viennent ensuite : " + " ; ".join(others) + ".")

    payers = [(p, d) for p in ranking if (d := delay(p)) is not None and not overdue(p)]
    if len(payers) > 1:
        p, d = min(payers, key=lambda pd: pd[1])
        if p != best:
            n = ctx.ds.party_name(p)
            lines.append(
                f"Meilleur payeur : {n}, réglé en moyenne en {c.fact('cust:fast', f'Délai moyen de paiement {n}', d, 'days', source='factures et relevé bancaire')}."
            )

    quiet = []
    for party in ranking:
        last = max(i.issue_date for i in by_party[party])
        if len(by_party[party]) >= 2 and (today - last).days > 90:
            n = ctx.ds.party_name(party)
            quiet.append(
                f"{n} (dernière facture il y a {c.fact(f'cust:quiet:{n}', f'Jours depuis la dernière facture {n}', (today - last).days, 'days')})"
            )
    if quiet:
        lines.append(
            "Clients réguliers sans commande depuis plus de 3 mois : "
            + ", ".join(quiet[:3])
            + ". Une prise de contact peut les faire revenir."
        )
    c.section("Vos clients (12 derniers mois)", lines)


# --- Agent administratif ----------------------------------------------------------------------


def receivables(c: Composer, ctx: Context, **_: Any) -> None:
    lines = []
    for i, a in enumerate(a for a in ctx.open_alerts if a["kind"] == "overdue_receivable"):
        lines.append(
            f"{a['title']} — {a['summary']} Montant : {c.fact(f'recv:{i}', a['title'], a['impact']['amount'], source='facture de vente et relevé bancaire', link='/alertes#' + a['fingerprint'])}."
        )
    c.section("Factures clients impayées", lines or ["Aucune facture client en retard."])


def documents_status(c: Composer, ctx: Context, **_: Any) -> None:
    to_review = sum(1 for inv in ctx.ds.invoices if ctx.ds.status(inv) == "to_review")
    lines = [
        f"Factures à vérifier : {c.fact('to_review', 'Factures à vérifier', to_review, 'count', source='centre des données', link='/donnees?status=to_review,failed')}."
    ]
    for a in ctx.open_alerts:
        if a["kind"] in ("missing_invoice", "duplicate", "silent_supplier", "possible_duplicate"):
            lines.append(f"{a['title']}.")
    c.section("Documents", lines)


TOOLS = {
    "month_summary": month_summary,
    "profit_change": profit_change,
    "compare_months": compare_months,
    "year_summary": year_summary,
    "forecast": forecast,
    "treasury": treasury,
    "investment_capacity": investment_capacity,
    "top_charges": top_charges,
    "losses": losses,
    "priorities": priorities,
    "hiring": hiring,
    "profit_target": profit_target,
    "plan_90": plan_90,
    "suppliers": suppliers,
    "subscriptions": subscriptions,
    "sales": sales,
    "customers": customers,
    "receivables": receivables,
    "documents_status": documents_status,
}
