from datetime import date
from decimal import Decimal

import pytest

from app.finance.bank import categorize
from app.finance.tabular import TabularError, parse_bank, parse_sales


def test_bank_with_preamble_signed_amounts_and_cp1252():
    data = (
        "Compte courant professionnel;FR76 ...\n"
        "Période;01/10/2026 au 31/10/2026\n"
        "\n"
        "Date;Libellé;Montant;Solde\n"
        "02/10/2026;PRLV SEPA URSSAF RHÔNE-ALPES;-5 912,40;18 087,60\n"
        "02/10/2026;REMISE CB 0110;1 812,05;19 899,65\n"
        "03/10/2026;;12,00;\n"
    ).encode("cp1252")
    rows, report = parse_bank(data)
    assert [(r.booked_on, r.amount) for r in rows] == [
        (date(2026, 10, 2), Decimal("-5912.40")), (date(2026, 10, 2), Decimal("1812.05")),
    ]  # fmt: skip
    assert rows[0].label == "PRLV SEPA URSSAF RHÔNE-ALPES"
    assert rows[1].balance == Decimal("19899.65")
    assert report.skipped == 1


def test_bank_with_debit_credit_columns_and_identical_rows():
    data = b"Date operation,Libelle,Debit,Credit\n2026-10-05,FRAIS,1.50,\n2026-10-05,FRAIS,1.50,\n2026-10-06,VIR CLIENT,,250.00\n"
    rows, report = parse_bank(data)
    assert [r.amount for r in rows] == [Decimal("-1.50"), Decimal("-1.50"), Decimal("250.00")]
    # Deux opérations identiques restent deux opérations distinctes.
    assert rows[0].fingerprint != rows[1].fingerprint
    assert any("Solde" in w for w in report.warnings)
    # Réimporter le même fichier redonne les mêmes empreintes : pas de doublon possible.
    assert [r.fingerprint for r in parse_bank(data)[0]] == [r.fingerprint for r in rows]


def test_bank_without_required_columns_is_refused():
    with pytest.raises(TabularError):
        parse_bank(b"Date;Commentaire\n01/01/2026;rien\n")


def test_sales_journal():
    data = "Date;Couverts;CA nourriture HT;CA boissons HT;TVA;Total TTC;CB;Espèces\n" \
           "04/11/2026;71;1 512,30;498,20;251,87;2 262,37;2 001,00;261,37\n".encode()  # fmt: skip
    rows, _ = parse_sales(data)
    assert rows[0].covers == 71
    assert rows[0].total_ht == Decimal("2010.50")  # nourriture + boissons, faute de colonne « Total HT »
    assert rows[0].cash == Decimal("261.37")


@pytest.mark.parametrize(
    "label,amount,expected",
    [
        ("REMISE CB 0311 TPE 44", "1200", "encaissement_cb"), ("PRLV SEPA URSSAF RHONE", "-5000", "charges_sociales"),
        ("PRLV SEPA DGFIP TVA 102026", "-3000", "tva"), ("PRLV SEPA DGFIP IS ACOMPTE 122026", "-3100", "impot_societes"),
        ("ECHEANCE PRET PROFESSIONNEL N 0412", "-1650", "emprunt"), ("VIR SEPA SALAIRES OCTOBRE", "-12000", "salaires"),
        ("VIR SEPA INCONNU", "-80", "a_classer"),
    ],
)  # fmt: skip
def test_bank_rules(label, amount, expected):
    assert categorize(label, Decimal(amount), None)[0] == expected
