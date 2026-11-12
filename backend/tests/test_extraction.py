"""Qualité de l'extraction mesurée sur les factures de démonstration, dont on connaît les valeurs exactes.

Les trois mises en page, les factures émises par le restaurant, les scans et la photo sont couverts.
"""

import json
from decimal import Decimal

import pytest

from app.demo.restaurant import COMPANY
from app.extraction.invoice import parse_invoice
from app.extraction.reader import ocr_available, read_document


def sample(truth: list[dict]) -> list[dict]:
    picked, seen = [], set()
    for t in truth:
        kind = (t["party"], t["file"].endswith(".jpg"), t["file"].startswith("scan_"))
        if kind not in seen or t["file"].endswith(".jpg"):
            seen.add(kind)
            picked.append(t)
    return picked


def test_demo_invoices_are_read_exactly(demo_files):
    truth = json.loads((demo_files / "verite-terrain.json").read_text())
    cases = sample(truth)
    assert len(cases) >= 18
    for t in cases:
        path = demo_files / "factures" / t["file"]
        if path.suffix == ".jpg" or t["file"].startswith("scan_"):
            if not ocr_available():
                pytest.skip("Tesseract n'est pas installé")
        read = read_document(path, "image/jpeg" if path.suffix == ".jpg" else "application/pdf")
        x = parse_invoice(read, company_name=COMPANY["name"], company_siren=COMPANY["siren"])
        got = {
            "direction": x.direction,
            "party": x.party_name,
            "number": x.number,
            "issue": x.issue_date.isoformat(),
            "due": x.due_date.isoformat(),
            "ht": x.total_ht,
            "ttc": x.total_ttc,
            "lines": len(x.lines),
        }
        expected = {
            "direction": t["direction"],
            "party": t["party"],
            "number": t["number"],
            "issue": t["issue"],
            "due": t["due"],
            "ht": Decimal(t["ht"]),
            "ttc": Decimal(t["ttc"]),
            "lines": t["lines"],
        }
        assert got == expected, t["file"]
        assert x.complete, (t["file"], x.issues)
