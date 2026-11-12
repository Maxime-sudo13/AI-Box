"""Agent exécutif : transforme une alerte en actions prêtes à valider.

Les brouillons sont rédigés par des modèles de lettres déterministes, à partir des seuls
éléments de l'alerte : aucun chiffre n'est inventé. Le dirigeant peut tout modifier avant
d'autoriser l'envoi.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, Invoice, Party


def _fr_date(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _signature(company: Company) -> str:
    return f"Bien cordialement,\n\n{company.name}"


def _party(db: Session, invoice_id: str | None) -> tuple[Party | None, Invoice | None]:
    if not invoice_id:
        return None, None
    import uuid

    inv = db.get(Invoice, uuid.UUID(invoice_id))
    return (inv.party if inv else None), inv


def drafts_for_alert(db: Session, company: Company, alert: dict[str, Any]) -> list[dict[str, Any]]:
    from app.finance.data import money

    kind = alert["kind"]
    fp = alert["fingerprint"]
    first = alert["invoices"][0] if alert["invoices"] else None
    party, inv = _party(db, first["invoice_id"] if first else None)
    to = party.email if party and party.email else ""
    hello = f"Bonjour{(' ' + party.contact_name) if party and party.contact_name else ''},"
    out: list[dict[str, Any]] = []

    def email(action_type: str, title: str, subject: str, body: str) -> None:
        out.append(
            {
                "action_type": action_type,
                "title": title,
                "trigger": {"alert": fp, "kind": kind},
                "payload": {"to": to, "subject": subject, "body": body, "party_id": str(party.id) if party else None},
                "needs_recipient": not to,
            }
        )

    if kind == "overdue_receivable" and first:
        email(
            "email.payment_reminder",
            f"Relancer {first['party']} — facture {first['number']}",
            f"Relance — facture n° {first['number']} du {_fr_date(first['date'])}",
            f"{hello}\n\nSauf erreur de notre part, la facture n° {first['number']} du {_fr_date(first['date'])}, "
            f"d'un montant de {money(first['amount'], 2)} TTC, arrivée à échéance le {_fr_date(inv.due_date.isoformat() if inv and inv.due_date else None)}, "
            "n'a pas encore été réglée.\n\nPourriez-vous procéder à son règlement dans les meilleurs délais, ou nous indiquer "
            "si un élément bloque le paiement ? Si le règlement a été effectué entre-temps, merci de ne pas tenir compte de ce message.\n\n"
            + _signature(company),
        )
    elif kind == "price_increase" and first:
        figures = {f["label"]: f["value"] for f in alert["figures"]}
        product = alert["title"].split(" : ")[0]
        email(
            "email.supplier_request",
            f"Demander une justification à {first['party']} ({product})",
            f"Évolution du prix — {product}",
            f"{hello}\n\nNous constatons que le prix de l'article « {product} » est passé de "
            f"{money(figures.get('Prix de référence'), 2)} à {money(figures.get('Prix actuel'), 2)} sur vos dernières factures.\n\n"
            "Pourriez-vous nous en indiquer la raison et nous dire si un tarif plus proche de nos conditions habituelles "
            "est envisageable, compte tenu de la régularité de nos commandes ?\n\n" + _signature(company),
        )
    elif kind == "missing_invoice":
        txs = alert["transactions"]
        party_name = alert["title"].split(" à ", 1)[-1].replace(" sans facture", "")
        from sqlalchemy import select

        from app.models import Party as P

        party = db.scalar(select(P).where(P.company_id == company.id, P.name == party_name))
        to = party.email if party and party.email else ""
        lines = "\n".join(f"- paiement du {_fr_date(t['date'])} : {money(-t['amount'], 2)}" for t in txs)
        hello = f"Bonjour{(' ' + party.contact_name) if party and party.contact_name else ''},"
        email(
            "email.supplier_request",
            f"Demander les factures manquantes à {party_name}",
            "Demande de duplicata de factures",
            f"{hello}\n\nNous ne retrouvons pas les factures correspondant aux règlements suivants :\n{lines}\n\n"
            "Pourriez-vous nous en adresser un duplicata ? Merci par avance.\n\n" + _signature(company),
        )
    elif kind == "unusual_invoice" and first:
        email(
            "email.supplier_request",
            f"Faire vérifier la facture {first['number']} de {first['party']}",
            f"Vérification de la facture n° {first['number']}",
            f"{hello}\n\nVotre facture n° {first['number']} du {_fr_date(first['date'])}, d'un montant de {money(first['amount'], 2)}, "
            "est nettement supérieure à nos factures habituelles.\n\nPourriez-vous vérifier les éléments retenus (relevé, quantités) "
            "et nous confirmer son montant avant règlement ?\n\n" + _signature(company),
        )
    elif kind == "redundant_subscription":
        older = alert["title"].split(" : ", 1)[-1].split(" et ")[0]
        from sqlalchemy import select

        from app.models import Party as P

        party = db.scalar(select(P).where(P.company_id == company.id, P.name == older))
        to = party.email if party and party.email else ""
        hello = f"Bonjour{(' ' + party.contact_name) if party and party.contact_name else ''},"
        email(
            "email.cancellation",
            f"Demander la résiliation de l'abonnement {older}",
            "Demande de résiliation d'abonnement",
            f"{hello}\n\nNous vous informons de notre souhait de résilier notre abonnement à vos services, "
            "dans le respect du préavis prévu au contrat.\n\nMerci de nous confirmer la date effective de résiliation "
            "ainsi que l'arrêt des prélèvements correspondants.\n\n" + _signature(company),
        )
    if kind in ("food_cost_drift", "treasury_tension", "silent_supplier", "possible_duplicate", "duplicate"):
        titles = {
            "food_cost_drift": "Contrôler les grammages, les pertes et les fiches techniques des plats",
            "treasury_tension": "Préparer le point bas de trésorerie : décaler les achats non urgents",
            "silent_supplier": "Retrouver la facture manquante du mois",
            "possible_duplicate": "Vérifier la possible double facturation",
            "duplicate": "Vérifier que la facture en double n'a pas été payée deux fois",
        }
        out.append(
            {
                "action_type": "task.create",
                "title": f"Créer la tâche : {titles[kind]}",
                "trigger": {"alert": fp, "kind": kind},
                "payload": {"title": titles[kind], "details": f"{alert['title']}\n{alert['summary']}"},
                "needs_recipient": False,
            }
        )
    return out
