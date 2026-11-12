"""Lecture des exports CSV : relevé bancaire et journal de caisse.

Les logiciels bancaires et de caisse exportent chacun à leur manière (séparateur, encodage,
noms de colonnes, débit/crédit séparés ou montant signé). Ce module reconnaît les variantes
courantes et refuse explicitement ce qu'il ne comprend pas plutôt que de deviner.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.extraction.text import find_dates, fold, to_decimal


class TabularError(ValueError):
    pass


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TabularError("Encodage du fichier non reconnu.")


def read_rows(data: bytes) -> tuple[list[str], list[list[str]]]:
    text = decode(data)
    sample = text[:5000]
    delimiter = max([";", ",", "\t", "|"], key=lambda d: sample.count(d))
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    # Certaines banques ajoutent quelques lignes d'en-tête (titulaire, période) avant le tableau.
    for index, row in enumerate(rows[:15]):
        if any(re.search(r"\bdate\b|\bjour\b", fold(c)) for c in row) and len(row) >= 3:
            return [fold(c) for c in row], rows[index + 1 :]
    raise TabularError("Ligne d'en-tête introuvable : le fichier doit contenir une colonne « Date ».")


def _column(header: list[str], *patterns: str) -> int | None:
    for pattern in patterns:
        for index, name in enumerate(header):
            if re.fullmatch(pattern, name):
                return index
    for pattern in patterns:
        for index, name in enumerate(header):
            if re.search(pattern, name):
                return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def _amount(raw: str) -> Decimal | None:
    raw = raw.replace("€", "").strip()
    if not raw:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    value = to_decimal(raw.strip("()"))
    return -value if value is not None and negative else value


@dataclass
class BankRow:
    booked_on: date
    label: str
    amount: Decimal
    balance: Decimal | None
    fingerprint: str


@dataclass
class ParseReport:
    rows_total: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_bank(data: bytes) -> tuple[list[BankRow], ParseReport]:
    header, rows = read_rows(data)
    c_date = _column(header, r"date operation", r"date comptable", r"date", r"date.*")
    c_label = _column(header, r"libelle", r"libelle.*", r"description", r"intitule", r"detail.*", r"operation")
    c_amount = _column(header, r"montant", r"montant.*", r"amount")
    c_debit = _column(header, r"debit", r"debit.*")
    c_credit = _column(header, r"credit", r"credit.*")
    c_balance = _column(header, r"solde", r"solde.*", r"balance")
    if c_date is None or c_label is None or (c_amount is None and c_debit is None and c_credit is None):
        raise TabularError("Colonnes attendues : date, libellé, et montant (ou débit et crédit).")

    report = ParseReport(rows_total=len(rows))
    out: list[BankRow] = []
    seen: Counter = Counter()
    for row in rows:
        dates = find_dates(_cell(row, c_date))
        label = re.sub(r"\s+", " ", _cell(row, c_label))[:300]
        if c_amount is not None and _cell(row, c_amount):
            amount = _amount(_cell(row, c_amount))
        else:
            debit, credit = _amount(_cell(row, c_debit)), _amount(_cell(row, c_credit))
            amount = (credit or Decimal(0)) - abs(debit or Decimal(0)) if (debit or credit) else None
        if not dates or not label or amount is None:
            report.skipped += 1
            continue
        balance = _amount(_cell(row, c_balance)) if c_balance is not None else None
        # Deux opérations identiques le même jour restent distinctes grâce à leur rang.
        key = (dates[0], label, amount)
        seen[key] += 1
        fingerprint = hashlib.sha256(f"{dates[0]}|{label}|{amount}|{seen[key]}".encode()).hexdigest()
        out.append(BankRow(dates[0], label, amount, balance, fingerprint))
    if c_balance is None:
        report.warnings.append(
            "Le relevé ne contient pas de colonne « Solde » : la trésorerie disponible ne pourra pas être calculée."
        )
    if report.skipped:
        report.warnings.append(f"{report.skipped} ligne(s) ignorée(s) car incomplètes.")
    return out, report


@dataclass
class SalesRow:
    day: date
    covers: int | None
    food_ht: Decimal | None
    drinks_ht: Decimal | None
    total_ht: Decimal
    total_tva: Decimal | None
    total_ttc: Decimal | None
    card: Decimal | None
    cash: Decimal | None
    meal_vouchers: Decimal | None


def parse_sales(data: bytes) -> tuple[list[SalesRow], ParseReport]:
    header, rows = read_rows(data)
    col = {
        "day": _column(header, r"date", r"jour", r"journee", r"date.*"),
        "covers": _column(header, r"couverts", r"nb couverts", r"nombre de couverts", r"clients", r".*couverts.*"),
        "food_ht": _column(header, r"ca nourriture ht", r"nourriture ht", r"cuisine ht", r"food.*", r".*nourriture.*"),
        "drinks_ht": _column(header, r"ca boissons ht", r"boissons ht", r"bar ht", r"drinks.*", r".*boissons.*"),
        "total_ht": _column(header, r"total ht", r"ca ht", r"chiffre d'?affaires ht"),
        "total_tva": _column(header, r"tva", r"total tva", r"montant tva"),
        "total_ttc": _column(header, r"total ttc", r"ca ttc", r"ttc"),
        "card": _column(header, r"cb", r"carte", r"carte bancaire", r"carte.*"),
        "cash": _column(header, r"especes", r"cash", r"liquide"),
        "meal_vouchers": _column(header, r"titres?[- ]restaurant", r"tickets?[- ]restaurant", r"tr", r".*titres?.*"),
    }
    if col["day"] is None or all(col[k] is None for k in ("total_ht", "total_ttc", "food_ht")):
        raise TabularError("Colonnes attendues : date, et chiffre d'affaires (HT ou TTC).")

    report = ParseReport(rows_total=len(rows))
    out: list[SalesRow] = []
    for row in rows:
        dates = find_dates(_cell(row, col["day"]))
        values = {k: _amount(_cell(row, c)) for k, c in col.items() if k not in ("day", "covers")}
        covers_raw = re.sub(r"\D", "", _cell(row, col["covers"]))
        total_ht = values["total_ht"]
        if total_ht is None and values["food_ht"] is not None:
            total_ht = values["food_ht"] + (values["drinks_ht"] or Decimal(0))
        if total_ht is None and values["total_ttc"] is not None and values["total_tva"] is not None:
            total_ht = values["total_ttc"] - values["total_tva"]
        if not dates or total_ht is None:
            report.skipped += 1
            continue
        out.append(
            SalesRow(
                dates[0],
                int(covers_raw) if covers_raw else None,
                values["food_ht"],
                values["drinks_ht"],
                total_ht,
                values["total_tva"],
                values["total_ttc"],
                values["card"],
                values["cash"],
                values["meal_vouchers"],
            )
        )
    if report.skipped:
        report.warnings.append(f"{report.skipped} ligne(s) ignorée(s) car incomplètes.")
    if col["covers"] is None:
        report.warnings.append("Pas de colonne « Couverts » : le ticket moyen ne pourra pas être calculé.")
    return out, report
