"""Extraction des informations d'une facture à partir de son texte.

Le principe est de ne jamais deviner en silence : chaque champ reçoit un statut
(`confirmed`, `estimated`, `missing`, `inconsistent`) et chaque doute est expliqué dans
`issues`. Un montant n'est « confirmé » que s'il se recoupe avec les autres
(HT + TVA = TTC, somme des lignes = HT).
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.extraction.reader import ReadResult
from app.extraction.text import (
    find_amounts,
    find_dates,
    find_number,
    fold,
    name_key,
    product_key,
    to_decimal,
)

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.05")

KEY_FIELDS = ("party", "number", "issue_date", "total_ttc")


@dataclass
class ExtractedLine:
    description: str
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    vat_rate: Decimal | None = None
    total_ht: Decimal | None = None

    @property
    def product_key(self) -> str | None:
        return product_key(self.description)


@dataclass
class ExtractedInvoice:
    direction: str = "purchase"
    party_name: str | None = None
    party_siren: str | None = None
    number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    total_ht: Decimal | None = None
    total_tva: Decimal | None = None
    total_ttc: Decimal | None = None
    vat_breakdown: list[dict[str, str]] = field(default_factory=list)
    lines: list[ExtractedLine] = field(default_factory=list)
    category: str | None = None
    field_status: dict[str, str] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    is_credit_note: bool = False

    @property
    def complete(self) -> bool:
        return all(self.field_status.get(f) in ("confirmed", "estimated") for f in KEY_FIELDS) and (
            self.field_status.get("total_ttc") == "confirmed"
        )


# --- Repérage des libellés ------------------------------------------------------------------

_TTC = re.compile(
    r"total\s*t\.?t\.?c|montant\s*t\.?t\.?c|net\s*a\s*payer|total\s*a\s*payer|montant\s*a\s*payer"
    r"|reste\s*a\s*payer|total\s*toutes\s*taxes"
)
_HT = re.compile(r"total\s*h\.?t|montant\s*h\.?t|total\s*hors\s*tax|net\s*h\.?t|sous[\s-]*total")
_TVA_TOTAL = re.compile(r"total\s*t\.?v\.?a|montant\s*(?:de\s*la\s*)?t\.?v\.?a|t\.?v\.?a\s*totale")
_TVA_RATE = re.compile(r"t\.?v\.?a\s*(?:a|au taux de|taux)?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%")
_RECIPIENT = re.compile(
    r"^(?:factur[ée]e?\s*a|adress[ée]e?\s*a|adresse\s*de\s*facturation|client\s*:|destinataire"
    r"|livr[ée]e?\s*a|bill\s*to)"
)
_DUE = re.compile(
    r"echeance|a\s*regler|a\s*payer\s*avant|date\s*limite|payable\s*(?:le|avant|au)|date\s*de\s*paiement"
    r"|due\s*date|paiement\s*(?:le|avant|au)"
)
_ISSUE = re.compile(
    r"date\s*(?:de\s*(?:la\s*)?facture|d'?emission|de\s*facturation)?\s*:|factur[ée]e?\s*le|\bdu\b|date"
)
_NOT_ISSUE = re.compile(r"echeance|livraison|commande|limite|regler|paiement|payable|bon\s*de|naissance|valid")
_NUMBER = re.compile(
    r"(?:n[°ºo]\.?|no\.?|num[ée]ro|num\.?|#|r[ée]f[ée]rence|r[ée]f\.?)\s*(?:(?:de\s*(?:la\s*)?)?facture\s*)?:?\s*"
    r"([A-Z0-9][A-Z0-9\-/_.]*\d[A-Z0-9\-/_.]*)",
    re.I,
)
_NUMBER_AFTER_WORD = re.compile(r"(?:facture|avoir|invoice)\s+([A-Z]{0,6}[\-/_.]?\d[A-Z0-9\-/_.]*)", re.I)
_SIREN = re.compile(r"(?:siret|siren|rcs[a-z\s]*?)\D{0,15}((?:\d[\s ]?){9,14})", re.I)
_VAT_ID = re.compile(r"\bFR\s?[0-9A-Z]{2}\s?(\d{3}\s?\d{3}\s?\d{3})\b")
_TERMS_DAYS = re.compile(r"(\d{1,3})\s*jours")
_HEADER_NOISE = re.compile(r"\b(facture|duplicata|original|invoice|copie|avoir)\b", re.I)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "alimentaire": (
        "legume",
        "fruit",
        "primeur",
        "boucher",
        "viande",
        "volaille",
        "poisson",
        "maree",
        "saumon",
        "cabillaud",
        "bar ",
        "fromage",
        "fromagerie",
        "cremerie",
        "laiterie",
        "lait",
        "creme",
        "beurre",
        "oeuf",
        "farine",
        "epicerie",
        "huile",
        "boulanger",
        "pain",
        "charcut",
        "surgel",
        "boeuf",
        "veau",
        "agneau",
        "porc",
        "poulet",
        "pomme de terre",
        "salade",
        "tomate",
        "herbes",
        "crustace",
        "moule",
        "sucre",
        "chocolat",
    ),
    "boissons": (
        "vin ",
        "vins",
        "cave",
        "biere",
        "brasser",
        "boisson",
        "spiritueux",
        "champagne",
        "eau minerale",
        "jus ",
        "cafe",
        "the ",
        "sirop",
        "soda",
        "cuvee",
        "aop",
        "igp",
        "fut ",
    ),
    "energie": ("electricite", "energie", " gaz", "kwh", "consommation", "abonnement electr", "compteur"),
    "entretien": ("hygiene", "nettoyage", "entretien", "detergent", "desinfect", "degraiss", "lessive"),
    "blanchisserie": ("blanchisserie", "linge", "nappe", "serviette", "tablier", "pressing", "veste de cuisine"),
    "logiciels": (
        "logiciel",
        "licence",
        "saas",
        "caisse enregistreuse",
        "abonnement mensuel",
        "hebergement",
        "application",
    ),
    "telecom": ("telephon", "internet", "fibre", "forfait mobile", " box"),
    "assurance": ("assurance", "cotisation annuelle", "sinistre"),
    "honoraires": ("honoraires", "expert-comptable", "expertise comptable", "comptab", "avocat", "conseil juridique"),
    "materiel": ("ustensile", "vaisselle", "materiel", "couteau", "casserole", "verre"),
    "marketing": ("publicite", "impression", "flyer", "communication", "affiche", "carte de visite"),
    "loyer": ("loyer", "bail", "charges locatives"),
    "immobilisations": ("four mixte", "chambre froide", "installation et mise en service", "equipement professionnel"),
}


def classify(text: str) -> str | None:
    folded = f" {fold(text)} "
    scores = {
        category: sum(folded.count(keyword) for keyword in keywords)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else None


# --- Analyse ----------------------------------------------------------------------------------


def _last_amount(lines: list[str], pattern: re.Pattern, *, exclude: re.Pattern | None = None) -> Decimal | None:
    found = None
    for line in lines:
        folded = fold(line)
        if pattern.search(folded) and not (exclude and exclude.search(folded)):
            amounts = find_amounts(line)
            if amounts:
                found = amounts[-1]
    return found


def _siren(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits[:9] if len(digits) in (9, 14) else None


def _find_number(lines: list[str]) -> str | None:
    for line in lines:
        folded = fold(line)
        if not re.search(r"factur|invoice|avoir", folded):
            continue
        if re.search(r"tva|siret|siren|client|commande|bon de|telephone|tel\b", folded):
            # Le numéro peut être sur la même ligne qu'un n° client : on isole la partie « facture ».
            match = re.search(r"(?:facture|avoir|invoice)[^|]*", line, re.I)
            line = match.group(0) if match else ""
        for regex in (_NUMBER, _NUMBER_AFTER_WORD):
            m = regex.search(line)
            if m and not re.fullmatch(r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}", m.group(1)):
                return m.group(1).strip(".-/")
    return None


def _recipient_block(lines: list[str]) -> tuple[int, int] | None:
    for index, line in enumerate(lines):
        if _RECIPIENT.search(fold(line)):
            return index, min(len(lines), index + 6)
    return None


def _clean_name(line: str) -> str:
    line = _HEADER_NOISE.sub(" ", line)
    line = re.sub(r"\s{2,}", " ", line).strip(" -–—:|")
    return line


_SEGMENT = re.compile(r"\S(?:.*?\S)?(?=\s{3,}|\s*$)")


def _segments(line: str) -> list[tuple[int, str]]:
    """Blocs d'une ligne séparés par de larges espaces, avec leur colonne de départ."""
    return [(m.start(), m.group(0)) for m in _SEGMENT.finditer(line)]


def _looks_like_name(line: str) -> bool:
    folded = fold(line)
    if len(folded) < 3 or not re.search(r"[a-z]{3}", folded):
        return False
    if ":" in folded or re.match(r"^(ref|n[°o]|no\b|date|echeance|client|page|tel|total|montant)", folded):
        return False
    if find_dates(line) or re.match(r"^\d", folded):
        return False
    return not re.search(r"(tel|telephone|email|e-mail|www\.|@|siret|siren|tva|iban|page)\b", folded)


def _parse_lines_from_tables(tables: list[list[list[str | None]]]) -> list[ExtractedLine]:
    result: list[ExtractedLine] = []
    for table in tables:
        if not table:
            continue
        header_index, columns = None, {}
        for index, row in enumerate(table[:4]):
            cells = [fold(c or "") for c in row]
            mapping = {}
            for col, cell in enumerate(cells):
                if re.search(r"designation|description|article|produit|libelle|prestation", cell):
                    mapping.setdefault("description", col)
                elif re.search(r"\bqte\b|quantite|qty|\bqt\b", cell):
                    mapping.setdefault("quantity", col)
                elif re.search(r"unite|^u\.?$|\bunit\b", cell):
                    mapping.setdefault("unit", col)
                elif re.search(r"p\.?\s*u|prix\s*unit|prix\s*ht|^prix$|tarif", cell):
                    mapping.setdefault("unit_price", col)
                elif re.search(r"tva|taux", cell):
                    mapping.setdefault("vat_rate", col)
                elif re.search(r"montant|total|^ht$", cell):
                    mapping["total_ht"] = col
            if "description" in mapping and ("total_ht" in mapping or "unit_price" in mapping):
                header_index, columns = index, mapping
                break
        if header_index is None:
            continue
        for row in table[header_index + 1 :]:

            def cell(name: str, row: list[str | None] = row, columns: dict[str, int] = columns) -> str:
                col = columns.get(name)
                return (row[col] or "").strip() if col is not None and col < len(row) else ""

            description = re.sub(r"\s+", " ", cell("description"))
            folded = fold(description)
            if not description or re.match(r"^(total|sous-total|tva|net|montant|remise globale)", folded):
                continue
            total = (find_amounts(cell("total_ht")) or [None])[-1]
            unit_price = (find_amounts(cell("unit_price")) or [None])[-1] or find_number(cell("unit_price"))
            if total is None and unit_price is None:
                continue
            raw_qty = cell("quantity")
            quantity = find_number(raw_qty) if raw_qty else None
            unit = cell("unit") or (re.sub(r"[\d\s.,]+", "", raw_qty).strip() or None if raw_qty else None)
            vat_rate = find_number(cell("vat_rate").replace("%", "")) if cell("vat_rate") else None
            result.append(
                ExtractedLine(description[:300], quantity, (unit or None) and unit[:20], unit_price, vat_rate, total)
            )
    return result


_TEXT_LINE = re.compile(
    r"^(?P<desc>[A-Za-zÀ-ÿ].*?)\s+(?P<qty>\S{1,8}?)\s*(?P<unit>[A-Za-zÀ-ÿ]{1,10}\.?)?\s+"
    r"(?P<pu>\d[\d\s]*[.,]\d{2,4})\s*€?\s+(?:(?P<vat>\d{1,2}(?:[.,]\d{1,2})?)\s*%\s+)?"
    r"(?P<total>\d[\d\s]*[.,]\d{2})\s*€?$",
)


def _parse_lines_from_text(lines: list[str]) -> list[ExtractedLine]:
    """Lignes d'articles d'un document sans tableau exploitable (cas des scans).

    Si l'OCR a mal lu la quantité (« T » au lieu de « 7 »), elle est recalculée à partir du
    montant et du prix unitaire, à condition de tomber juste.
    """
    result = []
    for line in lines:
        folded = fold(line)
        if re.match(r"^(total|sous-total|tva|net|montant|base|designation|article)", folded):
            continue
        m = _TEXT_LINE.match(line.strip())
        if not m:
            continue
        unit_price = to_decimal(m["pu"])
        total = to_decimal(m["total"])
        quantity = to_decimal(m["qty"]) if re.fullmatch(r"\d+(?:[.,]\d+)?", m["qty"]) else None
        if quantity is None and unit_price and total:
            guess = (total / unit_price).quantize(Decimal("0.1"))
            quantity = guess if abs(guess * unit_price - total) <= TOLERANCE else None
        if quantity is not None and unit_price and total and abs(quantity * unit_price - total) > TOLERANCE:
            # Quantité mal lue (« 39 » pour « 3,5 ») : le montant et le prix unitaire font foi.
            guess = (total / unit_price).quantize(Decimal("0.1"))
            quantity = guess if abs(guess * unit_price - total) <= TOLERANCE else quantity
        if quantity is None:
            continue
        vat = to_decimal(m["vat"]) if m["vat"] else None
        result.append(ExtractedLine(m["desc"].strip()[:300], quantity, m["unit"], unit_price, vat, total))
    return result


def parse_invoice(read: ReadResult, *, company_name: str, company_siren: str | None) -> ExtractedInvoice:
    out = ExtractedInvoice()
    lines = [line for line in (raw.strip() for raw in read.text.splitlines()) if line]
    folded_all = fold(read.text)
    out.is_credit_note = bool(re.search(r"\bavoir\b", folded_all[:400]))

    # Tiers ------------------------------------------------------------------------------
    raw_lines = [raw for raw in read.text.splitlines() if raw.strip()]
    recipient = _recipient_block(lines)
    in_recipient = (lambda i: recipient[0] <= i < recipient[1]) if recipient else (lambda i: False)
    recipient_name = None
    if recipient:
        start = recipient[0]
        # Colonne du libellé « Facturé à » : le nom du destinataire est aligné dessous.
        marker_col = next((col for col, seg in _segments(raw_lines[start]) if _RECIPIENT.search(fold(seg))), 0)
        marker_seg = next((seg for _, seg in _segments(raw_lines[start]) if _RECIPIENT.search(fold(seg))), lines[start])
        after_marker = re.split(r":", marker_seg, maxsplit=1)
        if len(after_marker) == 2 and _looks_like_name(after_marker[1]):
            recipient_name = _clean_name(after_marker[1])
        else:
            for raw in raw_lines[start + 1 : recipient[1]]:
                candidates = sorted(_segments(raw), key=lambda cs: abs(cs[0] - marker_col))
                if candidates and abs(candidates[0][0] - marker_col) <= 8 and _looks_like_name(candidates[0][1]):
                    recipient_name = _clean_name(candidates[0][1])
                    break

    issuer_name = None
    for i, raw in enumerate(raw_lines[:8]):
        if in_recipient(i):
            continue
        for _, segment in _segments(raw):
            cleaned = _clean_name(segment)
            if _looks_like_name(cleaned) and not _RECIPIENT.search(fold(cleaned)):
                issuer_name = cleaned
                break
        if issuer_name:
            break

    sirens: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        for m in _SIREN.finditer(line):
            if s := _siren(m.group(1)):
                sirens.append((i, s))
        for m in _VAT_ID.finditer(line):
            sirens.append((i, re.sub(r"\s", "", m.group(1))))
    issuer_sirens = [s for i, s in sirens if not in_recipient(i)]
    recipient_sirens = [s for i, s in sirens if in_recipient(i)]

    company_key = name_key(company_name)
    issuer_is_company = bool(
        (company_siren and company_siren in issuer_sirens and company_siren not in recipient_sirens)
        or (issuer_name and company_key and name_key(issuer_name) == company_key)
    )
    if issuer_is_company:
        out.direction = "sale"
        out.party_name = recipient_name
        out.party_siren = next((s for s in recipient_sirens if s != company_siren), None)
    else:
        out.direction = "purchase"
        out.party_name = issuer_name
        out.party_siren = next((s for s in issuer_sirens if s != company_siren), None)
    out.field_status["party"] = "confirmed" if out.party_name else "missing"
    if not out.party_name:
        out.issues.append("Le fournisseur ou le client n'a pas pu être identifié.")

    # Numéro et dates ----------------------------------------------------------------------
    out.number = _find_number(lines)
    out.field_status["number"] = "confirmed" if out.number else "missing"
    if not out.number:
        out.issues.append("Numéro de facture introuvable.")

    for line in lines:
        folded = fold(line)
        dates = find_dates(line)
        if not dates:
            continue
        if out.due_date is None and _DUE.search(folded):
            out.due_date = dates[-1]
        elif out.issue_date is None and _ISSUE.search(folded) and not _NOT_ISSUE.search(folded):
            out.issue_date = dates[0]
    if out.issue_date:
        out.field_status["issue_date"] = "confirmed"
    else:
        first = next((d for line in lines if not _NOT_ISSUE.search(fold(line)) for d in find_dates(line)), None)
        out.issue_date = first
        out.field_status["issue_date"] = "estimated" if first else "missing"
        out.issues.append(
            "Date de facture déduite de la première date du document." if first else "Date de facture introuvable."
        )

    if out.due_date:
        out.field_status["due_date"] = "confirmed"
    elif out.issue_date:
        terms = _TERMS_DAYS.search(folded_all)
        if re.search(r"a\s*reception|comptant", folded_all):
            out.due_date, label = out.issue_date, "paiement à réception"
        else:
            days = int(terms.group(1)) if terms and int(terms.group(1)) <= 120 else 30
            out.due_date, label = out.issue_date + timedelta(days=days), f"{days} jours"
        out.field_status["due_date"] = "estimated"
        out.issues.append(f"Échéance non indiquée : estimée selon les conditions ({label}).")
    else:
        out.field_status["due_date"] = "missing"

    # Montants ---------------------------------------------------------------------------
    out.total_ttc = _last_amount(lines, _TTC)
    out.total_ht = _last_amount(lines, _HT, exclude=_TTC)
    out.total_tva = _last_amount(lines, _TVA_TOTAL, exclude=_TTC)

    for line in lines:
        folded = fold(line)
        m = _TVA_RATE.search(folded)
        if not m or _TTC.search(folded):
            continue
        # Les montants situés après le taux : « TVA 5,5 % sur 1 234,56 : 67,90 ».
        amounts = find_amounts(folded[m.end() :])
        rate = find_number(m.group(1))
        if rate is None or rate > 30 or not amounts:
            continue
        base, amount = (amounts[-2], amounts[-1]) if len(amounts) >= 2 else (None, amounts[-1])
        entry = {"rate": str(rate), "amount": str(amount)}
        if base is not None:
            entry["base"] = str(base)
        if entry not in out.vat_breakdown:
            out.vat_breakdown.append(entry)
    if out.total_tva is None and out.vat_breakdown:
        out.total_tva = sum((Decimal(v["amount"]) for v in out.vat_breakdown), Decimal(0))
        tva_derived = True
    else:
        tva_derived = False

    # Lignes -----------------------------------------------------------------------------
    out.lines = _parse_lines_from_tables(read.tables) or _parse_lines_from_text(lines)
    for line in out.lines:
        if line.total_ht is None and line.quantity is not None and line.unit_price is not None:
            line.total_ht = (line.quantity * line.unit_price).quantize(CENT)
        if line.unit_price is None and line.total_ht is not None and line.quantity:
            line.unit_price = (line.total_ht / line.quantity).quantize(Decimal("0.0001"))
    lines_total = sum((line.total_ht for line in out.lines if line.total_ht is not None), Decimal(0))

    _reconcile_totals(out, lines_total, tva_derived)

    out.category = classify(" ".join([out.party_name or ""] + [line.description for line in out.lines]))
    if out.is_credit_note:
        out.issues.append("Ce document semble être un avoir : vérifiez le sens des montants.")
    return out


def _close(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= TOLERANCE


def _reconcile_totals(out: ExtractedInvoice, lines_total: Decimal, tva_derived: bool) -> None:
    ht, tva, ttc = out.total_ht, out.total_tva, out.total_ttc
    status = out.field_status

    if ht is not None and tva is not None and ttc is not None:
        if _close(ht + tva, ttc):
            status.update(total_ht="confirmed", total_tva="confirmed", total_ttc="confirmed")
        else:
            status.update(total_ht="inconsistent", total_tva="inconsistent", total_ttc="inconsistent")
            out.issues.append(f"Les montants ne se recoupent pas : HT {ht} + TVA {tva} ≠ TTC {ttc}.")
    elif ttc is not None and ht is not None:
        out.total_tva = (ttc - ht).quantize(CENT)
        status.update(total_ht="confirmed", total_ttc="confirmed", total_tva="estimated")
        out.issues.append("Montant de TVA calculé (TTC − HT).")
    elif ttc is not None and tva is not None:
        out.total_ht = (ttc - tva).quantize(CENT)
        status.update(
            total_ttc="confirmed", total_tva="estimated" if tva_derived else "confirmed", total_ht="estimated"
        )
        out.issues.append("Montant HT calculé (TTC − TVA).")
    elif ht is not None and tva is not None:
        out.total_ttc = (ht + tva).quantize(CENT)
        status.update(total_ht="confirmed", total_tva="confirmed", total_ttc="estimated")
        out.issues.append("Montant TTC calculé (HT + TVA) : le total à payer n'a pas été lu.")
    elif ttc is not None:
        status.update(total_ttc="estimated", total_ht="missing", total_tva="missing")
        out.issues.append("Seul le montant TTC a été trouvé : il n'a pas pu être recoupé.")
    else:
        if lines_total:
            out.total_ht = lines_total
            status.update(total_ht="estimated", total_tva="missing", total_ttc="missing")
        else:
            status.update(total_ht="missing", total_tva="missing", total_ttc="missing")
        out.issues.append("Montant total à payer introuvable.")

    if tva_derived and status.get("total_tva") == "confirmed":
        # La TVA vient de la ventilation par taux : elle est recoupée par HT + TVA = TTC.
        pass

    if out.lines and out.total_ht is not None:
        if _close(lines_total, out.total_ht):
            status["lines"] = "confirmed"
        else:
            status["lines"] = "inconsistent"
            out.issues.append(f"La somme des lignes ({lines_total}) ne correspond pas au total HT ({out.total_ht}).")
    else:
        status["lines"] = "missing" if not out.lines else "estimated"
