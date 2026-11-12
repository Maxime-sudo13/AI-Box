"""Données de démonstration.

uv run python -m app.demo generate --out ./demo-restaurant
    Produit les fichiers (factures, relevé, journal de caisse) à importer à la main.

uv run python -m app.demo seed
    Crée l'entreprise « Le Bistrot des Tilleuls » sur le boîtier et y importe ces fichiers
    en passant par exactement le même circuit que l'interface.
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.demo.restaurant import COMPANY, generate
from app.finance.bank import import_bank, import_sales, reconcile
from app.finance.ingest import AlreadyImported, ingest_document
from app.finance.tabular import parse_bank, parse_sales
from app.models import Company, DataImport, Membership, User


def seed(files: Path) -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.is_admin, User.is_active).order_by(User.created_at))
        if admin is None:
            sys.exit("Terminez d'abord l'installation du boîtier (compte administrateur).")
        company = db.scalar(select(Company).where(Company.name == COMPANY["name"]))
        if company is None:
            company = Company(
                name=COMPANY["name"],
                legal_form=COMPANY["legal_form"],
                siren=COMPANY["siren"],
                sector=COMPANY["sector"],
                enabled_modules=["direction", "documents", "finance", "conseiller"],
            )
            db.add(company)
            db.flush()
            db.add(Membership(user_id=admin.id, company_id=company.id, role="owner"))
            db.commit()

        started = time.monotonic()
        paths = sorted((files / "factures").iterdir())
        stats = {"importés": 0, "déjà présents": 0}
        for i, path in enumerate(paths, 1):
            try:
                ingest_document(db, company, admin, path.name, path.read_bytes())
                stats["importés"] += 1
            except AlreadyImported:
                stats["déjà présents"] += 1
            db.commit()
            print(f"\r  Factures : {i}/{len(paths)}", end="", flush=True)
        print()
        for kind, parser, importer in (("sales", parse_sales, import_sales), ("bank", parse_bank, import_bank)):
            folder = files / ("caisse" if kind == "sales" else "banque")
            for path in sorted(folder.glob("*.csv")):
                data = path.read_bytes()
                rows, report = parser(data)
                dates = [getattr(r, "booked_on", None) or r.day for r in rows]
                record = DataImport(
                    company_id=company.id,
                    kind=kind,
                    filename=path.name,
                    sha256="demo",
                    rows_total=report.rows_total,
                    rows_added=0,
                    rows_skipped=report.skipped,
                    period_start=min(dates),
                    period_end=max(dates),
                    warnings=report.warnings,
                    imported_by_id=admin.id,
                )
                db.add(record)
                db.flush()
                record.rows_added = importer(db, company.id, record, rows)
                db.commit()
        matched = reconcile(db, company.id)
        db.commit()
        print(f"  {stats}, {matched} paiements rapprochés, en {time.monotonic() - started:.0f} s.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.demo")
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="Produire les fichiers de démonstration")
    g.add_argument("--out", type=Path, default=Path("demo-restaurant"))
    s = sub.add_parser("seed", help="Créer l'entreprise de démonstration et importer ses données")
    s.add_argument("--files", type=Path, help="Dossier déjà généré (sinon, génération temporaire)")
    args = parser.parse_args()

    if args.command == "generate":
        result = generate(args.out)
        print(
            f"{result.files} factures, {result.sales_days} journées de caisse, {result.bank_rows} opérations "
            f"bancaires, du {result.start:%d/%m/%Y} au {result.end:%d/%m/%Y}, dans {result.out_dir}"
        )
    else:
        if args.files:
            seed(args.files)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                print("Génération des données…")
                generate(Path(tmp) / "demo")
                seed(Path(tmp) / "demo")


if __name__ == "__main__":
    main()
