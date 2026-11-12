"""Outils de lecture des nombres, dates et noms tels qu'ils apparaissent sur des documents
français (« 1 234,56 € », « 12/03/2026 », « 1er mars 2026 », « SARL Dupont & Fils »)."""

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

_SPACES = "   "

# Montant avec deux décimales, séparateurs de milliers facultatifs (espace, point, virgule).
_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(-?\s?\d{1,3}(?:[   .,]\d{3})+[.,]\d{2}|-?\s?\d+[.,]\d{2})(?![\d])"
    r"(?!\s*%)"
)
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")

_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "janv": 1,
    "fevr": 2,
    "fev": 2,
    "avr": 4,
    "juil": 7,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DATE_NUMERIC = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DATE_TEXT = re.compile(
    r"(?<!\d)(\d{1,2})(?:er)?\s+(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{4})"
)

LEGAL_FORMS = {
    "sarl",
    "sas",
    "sasu",
    "eurl",
    "sa",
    "snc",
    "sci",
    "ei",
    "eirl",
    "scop",
    "sca",
    "selarl",
    "earl",
    "gaec",
    "scea",
    "ste",
    "societe",
    "ets",
    "etablissements",
    "et",
    "cie",
    "fils",
}


def fold(value: str) -> str:
    """Minuscules sans accents, espaces normalisés : base de toutes les comparaisons."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    for space in _SPACES:
        value = value.replace(space, " ")
    return re.sub(r"\s+", " ", value.lower()).strip()


def name_key(name: str) -> str:
    """Clé de rapprochement d'un nom d'entreprise : sans forme juridique ni ponctuation."""
    words = re.findall(r"[a-z0-9]+", fold(name))
    kept = [w for w in words if w not in LEGAL_FORMS]
    return " ".join(kept or words)


def to_decimal(raw: str) -> Decimal | None:
    raw = raw.strip()
    for space in " " + _SPACES:
        raw = raw.replace(space, "")
    raw = raw.replace("€", "").replace("EUR", "")
    if not raw:
        return None
    # Le dernier séparateur suivi de 1 à 3 chiffres en fin de nombre est le séparateur décimal
    # quand il est une virgule, ou un point suivi d'exactement 1, 2 ou 4 chiffres.
    if "," in raw and "." in raw:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        raw = raw.replace(thousands, "").replace(decimal_sep, ".")
    elif "," in raw:
        raw = raw.replace(",", ".") if raw.count(",") == 1 else raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def find_amounts(line: str) -> list[Decimal]:
    amounts = []
    for match in _AMOUNT_RE.finditer(line):
        value = to_decimal(match.group(1))
        if value is not None:
            amounts.append(value)
    return amounts


def find_number(text: str) -> Decimal | None:
    match = _NUMBER_RE.search(text.replace(" ", "").replace(" ", ""))
    return to_decimal(match.group(0)) if match else None


def _safe_date(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    try:
        found = date(year, month, day)
    except ValueError:
        return None
    return found if 2000 <= found.year <= 2100 else None


def find_dates(line: str) -> list[date]:
    """Toutes les dates d'une ligne, dans leur ordre d'apparition."""
    folded = fold(line)
    found: list[tuple[int, date]] = []
    for m in _DATE_ISO.finditer(folded):
        if d := _safe_date(int(m[1]), int(m[2]), int(m[3])):
            found.append((m.start(), d))
    for m in _DATE_NUMERIC.finditer(folded):
        if d := _safe_date(int(m[3]), int(m[2]), int(m[1])):
            found.append((m.start(), d))
    for m in _DATE_TEXT.finditer(folded):
        if d := _safe_date(int(m[3]), _MONTHS[m[2]], int(m[1])):
            found.append((m.start(), d))
    return [d for _, d in sorted(found, key=lambda item: item[0])]


def product_key(description: str) -> str | None:
    """Désignation d'article normalisée, stable d'une facture à l'autre.

    « Pavé de saumon frais 2x180g - Lot 4521 » et « PAVE DE SAUMON FRAIS 2X180G LOT 4687 »
    donnent la même clé : on retire les numéros de lot, quantités et conditionnements.
    """
    text = fold(description)
    text = re.sub(r"\b(lot|ref|reference|code|art)\b\.?\s*[:#]?\s*[a-z0-9\-]+", " ", text)
    text = re.sub(r"\d+([.,]\d+)?\s*(x\s*\d+([.,]\d+)?)?\s*(kg|g|gr|l|cl|ml|pcs?|u|bt|btl|col)?\b", " ", text)
    text = re.sub(r"[^a-z ]+", " ", text)
    words = [
        w
        for w in text.split()
        if len(w) > 1 and w not in {"de", "du", "la", "le", "les", "des", "et", "en", "au", "aux"}
    ]
    return " ".join(words)[:200] or None
