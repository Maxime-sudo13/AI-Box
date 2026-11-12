"""Catalogue des modules fonctionnels (cahier des charges, section 4).

Chaque entreprise active uniquement les modules qui correspondent à son activité.
`available` indique si le module est livré dans cette version du logiciel.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    name: str
    description: str
    available: bool = False


CATALOG: tuple[Module, ...] = (
    Module(
        "direction",
        "Direction générale",
        "Vue globale : santé de l'entreprise, alertes prioritaires et recommandations.",
        available=True,
    ),
    Module(
        "finance",
        "Gestion financière",
        "Revenus, dépenses, marges, trésorerie prévisionnelle et impayés.",
        available=True,
    ),
    Module(
        "documents",
        "Comptabilité et documents",
        "Import et lecture automatique des factures, classement et rapprochement.",
        available=True,
    ),
    Module(
        "ventes",
        "Ventes et chiffre d'affaires",
        "Analyse des ventes, rentabilité par produit et prévision des revenus.",
    ),
    Module(
        "clients",
        "Clients et CRM",
        "Segmentation, fidélisation, clients inactifs et relances.",
    ),
    Module(
        "achats",
        "Fournisseurs et achats",
        "Comparaison des prix, évolutions tarifaires et dépendances fournisseurs.",
    ),
    Module(
        "stocks",
        "Stocks et logistique",
        "Rotation, stocks dormants, ruptures et réapprovisionnement.",
    ),
    Module(
        "rh",
        "Ressources humaines",
        "Effectifs, masse salariale et absences, sans décision automatisée.",
    ),
    Module(
        "contrats",
        "Contrats et abonnements",
        "Échéances, renouvellements et dépenses récurrentes.",
    ),
    Module(
        "conseiller",
        "Conseiller stratégique IA",
        "Dialogue avec les données de l'entreprise et plans d'action justifiés.",
        available=True,
    ),
)

MODULE_KEYS: frozenset[str] = frozenset(m.key for m in CATALOG)
