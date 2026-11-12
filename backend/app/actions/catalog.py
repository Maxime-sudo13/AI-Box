"""Catalogue des actions que le boîtier sait exécuter, classées par niveau de risque.

Niveau 1 : sans conséquence financière ou juridique (tâche interne, classement…).
Niveau 2 : engage l'entreprise vis-à-vis d'un tiers (courriel à un client ou un fournisseur).
Niveau 3 : opération sensible (paiement). Jamais automatique : validation du dirigeant,
           confirmation explicite et saisie du mot de passe, même si un agent l'a proposée.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.categories import CATEGORY_KEYS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PayloadError(ValueError):
    pass


def _text(payload: dict, key: str, label: str, max_len: int) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise PayloadError(f"{label} : champ obligatoire.")
    if len(value) > max_len:
        raise PayloadError(f"{label} : {max_len} caractères au maximum.")
    return value


def validate_email(payload: dict) -> dict:
    to = _text(payload, "to", "Destinataire", 254).lower()
    if not EMAIL_RE.match(to):
        raise PayloadError("Destinataire : adresse e-mail invalide.")
    return {
        **payload,
        "to": to,
        "subject": _text(payload, "subject", "Objet", 300),
        "body": _text(payload, "body", "Message", 10000),
    }


def validate_task(payload: dict) -> dict:
    return {
        **payload,
        "title": _text(payload, "title", "Titre", 300),
        "details": str(payload.get("details") or "")[:5000],
    }


def validate_categorize(payload: dict) -> dict:
    if payload.get("category") not in CATEGORY_KEYS:
        raise PayloadError("Catégorie inconnue.")
    if not payload.get("document_id"):
        raise PayloadError("Document manquant.")
    return payload


def validate_alert_status(payload: dict) -> dict:
    if payload.get("status") not in ("acknowledged", "resolved", "dismissed"):
        raise PayloadError("Statut d'alerte invalide.")
    _text(payload, "fingerprint", "Alerte", 120)
    return payload


def iban_ok(iban: str) -> bool:
    iban = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    digits = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def validate_transfer(payload: dict) -> dict:
    out = dict(payload)
    out["creditor_name"] = _text(payload, "creditor_name", "Bénéficiaire", 70)
    for key, label in (("creditor_iban", "IBAN du bénéficiaire"), ("debtor_iban", "IBAN de votre compte")):
        iban = re.sub(r"\s", "", str(payload.get(key) or "")).upper()
        if not iban_ok(iban):
            raise PayloadError(f"{label} invalide (clé de contrôle incorrecte).")
        out[key] = iban
    try:
        amount = Decimal(str(payload.get("amount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError) as exc:
        raise PayloadError("Montant invalide.") from exc
    if amount <= 0 or amount > Decimal("100000"):
        raise PayloadError("Montant hors limites (entre 0,01 € et 100 000 €).")
    out["amount"] = str(amount)
    out["reference"] = _text(payload, "reference", "Référence", 140)
    return out


@dataclass(frozen=True)
class ActionType:
    key: str
    label: str
    level: int
    description: str
    reversible: bool
    validate: Any
    default_mode: str


CATALOG: dict[str, ActionType] = {
    t.key: t
    for t in (
        ActionType(
            "task.create",
            "Créer une tâche interne",
            1,
            "Ajoute une tâche à la liste de l'entreprise.",
            True,
            validate_task,
            "automatic",
        ),
        ActionType(
            "alert.update",
            "Mettre à jour le statut d'une alerte",
            1,
            "Marque une alerte comme prise en compte, traitée ou ignorée.",
            True,
            validate_alert_status,
            "automatic",
        ),
        ActionType(
            "document.categorize",
            "Reclasser une facture",
            1,
            "Change la catégorie de dépense d'une facture.",
            True,
            validate_categorize,
            "automatic",
        ),
        ActionType(
            "email.payment_reminder",
            "Relancer un client",
            2,
            "Envoie une relance pour une facture impayée.",
            False,
            validate_email,
            "approval",
        ),
        ActionType(
            "email.supplier_request",
            "Écrire à un fournisseur",
            2,
            "Demande de justificatif, de duplicata ou de vérification.",
            False,
            validate_email,
            "approval",
        ),
        ActionType(
            "email.cancellation",
            "Demander une résiliation",
            2,
            "Envoie une demande de résiliation d'abonnement.",
            False,
            validate_email,
            "approval",
        ),
        ActionType(
            "payment.transfer",
            "Préparer un virement",
            3,
            "Produit un ordre de virement SEPA à déposer dans votre banque.",
            False,
            validate_transfer,
            "approval",
        ),
    )
}

MODES = ("forbidden", "approval", "automatic")


def allowed_modes(level: int) -> tuple[str, ...]:
    # Une opération sensible n'est jamais automatique.
    return ("forbidden", "approval") if level == 3 else MODES
