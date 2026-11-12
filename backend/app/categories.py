"""Plan de catégories des recettes et des charges.

Volontairement proche du plan comptable (classes 6 et 7) tout en restant lisible par un
dirigeant. Le groupe détermine la place de la catégorie dans le compte de résultat :
`hors_resultat` couvre les flux de trésorerie qui ne sont ni des charges ni des produits
(TVA reversée, capital d'emprunt, virements internes).
"""

from dataclasses import dataclass
from typing import Literal

Group = Literal["recette", "matieres", "externes", "personnel", "impots", "financier", "hors_resultat"]


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    group: Group


CATEGORIES: tuple[Category, ...] = (
    # Recettes
    Category("ventes", "Ventes facturées", "recette"),
    Category("encaissement_cb", "Encaissements carte bancaire", "recette"),
    Category("encaissement_especes", "Dépôts d'espèces", "recette"),
    Category("encaissement_titres", "Titres-restaurant", "recette"),
    Category("autres_recettes", "Autres recettes", "recette"),
    # Achats consommés
    Category("alimentaire", "Matières premières alimentaires", "matieres"),
    Category("boissons", "Boissons", "matieres"),
    Category("marchandises", "Marchandises", "matieres"),
    # Charges externes
    Category("loyer", "Loyer et charges locatives", "externes"),
    Category("energie", "Énergie et eau", "externes"),
    Category("entretien", "Hygiène et entretien", "externes"),
    Category("blanchisserie", "Blanchisserie", "externes"),
    Category("logiciels", "Logiciels et abonnements", "externes"),
    Category("telecom", "Téléphone et internet", "externes"),
    Category("assurance", "Assurances", "externes"),
    Category("honoraires", "Honoraires", "externes"),
    Category("materiel", "Petit matériel", "externes"),
    Category("marketing", "Communication et publicité", "externes"),
    Category("autres_charges", "Autres charges externes", "externes"),
    # Personnel
    Category("salaires", "Salaires", "personnel"),
    Category("remuneration_gerant", "Rémunération du gérant", "personnel"),
    Category("charges_sociales", "Cotisations sociales", "personnel"),
    # Impôts et frais financiers
    Category("impots_taxes", "Impôts et taxes", "impots"),
    Category("frais_bancaires", "Frais bancaires et commissions", "externes"),
    Category("interets", "Intérêts d'emprunt", "financier"),
    # Hors compte de résultat
    Category("tva", "TVA reversée", "hors_resultat"),
    Category("emprunt", "Remboursement d'emprunt", "hors_resultat"),
    Category("impot_societes", "Impôt sur les sociétés", "hors_resultat"),
    Category("immobilisations", "Investissements", "hors_resultat"),
    Category("compte_courant", "Compte courant d'associé", "hors_resultat"),
    Category("virement_interne", "Virement interne", "hors_resultat"),
    Category("a_classer", "À classer", "externes"),
)

BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
CATEGORY_KEYS: frozenset[str] = frozenset(BY_KEY)
PURCHASE_CATEGORIES: tuple[str, ...] = tuple(
    c.key for c in CATEGORIES if c.group in ("matieres", "externes", "impots", "financier")
)

GROUP_LABELS: dict[str, str] = {
    "matieres": "Achats consommés",
    "externes": "Charges externes",
    "personnel": "Personnel",
    "impots": "Impôts et taxes",
    "financier": "Frais financiers",
}
