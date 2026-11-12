"""Agents spécialisés et périmètre de données de chacun.

Un agent n'accède qu'aux familles de données nécessaires à sa mission. Le cloisonnement est
appliqué avant l'appel des outils : un agent sans accès « personnel » ne voit ni les salaires
ni les cotisations, même dans le relevé bancaire.
"""

from dataclasses import dataclass, replace

from app.categories import BY_KEY
from app.finance.data import Dataset

# Familles de données : ventes, achats, banque, personnel (données RH agrégées), documents.
DOMAINS = ("ventes", "achats", "banque", "personnel", "documents")


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    mission: str
    domains: frozenset[str]
    tools: tuple[str, ...]


AGENTS: dict[str, Agent] = {
    a.key: a
    for a in (
        Agent(
            "financier",
            "Agent financier",
            "Rentabilité, charges et trésorerie.",
            frozenset({"ventes", "achats", "banque", "personnel"}),
            (
                "month_summary",
                "profit_change",
                "compare_months",
                "year_summary",
                "treasury",
                "investment_capacity",
                "top_charges",
                "hiring",
            ),
        ),
        Agent("commercial", "Agent commercial", "Ventes, fréquentation et clients.", frozenset({"ventes"}), ("sales",)),
        Agent(
            "achats",
            "Agent achats",
            "Fournisseurs, prix et abonnements.",
            frozenset({"achats"}),
            ("suppliers", "subscriptions"),
        ),
        Agent(
            "administratif",
            "Agent administratif",
            "Documents, échéances et impayés.",
            frozenset({"ventes", "achats", "banque", "documents"}),
            ("receivables", "documents_status"),
        ),
        Agent(
            "strategique",
            "Agent stratégique",
            "Synthèse, priorités et plans d'action.",
            frozenset({"ventes", "achats", "banque", "personnel", "documents"}),
            ("priorities", "losses", "profit_target", "plan_90"),
        ),
    )
}

TOOL_AGENT = {tool: agent.key for agent in AGENTS.values() for tool in agent.tools}


def scoped(ds: Dataset, agent: Agent) -> Dataset:
    """Vue du jeu de données limitée au périmètre de l'agent."""
    allowed = agent.domains
    txs = ds.txs if "banque" in allowed else []
    if "personnel" not in allowed:
        txs = [t for t in txs if BY_KEY.get(t.category) is None or BY_KEY[t.category].group != "personnel"]
    invoices = [
        inv
        for inv in ds.invoices
        if (inv.direction == "sale" and "ventes" in allowed) or (inv.direction == "purchase" and "achats" in allowed)
    ]
    return replace(ds, txs=txs, invoices=invoices, sales=ds.sales if "ventes" in allowed else [])
