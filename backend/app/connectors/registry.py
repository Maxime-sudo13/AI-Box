from .base import Connector, PlannedConnector
from .folder import FolderConnector
from .imap import ImapConnector
from .qonto import QontoConnector

CONNECTORS: dict[str, Connector] = {c.key: c for c in (FolderConnector(), ImapConnector(), QontoConnector())}

# Intégrations prévues par le cahier des charges (section 7), développées selon les besoins
# des premiers clients et les conditions d'accès de chaque éditeur.
PLANNED = (
    PlannedConnector("pennylane", "Pennylane", "Comptabilité", "Factures, écritures et rapprochements."),
    PlannedConnector("sage", "Sage", "Comptabilité", "Écritures et balance."),
    PlannedConnector("cegid", "Cegid", "Comptabilité", "Écritures et balance."),
    PlannedConnector("odoo", "Odoo", "ERP", "Ventes, achats et stocks."),
    PlannedConnector("hubspot", "HubSpot", "CRM", "Clients, contacts et opportunités."),
    PlannedConnector("axonaut", "Axonaut", "Gestion commerciale", "Devis, factures et clients."),
    PlannedConnector("shopify", "Shopify", "E-commerce", "Commandes et produits."),
    PlannedConnector("m365", "Microsoft 365 / OneDrive", "Documents", "Fichiers Excel et documents partagés."),
    PlannedConnector("gdrive", "Google Drive", "Documents", "Fichiers et documents partagés."),
)
