"""Génère les données d'un restaurant fictif : « Le Bistrot des Tilleuls ».

Douze mois complets d'activité, produits comme le ferait un vrai restaurant :
- factures fournisseurs en PDF, avec trois mises en page différentes, des scans à lire par
  OCR et une photo prise au smartphone ;
- factures de privatisation émises par le restaurant ;
- journal de caisse quotidien (tickets Z) et relevé bancaire au format CSV.

Plusieurs situations à détecter sont glissées dans les données (voir docs/demo.md). Tous les
noms, adresses et numéros SIREN sont fictifs ; les SIREN ne respectent volontairement pas la
clé de contrôle, pour ne jamais correspondre à une entreprise réelle.
"""

import calendar
import csv
import io
import json
import random
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

D = Decimal
CENT = D("0.01")

COMPANY = {
    "name": "Le Bistrot des Tilleuls",
    "legal_form": "SARL",
    "siren": "812345670",
    "sector": "Restauration traditionnelle",
    "address": ["14 place des Tilleuls", "69002 Lyon"],
}


def money(value) -> Decimal:
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fr(value: Decimal, decimals: int = 2) -> str:
    """Format français : 1 234,56."""
    q = D(1).scaleb(-decimals)
    text = f"{D(value).quantize(q, rounding=ROUND_HALF_UP):,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def fr_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]  # fmt: skip


def fr_long_date(d: date) -> str:
    return f"{'1er' if d.day == 1 else d.day} {MONTHS_FR[d.month - 1]} {d.year}"


@dataclass
class Product:
    name: str
    unit: str
    price: Decimal
    vat: Decimal


@dataclass
class Supplier:
    key: str
    name: str
    legal: str
    siren: str
    address: list[str]
    prefix: str
    layout: str
    payment: str  # "virement" ou "prelevement"
    terms_days: int
    products: list[Product]
    scanned: bool = False


def P(name, unit, price, vat="5.5"):
    return Product(name, unit, D(str(price)), D(vat))


SUPPLIERS = {
    s.key: s
    for s in [
        Supplier("primeur", "Primeurs du Val", "SARL", "523418907", ["ZI des Grandes Terres", "69730 Genay"], "PV", "A", "virement", 15, [
            P("Pommes de terre grenaille", "kg", 1.85), P("Carottes des sables", "kg", 1.60),
            P("Oignons jaunes", "kg", 1.35), P("Échalotes", "kg", 4.20), P("Poireaux", "kg", 2.40),
            P("Salade batavia", "pièce", 0.95), P("Tomates grappe", "kg", 3.10),
            P("Champignons de Paris", "kg", 4.80), P("Citrons jaunes", "kg", 2.90),
            P("Herbes fraîches (botte)", "botte", 1.20), P("Pommes Golden", "kg", 2.10),
            P("Courge butternut", "kg", 1.90)]),
        Supplier("boucherie", "Boucherie Marchand", "SAS", "498223610", ["8 rue de la Charité", "69002 Lyon"], "BM", "B", "virement", 30, [
            P("Bavette d'aloyau", "kg", 21.50), P("Paleron de bœuf", "kg", 14.20),
            P("Suprême de volaille fermière", "kg", 15.80), P("Épaule d'agneau", "kg", 16.90),
            P("Joue de porc", "kg", 11.40), P("Saucisse de Toulouse", "kg", 9.80),
            P("Lard paysan", "kg", 12.30)]),
        Supplier("maree", "Marée Atlantique", "SAS", "441902386", ["Marché d'intérêt national", "69200 Vénissieux"], "MA", "C", "virement", 30, [
            P("Pavé de saumon frais", "kg", 24.90), P("Dos de cabillaud", "kg", 22.50),
            P("Filet de lieu jaune", "kg", 19.80), P("Moules de bouchot", "kg", 4.60),
            P("Crevettes sauvages", "kg", 26.00), P("Bar de ligne", "kg", 29.50)]),
        Supplier("laiterie", "Laiterie des Monts", "SARL", "389017245", ["Route de Saint-Bonnet", "69610 Sainte-Foy-l'Argentière"], "LM", "A", "virement", 30, [
            P("Crème liquide 35 %", "L", 4.60), P("Beurre doux AOP", "kg", 9.80),
            P("Lait entier", "L", 1.10), P("Œufs plein air (plateau 30)", "plateau", 8.90),
            P("Mascarpone", "kg", 7.40), P("Fromage blanc", "kg", 3.80)]),
        Supplier("epicerie", "Épicerie Pro Rhône", "SAS", "752006134", ["45 avenue Jean Jaurès", "69007 Lyon"], "EPR", "B", "virement", 30, [
            P("Farine T55", "kg", 0.95), P("Huile d'olive vierge extra", "L", 9.80),
            P("Sucre semoule", "kg", 1.25), P("Riz arborio", "kg", 3.90),
            P("Chocolat noir 70 %", "kg", 14.50), P("Vinaigre de Xérès", "L", 6.20),
            P("Moutarde à l'ancienne", "kg", 7.10), P("Fond de veau", "kg", 18.00)]),
        Supplier("fromagerie", "Fromagerie Bel Air", "EURL", "831550428", ["3 chemin du Bel Air", "69210 L'Arbresle"], "FBA", "A", "virement", 30, [
            P("Comté 18 mois", "kg", 24.00), P("Saint-Marcellin", "pièce", 2.40),
            P("Fourme d'Ambert", "kg", 17.50), P("Tomme de Savoie", "kg", 16.80)], scanned=True),
        Supplier("cave", "Cave des Coteaux", "SARL", "419385522", ["12 quai Saint-Vincent", "69001 Lyon"], "CC", "C", "virement", 30, [
            P("Côtes-du-Rhône rouge AOP", "bouteille", 6.80, "20"), P("Saint-Joseph rouge", "bouteille", 14.50, "20"),
            P("Mâcon-Villages blanc", "bouteille", 8.20, "20"), P("Beaujolais-Villages", "bouteille", 6.10, "20"),
            P("Crémant de Bourgogne", "bouteille", 9.40, "20"), P("Condrieu", "bouteille", 32.00, "20")]),
        Supplier("brasserie", "Brasserie du Confluent", "SAS", "807114395", ["27 cours Charlemagne", "69002 Lyon"], "BDC", "A", "virement", 30, [
            P("Fût bière blonde 30 L", "fût", 98.00, "20"), P("Bière ambrée 33 cl (carton 24)", "carton", 31.20, "20"),
            P("Jus de pomme artisanal 1 L", "bouteille", 3.20), P("Eau minérale gazeuse 50 cl (pack 20)", "pack", 9.60),
            P("Limonade artisanale 33 cl (carton 24)", "carton", 21.60), P("Café en grains 1 kg", "kg", 18.50)]),
        Supplier("energie", "Volta Énergie", "SA", "533207718", ["Service clients professionnels", "92400 Courbevoie"], "VE", "B", "prelevement", 15, []),
        Supplier("hygiene", "Hygiène Pro Services", "SARL", "790441257", ["5 rue des Artisans", "69120 Vaulx-en-Velin"], "HPS", "C", "prelevement", 30, [
            P("Dégraissant cuisine 5 L", "bidon", 18.90, "20"), P("Liquide lave-vaisselle 20 L", "bidon", 64.00, "20"),
            P("Désinfectant surfaces 5 L", "bidon", 21.50, "20"), P("Gants nitrile (boîte 100)", "boîte", 8.90, "20"),
            P("Sacs poubelle 130 L (rouleau)", "rouleau", 12.40, "20")]),
        Supplier("blanchisserie", "Blanchisserie Lumière", "SAS", "512908873", ["66 rue Paul Bert", "69003 Lyon"], "BL", "A", "prelevement", 15, [
            P("Location et entretien du linge de table", "forfait", 245.00, "20"), P("Serviettes tissu (lot de 50)", "lot", 22.00, "20"),
            P("Vestes de cuisine", "pièce", 3.20, "20"), P("Tabliers", "pièce", 1.80, "20")]),
        Supplier("caissepro", "CaissePro", "SAS", "849112360", ["10 rue de la Gare", "35000 Rennes"], "CP", "C", "prelevement", 0, [
            P("Abonnement logiciel de caisse CaissePro, 2 terminaux", "mois", 89.00, "20")]),
        Supplier("tactil", "TactilResto", "SAS", "802775193", ["Parc d'activités Les Milles", "13290 Aix-en-Provence"], "TR", "B", "prelevement", 0, [
            P("Licence logiciel de caisse TactilResto, 1 terminal", "mois", 119.00, "20"),
            P("Maintenance et assistance", "mois", 15.00, "20")]),
        Supplier("comptable", "Cabinet Ravel Expertise", "SELARL", "478330929", ["2 place Bellecour", "69002 Lyon"], "CRE", "A", "virement", 15, [
            P("Honoraires mission de tenue comptable", "mois", 390.00, "20"),
            P("Établissement des bulletins de paie (7 salariés)", "mois", 98.00, "20")]),
        Supplier("equipement", "Équipements CHR Rhône", "SAS", "530882196", ["ZA du Puy d'Or", "69760 Limonest"], "ECR", "A", "virement", 30, [
            P("Four mixte professionnel 10 niveaux GN 1/1", "pièce", 8900.00, "20"),
            P("Installation et mise en service", "forfait", 600.00, "20")]),
        Supplier("telecom", "Fibrazur Télécom", "SAS", "811023455", ["Service entreprises", "06200 Nice"], "FZ", "C", "prelevement", 10, [
            P("Forfait fibre professionnelle et ligne fixe", "mois", 45.00, "20")]),
    ]
}  # fmt: skip

# Coordonnées fictives (domaines réservés « .example ») utilisées par les actions de démonstration.
CONTACTS = {
    "Primeurs du Val": ("commandes@primeurs-du-val.example", "Sophie Lambert"),
    "Boucherie Marchand": ("contact@boucherie-marchand.example", "Marc Marchand"),
    "Marée Atlantique": ("pro@maree-atlantique.example", "Julien Costa"),
    "Laiterie des Monts": ("commandes@laiterie-des-monts.example", None),
    "Cave des Coteaux": ("pro@cave-des-coteaux.example", "Élise Ferrand"),
    "Volta Énergie": ("pro@volta-energie.example", None),
    "TactilResto": ("resiliation@tactilresto.example", None),
    "CaissePro": ("support@caissepro.example", None),
    "Delmas Conseil": ("comptabilite@delmas-conseil.example", "Anne Delmas"),
    "Atelier Morel Architectes": ("contact@atelier-morel.example", None),
}

CUSTOMERS = [
    ("Atelier Morel Architectes", "533901244", ["18 rue Childebert", "69002 Lyon"]),
    ("Delmas Conseil", "820417736", ["101 cours Gambetta", "69003 Lyon"]),
    ("Association des Commerçants de la Presqu'île", None, ["Maison des associations", "69002 Lyon"]),
    ("Clinique vétérinaire des Brotteaux", "450228193", ["7 boulevard des Brotteaux", "69006 Lyon"]),
    ("Studio Graphique Lumen", "882104470", ["40 rue Burdeau", "69001 Lyon"]),
]  # fmt: skip


@dataclass
class Line:
    product: Product
    qty: Decimal

    @property
    def total(self) -> Decimal:
        return money(self.qty * self.product.price)


@dataclass
class Invoice:
    issuer: dict
    recipient: dict
    number: str
    issue: date
    due: date
    lines: list[Line]
    layout: str
    supplier_key: str | None = None
    customer: str | None = None
    duplicata: bool = False
    note: str | None = None

    @property
    def ht(self) -> Decimal:
        return sum((l.total for l in self.lines), D(0))

    def vat_groups(self) -> dict[Decimal, tuple[Decimal, Decimal]]:
        bases: dict[Decimal, Decimal] = defaultdict(lambda: D(0))
        for l in self.lines:
            bases[l.product.vat] += l.total
        return {rate: (base, money(base * rate / 100)) for rate, base in sorted(bases.items())}

    @property
    def tva(self) -> Decimal:
        return sum((v for _, v in self.vat_groups().values()), D(0))

    @property
    def ttc(self) -> Decimal:
        return self.ht + self.tva


@dataclass
class World:
    start: date
    end: date
    invoices: list[Invoice] = field(default_factory=list)
    sales: list[dict] = field(default_factory=list)
    bank: list[tuple[date, str, Decimal]] = field(default_factory=list)
    opening_balance: Decimal = D("24500.00")


# --- Activité du restaurant ------------------------------------------------------------------

SEASON = {1: .86, 2: .9, 3: .96, 4: 1.0, 5: 1.05, 6: 1.1, 7: 1.02, 8: .82, 9: 1.0, 10: 1.0, 11: .95, 12: 1.14}  # fmt: skip


def is_closed(d: date) -> bool:
    # Fermé le lundi, deux semaines en août, et le 1er janvier.
    return d.weekday() == 0 or (d.month == 8 and 4 <= d.day <= 18) or (d.month, d.day) == (1, 1)


def simulate_sales(world: World, rng: random.Random) -> None:
    d = world.start
    while d <= world.end:
        if not is_closed(d):
            season = SEASON[d.month]
            wd = d.weekday()
            lunch_cov = rng.gauss(38 if wd < 5 else 46, 4) * season
            dinner_cov = 0.0 if wd == 6 else rng.gauss(30 * (1.4 if wd in (4, 5) else 1.0), 4) * season
            lunch_cov, dinner_cov = max(0, round(lunch_cov)), max(0, round(dinner_cov))
            lunch_ttc = D(str(round(lunch_cov * rng.gauss(21.8, 1.0), 2)))
            dinner_ttc = D(str(round(dinner_cov * rng.gauss(36.5, 2.0), 2)))
            # Part nourriture (TVA 10 %) et boissons (TVA 20 %) dans le TTC.
            food_ttc = lunch_ttc * D("0.74") + dinner_ttc * D("0.64")
            drinks_ttc = lunch_ttc + dinner_ttc - food_ttc
            food_ht, drinks_ht = money(food_ttc / D("1.10")), money(drinks_ttc / D("1.20"))
            ttc = money(lunch_ttc + dinner_ttc)
            tva = ttc - food_ht - drinks_ht
            vouchers = money(lunch_ttc * D(str(rng.uniform(0.10, 0.16)))) if wd < 5 else D(0)
            cash = money((ttc - vouchers) * D(str(rng.uniform(0.06, 0.11))))
            card = ttc - vouchers - cash
            world.sales.append(dict(day=d, covers=lunch_cov + dinner_cov, food_ht=food_ht, drinks_ht=drinks_ht,
                                    total_ht=food_ht + drinks_ht, tva=tva, ttc=ttc, card=card, cash=cash,
                                    vouchers=vouchers))  # fmt: skip
        d += timedelta(days=1)


def _make_lines(
    rng: random.Random, products: list[Product], target: Decimal, *, n=(4, 7), price_factor=None
) -> list[Line]:
    count = min(len(products), rng.randint(*n))
    chosen = rng.sample(products, count)
    weights = [rng.uniform(0.5, 1.5) for _ in chosen]
    total_w = sum(weights)
    lines = []
    for product, w in zip(chosen, weights, strict=True):
        price = product.price * D(str(price_factor(product))) if price_factor else product.price
        price = price.quantize(CENT)
        alloc = target * D(str(w / total_w))
        step = D("0.5") if product.unit in ("kg", "L") else D(1)
        qty = max(step, (alloc / price / step).quantize(D(1), rounding=ROUND_HALF_UP) * step)
        lines.append(Line(Product(product.name, product.unit, price, product.vat), qty))
    return lines


def simulate_purchases(world: World, rng: random.Random) -> None:
    company = {"name": COMPANY["name"], "siren": COMPANY["siren"], "address": COMPANY["address"],
               "legal": COMPANY["legal_form"]}  # fmt: skip
    sales_by_day = {s["day"]: s for s in world.sales}
    counters: dict[str, int] = defaultdict(int)
    end = world.end

    salmon_from = end - timedelta(days=100)
    bavette_from = end - timedelta(days=70)
    cream_from = end - timedelta(days=60)
    overuse_from = end - timedelta(days=75)

    def food_ht_between(a: date, b: date) -> Decimal:
        return sum((s["food_ht"] for d, s in sales_by_day.items() if a <= d <= b), D(0))

    def drinks_ht_between(a: date, b: date) -> Decimal:
        return sum((s["drinks_ht"] for d, s in sales_by_day.items() if a <= d <= b), D(0))

    def issue(key: str, when: date, lines: list[Line], **extra) -> Invoice:
        s = SUPPLIERS[key]
        counters[key] += 1
        number = f"{s.prefix}-{when.year}-{counters[key] + 100:04d}"
        inv = Invoice(issuer={"name": s.name, "siren": s.siren, "address": s.address, "legal": s.legal},
                      recipient=company, number=number, issue=when, due=when + timedelta(days=s.terms_days),
                      lines=lines, layout=s.layout, supplier_key=key, **extra)  # fmt: skip
        world.invoices.append(inv)
        return inv

    def factor(p: Product, when: date) -> float:
        if p.name.startswith("Pavé de saumon") and when >= salmon_from:
            return 1.22
        if p.name.startswith("Bavette") and when >= bavette_from:
            return 1.09
        if p.name.startswith("Crème liquide") and when >= cream_from:
            return 1.12
        return 1.0

    # Livraisons hebdomadaires et bimensuelles, proportionnelles à l'activité.
    weekly = {"primeur": (1, 0.20), "boucherie": (3, 0.33), "maree": (2, 0.22)}
    d = world.start
    while d <= end:
        for key, (weekday, share) in weekly.items():
            if d.weekday() == weekday and not is_closed(d):
                base = food_ht_between(d - timedelta(days=7), d - timedelta(days=1)) or D(4000)
                target = base * D("0.29") * D(str(share)) * D(str(rng.uniform(0.92, 1.08)))
                if key in ("boucherie", "maree") and d >= overuse_from:
                    target *= D("1.13")  # volumes achetés en hausse, sans hausse de fréquentation
                if target > 50:
                    issue(
                        key,
                        d,
                        _make_lines(rng, SUPPLIERS[key].products, target, price_factor=lambda p, d=d: factor(p, d)),
                    )
        if d.weekday() == 4 and d.isocalendar().week % 2 == 0 and not is_closed(d):
            base = food_ht_between(d - timedelta(days=14), d - timedelta(days=1)) or D(8000)
            target = base * D("0.29") * D("0.09") * D(str(rng.uniform(0.9, 1.1)))
            if target > 50:
                issue(
                    "laiterie",
                    d,
                    _make_lines(
                        rng, SUPPLIERS["laiterie"].products, target, n=(3, 5), price_factor=lambda p, d=d: factor(p, d)
                    ),
                )
        d += timedelta(days=1)

    # Fournisseurs mensuels.
    month = date(world.start.year, world.start.month, 1)
    while month <= end:
        last = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
        food = food_ht_between(month, last)

        def on(day: int) -> date:
            return month.replace(day=min(day, last.day))

        if on(6) <= end:
            issue("epicerie", on(6), _make_lines(rng, SUPPLIERS["epicerie"].products, food * D("0.29") * D("0.10")))
        # Boissons : réassort deux fois par mois, au rythme des ventes des deux semaines passées.
        for day in (6, 20):
            when = on(day)
            while is_closed(when) and when < last:
                when += timedelta(days=1)
            if when > end or is_closed(when):
                continue
            window = max(world.start, when - timedelta(days=14))
            days = (when - window).days
            sold = drinks_ht_between(window, when - timedelta(days=1))
            sold = sold * 14 / days if days >= 4 else D(6000)
            if sold > 300:
                issue("cave", when, _make_lines(rng, SUPPLIERS["cave"].products, sold * D("0.17"), n=(3, 5)))
                issue("brasserie", when, _make_lines(rng, SUPPLIERS["brasserie"].products, sold * D("0.08"), n=(3, 5)))
        if on(12) <= end:
            issue(
                "fromagerie",
                on(12),
                _make_lines(
                    rng, SUPPLIERS["fromagerie"].products, (food or D(30000)) * D("0.29") * D("0.06"), n=(3, 4)
                ),
            )
        if on(3) <= end:
            # Électricité : la facture de régularisation à J-60 environ est anormalement élevée.
            winter = month.month in (11, 12, 1, 2, 3)
            hp = D(rng.randint(3600, 4100) if winter else rng.randint(2600, 3000))
            months_before_end = (end.year - month.year) * 12 + end.month - month.month
            note = None
            if months_before_end == 2:
                hp *= D("2.1")
                note = "Consommation estimée (relevé de compteur non transmis)"
            hc = (hp * D("0.45")).quantize(D(1))
            lines = [Line(P("Abonnement puissance 36 kVA", "mois", "89.40", "20"), D(1)),
                     Line(P("Consommation heures pleines", "kWh", "0.2014", "20"), hp),
                     Line(P("Consommation heures creuses", "kWh", "0.1568", "20"), hc),
                     Line(P("Accise sur l'électricité", "kWh", "0.0225", "20"), hp + hc)]  # fmt: skip
            for line in lines:
                line.qty = line.qty.quantize(D(1))
            issue("energie", on(3), lines, note=note)
            issue("telecom", on(3), [Line(SUPPLIERS["telecom"].products[0], D(1))])
            issue("comptable", on(3), [Line(p, D(1)) for p in SUPPLIERS["comptable"].products])
        if on(1) <= end:
            issue("tactil", on(1), [Line(p, D(1)) for p in SUPPLIERS["tactil"].products])
            # Migration vers CaissePro six mois avant la fin… sans résilier l'ancien logiciel.
            if month >= date(end.year, end.month, 1) - timedelta(days=170):
                issue("caissepro", on(1), [Line(SUPPLIERS["caissepro"].products[0], D(1))])
        if on(20) <= end:
            issue(
                "hygiene", on(20), _make_lines(rng, SUPPLIERS["hygiene"].products, D(rng.uniform(190, 260)), n=(3, 5))
            )
            blanch = [Line(SUPPLIERS["blanchisserie"].products[0], D(1))] + _make_lines(
                rng, SUPPLIERS["blanchisserie"].products[1:], D(rng.uniform(110, 150)), n=(2, 3)
            )
            issue("blanchisserie", on(20), blanch)
        month = last + timedelta(days=1)

    # Achat d'un four (investissement) sept mois avant la fin.
    oven = end - timedelta(days=200)
    while is_closed(oven):
        oven += timedelta(days=1)
    issue("equipement", oven, [Line(p, D(1)) for p in SUPPLIERS["equipement"].products])

    # Commande de fin d'année chez le caviste : grosse facture récente, à payer bientôt.
    big = end - timedelta(days=4)
    issue("cave", big, [Line(P("Champagne brut, cuvée de réserve", "bouteille", "24.50", "20"), D(96)),
                        Line(P("Condrieu", "bouteille", "32.00", "20"), D(48)),
                        Line(P("Saint-Joseph rouge", "bouteille", "14.50", "20"), D(120))])  # fmt: skip

    # Factures de privatisation émises par le restaurant.
    sale_counter = 0
    for i, (cust_name, cust_siren, cust_addr) in enumerate(CUSTOMERS * 2):
        when = world.start + timedelta(days=30 + i * 33 + rng.randint(0, 9))
        if when > end - timedelta(days=8):
            break
        sale_counter += 1
        guests = rng.randint(18, 40)
        lines = [Line(P(f"Menu privatisation {guests} convives", "convive", rng.choice(["48.00", "55.00", "62.00"]), "10"), D(guests)),
                 Line(P("Forfait boissons et vins", "convive", "18.00", "20"), D(guests)),
                 Line(P("Mise à disposition de la salle", "forfait", "250.00", "20"), D(1))]  # fmt: skip
        inv = Invoice(issuer=company, recipient={"name": cust_name, "siren": cust_siren, "address": cust_addr, "legal": ""},
                      number=f"BT-{when.year}-{sale_counter:03d}", issue=when, due=when + timedelta(days=30),
                      lines=lines, layout="A", customer=cust_name)  # fmt: skip
        world.invoices.append(inv)


# --- Banque ----------------------------------------------------------------------------------


def next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


SHORT_LABELS = {
    "primeur": "PRIMEURS DU VAL", "boucherie": "BOUCHERIE MARCHAND", "maree": "MAREE ATLANTIQUE",
    "laiterie": "LAITERIE DES MONTS", "epicerie": "EPICERIE PRO RHONE", "fromagerie": "FROMAGERIE BEL AIR",
    "cave": "CAVE DES COTEAUX", "brasserie": "BRASSERIE DU CONFLUENT", "energie": "VOLTA ENERGIE",
    "hygiene": "HYGIENE PRO SERVICES", "blanchisserie": "BLANCHISSERIE LUMIERE", "caissepro": "CAISSEPRO",
    "tactil": "TACTILRESTO", "comptable": "CABINET RAVEL EXPERTISE", "telecom": "FIBRAZUR TELECOM",
    "equipement": "EQUIPEMENTS CHR RHONE",
}  # fmt: skip


def simulate_bank(world: World, rng: random.Random, missing_invoices: set[str]) -> None:
    end = world.end
    tx = world.bank

    def add(d: date, label: str, amount: Decimal) -> None:
        d = next_business_day(d)
        if world.start <= d <= end:
            tx.append((d, label, money(amount)))

    # Encaissements CB (J+1), espèces (dépôt le mardi), titres-restaurant (le 10 du mois).
    card_by_day: dict[date, Decimal] = defaultdict(lambda: D(0))
    cash_pending = D(0)
    vouchers_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: D(0))
    card_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: D(0))
    for s in world.sales:
        card_by_day[next_business_day(s["day"] + timedelta(days=1))] += s["card"]
        vouchers_by_month[(s["day"].year, s["day"].month)] += s["vouchers"]
        card_by_month[(s["day"].year, s["day"].month)] += s["card"]
    for d, amount in sorted(card_by_day.items()):
        add(d, f"REMISE CB {d.strftime('%d%m')} TPE 4471023", amount)
    d = world.start
    while d <= end:
        cash_pending += next((s["cash"] for s in world.sales if s["day"] == d), D(0))
        if d.weekday() == 1 and cash_pending > 0:
            add(d, "VERSEMENT ESPECES AGENCE LYON CORDELIERS", cash_pending)
            cash_pending = D(0)
        d += timedelta(days=1)

    month = date(world.start.year, world.start.month, 1)
    prev_key = None
    while month <= end:
        last = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
        key = (month.year, month.month)
        if prev_key:
            add(month.replace(day=10), "REMISE TITRES RESTAURANT CENTRALE TR", vouchers_by_month[prev_key] * D("0.962"))
            add(month.replace(day=3), "COMMISSIONS CB MOIS PRECEDENT", -card_by_month[prev_key] * D("0.011"))
        add(month.replace(day=1), "FRAIS TENUE DE COMPTE PRO", D("-32.00"))
        add(month.replace(day=5), "VIR SEPA SCI LES TILLEULS LOYER", D("-3800.00"))
        add(month.replace(day=8), "PRLV SEPA AMBIANCE SONORE PRO", D("-29.00"))
        add(month.replace(day=10), "ECHEANCE PRET PROFESSIONNEL N 0412", D("-1650.00"))
        add(month.replace(day=15), "PRLV SEPA URSSAF RHONE-ALPES", -D(str(round(rng.uniform(5900, 6200), 2))))
        add(month.replace(day=25), "VIR SEPA REMBT COMPTE COURANT ASSOCIE", D("-2000.00"))
        if month.month in (3, 6, 9, 12):
            add(month.replace(day=15), f"PRLV SEPA DGFIP IS ACOMPTE {month.month:02d}{month.year}", D("-3100.00"))
        if month.month == 12:
            add(month.replace(day=15), "PRLV SEPA DGFIP CFE 2025", D("-1180.00"))
        if month.month in (1, 4, 7, 10):
            add(month.replace(day=15), "PRLV SEPA ASSURANCES MUTUELLES DU RHONE", D("-1950.00"))
        salary_day = last
        while salary_day.weekday() >= 5:
            salary_day -= timedelta(days=1)
        if salary_day <= end:
            tx.append(
                (
                    salary_day,
                    f"VIR SEPA SALAIRES {MONTHS_FR[month.month - 1].upper()}",
                    -D(str(round(rng.uniform(11900, 12400), 2))),
                )
            )
            tx.append((salary_day, "VIR SEPA REMUNERATION GERANT", D("-2400.00")))
        prev_key = key
        month = last + timedelta(days=1)

    # TVA : reversée le 19 du mois suivant (collectée − déductible).
    collected: dict[tuple[int, int], Decimal] = defaultdict(lambda: D(0))
    deductible: dict[tuple[int, int], Decimal] = defaultdict(lambda: D(0))
    for s in world.sales:
        collected[(s["day"].year, s["day"].month)] += s["tva"]
    for inv in world.invoices:
        if inv.duplicata:
            continue
        k = (inv.issue.year, inv.issue.month)
        if inv.customer:
            collected[k] += inv.tva
        else:
            deductible[k] += inv.tva
    for (y, m), amount in sorted(collected.items()):
        due = date(y + (m == 12), m % 12 + 1, 19)
        net = amount - deductible[(y, m)]
        if net > 0:
            add(due, f"PRLV SEPA DGFIP TVA {m:02d}{y}", -net)

    # Paiements des factures.
    for inv in world.invoices:
        if inv.duplicata:
            continue
        if inv.customer:
            if inv.customer == "Delmas Conseil" and inv.issue > end - timedelta(days=150):
                continue  # facture restée impayée
            add(
                inv.due + timedelta(days=rng.randint(-3, 18)),
                f"VIR SEPA {inv.customer.upper()[:28]} {inv.number}",
                inv.ttc,
            )
            continue
        s = SUPPLIERS[inv.supplier_key]
        pay_on = inv.due
        if pay_on > end:
            continue  # pas encore payée
        if s.payment == "prelevement":
            label = f"PRLV SEPA {SHORT_LABELS[inv.supplier_key]} {inv.number}"
        else:
            label = f"VIR SEPA {SHORT_LABELS[inv.supplier_key]} FACT {inv.number}"
        add(pay_on, label, -inv.ttc)

    tx.sort(key=lambda t: (t[0], -t[2]))

    # Solde d'ouverture choisi pour finir autour de 19 000 € sans jamais passer sous 2 000 €.
    running, lowest = D(0), D(0)
    for _, _, amount in tx:
        running += amount
        lowest = min(lowest, running)
    world.opening_balance = max(D("19000") - running, D("2000") - lowest).quantize(CENT)


# --- Rendu PDF ---------------------------------------------------------------------------------


def _table(inv: Invoice, layout: str) -> Table:
    if layout == "A":
        head = ["Désignation", "Qté", "Unité", "P.U. HT", "TVA", "Montant HT"]
        rows = [[l.product.name, fr(l.qty, 1 if l.qty % 1 else 0), l.product.unit, fr(l.product.price, 4 if l.product.price < 1 else 2),
                 f"{fr(l.product.vat, 1)} %", fr(l.total)] for l in inv.lines]  # fmt: skip
        widths = [72 * mm, 16 * mm, 20 * mm, 24 * mm, 16 * mm, 28 * mm]
    elif layout == "B":
        head = ["Article", "Quantité", "Prix unitaire", "Total HT"]
        rows = [
            [
                l.product.name,
                f"{fr(l.qty, 1 if l.qty % 1 else 0)} {l.product.unit}",
                f"{fr(l.product.price, 4 if l.product.price < 1 else 2)} €",
                f"{fr(l.total)} €",
            ]
            for l in inv.lines
        ]
        widths = [92 * mm, 28 * mm, 30 * mm, 26 * mm]
    else:
        head = ["Réf.", "Description", "Qté", "PU HT", "Total HT"]
        rows = [
            [
                f"{i + 1:03d}",
                l.product.name,
                fr(l.qty, 1 if l.qty % 1 else 0),
                fr(l.product.price, 4 if l.product.price < 1 else 2),
                fr(l.total),
            ]
            for i, l in enumerate(inv.lines)
        ]
        widths = [14 * mm, 96 * mm, 18 * mm, 24 * mm, 24 * mm]
    table = Table([head, *rows], colWidths=widths)
    accent = {"A": colors.HexColor("#2f4858"), "B": colors.HexColor("#7a3e2e"), "C": colors.HexColor("#33553c")}[layout]
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8bcc0")), ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))  # fmt: skip
    return table


def render_invoice(inv: Invoice) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Facture {inv.number}")
    width, height = A4
    layout = inv.layout
    left, right = 18 * mm, width - 18 * mm
    issuer, recipient = inv.issuer, inv.recipient

    def text(x, y, value, font="Helvetica", size=9, align="left", color=colors.black):
        c.setFont(font, size)
        c.setFillColor(color)
        {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[align](x, y, value)

    y = height - 22 * mm
    if layout == "A":
        text(left, y, issuer["name"], "Helvetica-Bold", 15)
        for i, line in enumerate(issuer["address"]):
            text(left, y - 14 - i * 11, line)
        text(
            left,
            y - 14 - 2 * 11,
            f"SIRET {issuer['siren'][:3]} {issuer['siren'][3:6]} {issuer['siren'][6:]} 00018"
            if issuer.get("siren")
            else "",
        )
        text(right, y, "FACTURE" + (" — DUPLICATA" if inv.duplicata else ""), "Helvetica-Bold", 15, "right")
        text(right, y - 16, f"N° de facture : {inv.number}", align="right")
        text(right, y - 28, f"Date de facture : {fr_date(inv.issue)}", align="right")
        text(right, y - 40, f"Échéance : {fr_date(inv.due)}", align="right")
        by = y - 78
        text(right - 70 * mm, by, "Facturé à :", "Helvetica-Bold")
        text(right - 70 * mm, by - 12, recipient["name"])
        for i, line in enumerate(recipient["address"]):
            text(right - 70 * mm, by - 24 - i * 11, line)
        if recipient.get("siren"):
            text(right - 70 * mm, by - 46, f"SIREN {recipient['siren']}")
        ty = by - 70
    elif layout == "B":
        c.setFillColor(colors.HexColor("#7a3e2e"))
        c.rect(0, height - 34 * mm, width, 34 * mm, stroke=0, fill=1)
        text(left, height - 17 * mm, issuer["name"], "Helvetica-Bold", 17, color=colors.white)
        text(left, height - 24 * mm, " · ".join(issuer["address"]), size=9, color=colors.white)
        y = height - 48 * mm
        text(
            left,
            y,
            f"Facture n° {inv.number} du {fr_date(inv.issue)}" + ("  (DUPLICATA)" if inv.duplicata else ""),
            "Helvetica-Bold",
            12,
        )
        text(left, y - 18, f"Client : {recipient['name']}")
        text(left, y - 30, " · ".join(recipient["address"]))
        ty = y - 56
    else:
        text(left, y, "FACTURE", "Helvetica-Bold", 20, color=colors.HexColor("#33553c"))
        text(left, y - 18, issuer["name"], "Helvetica-Bold", 11)
        for i, line in enumerate(issuer["address"]):
            text(left, y - 30 - i * 11, line)
        text(right, y - 4, f"Réf. facture : {inv.number}", align="right")
        text(right, y - 16, f"Date d'émission : {fr_long_date(inv.issue)}", align="right")
        text(right, y - 28, f"Date limite de paiement : {fr_long_date(inv.due)}", align="right")
        by = y - 70
        text(left, by, "Adressé à", "Helvetica-Bold")
        text(left, by - 12, recipient["name"])
        for i, line in enumerate(recipient["address"]):
            text(left, by - 24 - i * 11, line)
        ty = by - 56

    table = _table(inv, layout)
    tw, th = table.wrapOn(c, right - left, ty)
    table.drawOn(c, left, ty - th)
    y = ty - th - 22

    groups = inv.vat_groups()
    rows: list[tuple[str, str]] = []
    if layout == "A":
        rows.append(("Total HT", f"{fr(inv.ht)} €"))
        for rate, (base, amount) in groups.items():
            rows.append((f"TVA {fr(rate, 1)} % sur {fr(base)}", f"{fr(amount)} €"))
        rows.append(("Total TTC", f"{fr(inv.ttc)} €"))
    elif layout == "B":
        rows += [
            ("Montant HT", f"{fr(inv.ht)} €"),
            ("Montant TVA", f"{fr(inv.tva)} €"),
            ("Net à payer", f"{fr(inv.ttc)} €"),
        ]
    else:
        rows.append(("Sous-total HT", fr(inv.ht)))
        for rate, (_base, amount) in groups.items():
            rows.append((f"TVA {fr(rate, 1)} %", fr(amount)))
        rows.append(("Total TTC (EUR)", fr(inv.ttc)))
    for i, (label, value) in enumerate(rows):
        bold = i == len(rows) - 1
        text(right - 45 * mm, y - i * 14, label, "Helvetica-Bold" if bold else "Helvetica", 9.5, "right")
        text(right, y - i * 14, value, "Helvetica-Bold" if bold else "Helvetica", 9.5, "right")
    y -= len(rows) * 14 + 16

    if layout == "B":
        text(left, y, f"À régler avant le {fr_date(inv.due)}.")
        y -= 14
    if inv.note:
        text(left, y, inv.note, "Helvetica-Oblique")
        y -= 14
    terms = "Paiement à réception" if inv.due == inv.issue else f"Paiement à {(inv.due - inv.issue).days} jours"
    text(
        left,
        30 * mm,
        f"{terms}. Pénalités de retard : 3 fois le taux d'intérêt légal. Indemnité forfaitaire de recouvrement : 40 €.",
        size=7,
        color=colors.HexColor("#555555"),
    )
    siren = issuer.get("siren")
    if siren:
        text(left, 25 * mm, f"{issuer['name']} — {issuer.get('legal', '')} — RCS Lyon {siren[:3]} {siren[3:6]} {siren[6:]} — TVA intracommunautaire FR27{siren}",
             size=7, color=colors.HexColor("#555555"))  # fmt: skip
    c.showPage()
    c.save()
    return buf.getvalue()


def render_delivery_note(supplier: Supplier, when: date, number: str) -> bytes:
    """Bon de livraison : ressemble à une facture mais ne contient aucun montant."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 15)
    c.drawString(18 * mm, height - 22 * mm, supplier.name)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 18 * mm, height - 22 * mm, "BON DE LIVRAISON")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 18 * mm, height - 30 * mm, f"BL n° {number} — livré le {fr_date(when)}")
    c.drawString(18 * mm, height - 40 * mm, f"Livré à : {COMPANY['name']}, {', '.join(COMPANY['address'])}")
    table = Table([["Article", "Quantité livrée"]] + [[p.name, f"{random.Random(number).randint(2, 9)} {p.unit}"] for p in supplier.products[:5]],
                  colWidths=[110 * mm, 40 * mm])  # fmt: skip
    table.setStyle(
        TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9)])
    )
    _, th = table.wrapOn(c, 150 * mm, 200 * mm)
    table.drawOn(c, 18 * mm, height - 50 * mm - th)
    c.drawString(18 * mm, height - 60 * mm - th, "Signature du client à réception :")
    c.save()
    return buf.getvalue()


def scan_pdf(pdf: bytes, rng: random.Random, *, as_photo: bool = False) -> bytes:
    """Simule un document numérisé (ou photographié) : image seule, légèrement de travers."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageEnhance, ImageFilter

    page = pdfium.PdfDocument(pdf)[0]
    image = page.render(scale=200 / 72).to_pil().convert("L")
    image = image.rotate(rng.uniform(-0.8, 0.8), expand=True, fillcolor=245, resample=Image.BICUBIC)
    image = ImageEnhance.Contrast(image).enhance(0.9).filter(ImageFilter.GaussianBlur(0.4))
    out = io.BytesIO()
    if as_photo:
        image.convert("RGB").save(out, "JPEG", quality=82)
        return out.getvalue()
    jpeg = io.BytesIO()
    image.save(jpeg, "JPEG", quality=80)
    c = canvas.Canvas(out, pagesize=A4)
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(io.BytesIO(jpeg.getvalue())), 0, 0, width=A4[0], height=A4[1])
    c.save()
    return out.getvalue()


# --- Orchestration -----------------------------------------------------------------------------


@dataclass
class DemoResult:
    out_dir: Path
    invoices: int
    files: int
    sales_days: int
    bank_rows: int
    start: date
    end: date


def generate(out_dir: Path, *, end: date | None = None, seed: int = 2026) -> DemoResult:
    rng = random.Random(seed)
    end = end or date.today() - timedelta(days=1)
    start = date(end.year - 1, end.month, 1)
    world = World(start=start, end=end)

    simulate_sales(world, rng)
    simulate_purchases(world, rng)

    # Deux factures de boucherie jamais reçues (payées, mais sans justificatif).
    boucherie = [i for i in world.invoices if i.supplier_key == "boucherie" and i.issue < end - timedelta(days=60)]
    missing = {boucherie[-9].number, boucherie[-14].number}
    # Une facture du primeur renvoyée en duplicata une semaine plus tard.
    primeur = [i for i in world.invoices if i.supplier_key == "primeur" and i.issue < end - timedelta(days=40)]
    original = primeur[-3]
    dup = Invoice(**{**original.__dict__, "duplicata": True})

    simulate_bank(world, rng, missing)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "factures").mkdir(parents=True)
    (out_dir / "banque").mkdir()
    (out_dir / "caisse").mkdir()

    files = 0
    scans = 0
    truth = []
    for inv in world.invoices:
        if inv.number in missing:
            continue
        pdf = render_invoice(inv)
        who = inv.customer or SUPPLIERS[inv.supplier_key].name
        stem = f"{inv.issue.isoformat()}_{who}_{inv.number}".replace(" ", "-").replace("'", "")
        if inv.supplier_key and SUPPLIERS[inv.supplier_key].scanned:
            scans += 1
            if scans == 3:
                (out_dir / "factures" / f"IMG_{inv.issue.strftime('%Y%m%d')}_1432.jpg").write_bytes(
                    scan_pdf(pdf, rng, as_photo=True)
                )
            else:
                (out_dir / "factures" / f"scan_{inv.issue.strftime('%Y%m%d')}_{scans:03d}.pdf").write_bytes(
                    scan_pdf(pdf, rng)
                )
        else:
            (out_dir / "factures" / f"{stem}.pdf").write_bytes(pdf)
        truth.append(
            {
                "file": sorted((out_dir / "factures").iterdir(), key=lambda p: p.stat().st_mtime_ns)[-1].name,
                "direction": "sale" if inv.customer else "purchase",
                "party": inv.customer or SUPPLIERS[inv.supplier_key].name,
                "number": inv.number,
                "issue": inv.issue.isoformat(),
                "due": inv.due.isoformat(),
                "ht": str(inv.ht),
                "tva": str(inv.tva),
                "ttc": str(inv.ttc),
                "lines": len(inv.lines),
            }
        )
        files += 1
        if inv is original:
            (
                out_dir / "factures" / f"{(inv.issue + timedelta(days=7)).isoformat()}_relance-primeur_DUPLICATA.pdf"
            ).write_bytes(render_invoice(dup))
            files += 1
            # Le même fichier enregistré deux fois dans le dossier de téléchargements.
            shutil.copy(out_dir / "factures" / f"{stem}.pdf", out_dir / "factures" / f"{stem} (1).pdf")
            files += 1
    bl_date = end - timedelta(days=12)
    (out_dir / "factures" / f"{bl_date.isoformat()}_BL-boucherie.pdf").write_bytes(
        render_delivery_note(SUPPLIERS["boucherie"], bl_date, f"BL-{bl_date.strftime('%y%m%d')}-07")
    )
    files += 1

    with (out_dir / "caisse" / f"journal-caisse_{start.isoformat()}_{end.isoformat()}.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Date", "Couverts", "CA nourriture HT", "CA boissons HT", "Total HT", "TVA", "Total TTC",
                    "CB", "Espèces", "Titres-restaurant"])  # fmt: skip
        for s in world.sales:
            w.writerow([fr_date(s["day"]), s["covers"], fr(s["food_ht"]), fr(s["drinks_ht"]), fr(s["total_ht"]),
                        fr(s["tva"]), fr(s["ttc"]), fr(s["card"]), fr(s["cash"]), fr(s["vouchers"])])  # fmt: skip

    with (out_dir / "banque" / f"releve_{start.isoformat()}_{end.isoformat()}.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Date opération", "Libellé", "Débit", "Crédit", "Solde"])
        balance = world.opening_balance
        for d, label, amount in world.bank:
            balance += amount
            w.writerow(
                [fr_date(d), label, fr(-amount) if amount < 0 else "", fr(amount) if amount > 0 else "", fr(balance)]
            )

    # Valeurs attendues, utilisées par les tests pour mesurer la qualité de l'extraction.
    (out_dir / "verite-terrain.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    return DemoResult(out_dir, len(world.invoices), files, len(world.sales), len(world.bank), start, end)
