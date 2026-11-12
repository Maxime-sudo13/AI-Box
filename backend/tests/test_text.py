from datetime import date
from decimal import Decimal

import pytest

from app.extraction.text import find_amounts, find_dates, name_key, product_key, to_decimal


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1 234,56", "1234.56"), ("1 234,56 €", "1234.56"), ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"), ("1234.56", "1234.56"), ("-12,50", "-12.50"), ("0,2014", "0.2014"),
    ],
)  # fmt: skip
def test_to_decimal(raw, expected):
    assert to_decimal(raw) == Decimal(expected)


def test_find_amounts_ignores_percentages_and_dates():
    assert find_amounts("TVA 5,5 % sur 1 234,56 : 67,90 €") == [Decimal("1234.56"), Decimal("67.90")]
    assert find_amounts("Date : 12/03/2026") == []


@pytest.mark.parametrize(
    "line,expected",
    [
        ("Date de facture : 12/03/2026", date(2026, 3, 12)), ("Émise le 2026-03-12", date(2026, 3, 12)),
        ("Lyon, le 1er mars 2026", date(2026, 3, 1)), ("Échéance : 5 août 2026", date(2026, 8, 5)),
        ("le 31/02/2026", None),
    ],
)  # fmt: skip
def test_find_dates(line, expected):
    assert (find_dates(line) or [None])[0] == expected


def test_keys_are_stable_across_spellings():
    assert name_key("SARL Boucherie Marchand & Fils") == name_key("BOUCHERIE MARCHAND")
    assert product_key("Pavé de saumon frais 2x180g - Lot 4521") == product_key("PAVE DE SAUMON FRAIS LOT 4687")
