"""Socle des connecteurs.

Un connecteur ne reçoit ni la base de données ni la session : seulement ses réglages, ses
identifiants déchiffrés, les permissions accordées par le dirigeant et un curseur de reprise.
Il renvoie des enregistrements normalisés (documents, opérations bancaires) que le cœur du
boîtier importe par le circuit habituel. Un connecteur défaillant ne peut donc ni écrire
ailleurs, ni bloquer les autres : ses erreurs sont capturées et rattachées à sa connexion.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar


class ConnectorError(Exception):
    """Erreur affichée au dirigeant (message en français, sans détail technique sensible)."""


class AuthError(ConnectorError):
    """Identifiants refusés ou accès expiré : la connexion doit être renouvelée."""


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    write: bool = False
    default: bool = False  # les droits d'écriture ne sont jamais accordés par défaut


@dataclass(frozen=True)
class SettingField:
    key: str
    label: str
    kind: str = "text"  # text, password, number, email
    secret: bool = False
    required: bool = True
    hint: str | None = None
    default: Any = None


@dataclass
class DocumentRecord:
    external_id: str
    filename: str
    data: bytes


@dataclass
class TableRecord:
    """Export CSV (relevé bancaire ou journal de caisse) trouvé par un connecteur."""

    external_id: str
    filename: str
    data: bytes


@dataclass
class BankRecord:
    external_id: str
    booked_on: date
    label: str
    amount: Decimal
    balance: Decimal | None = None


@dataclass
class SyncContext:
    settings: dict[str, Any]
    secrets: dict[str, Any]
    permissions: frozenset[str]
    cursor: dict[str, Any]
    seen: Callable[[str], bool]
    log: list[str] = field(default_factory=list)

    def allowed(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass
class SyncResult:
    documents: list[DocumentRecord] = field(default_factory=list)
    tables: list[TableRecord] = field(default_factory=list)
    transactions: list[BankRecord] = field(default_factory=list)
    cursor: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Appelée après l'import avec les éléments bien traités : actions d'écriture autorisées
    # (déplacer un fichier, marquer un courriel comme lu) puis fermeture des connexions.
    finalize: Callable[[set[str]], None] | None = None


class Connector:
    key: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str]
    online: ClassVar[bool] = True  # nécessite Internet : désactivé en mode « zéro communication externe »
    hosts: ClassVar[tuple[str, ...]] = ()  # seuls hôtes contactés
    fields: ClassVar[tuple[SettingField, ...]] = ()
    permissions: ClassVar[tuple[Permission, ...]] = ()
    data_notice: ClassVar[str] = ""

    def test(self, settings: dict[str, Any], secrets: dict[str, Any]) -> str:
        """Vérifie l'accès ; renvoie un message de succès ou lève ConnectorError."""
        raise NotImplementedError

    def sync(self, ctx: SyncContext) -> SyncResult:
        raise NotImplementedError


@dataclass(frozen=True)
class PlannedConnector:
    """Intégration prévue (cahier des charges, section 7), pas encore disponible."""

    key: str
    name: str
    category: str
    description: str
