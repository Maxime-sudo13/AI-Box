import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    legal_form: Mapped[str | None] = mapped_column(String(50))
    siren: Mapped[str | None] = mapped_column(String(9))
    sector: Mapped[str | None] = mapped_column(String(200))
    enabled_modules: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Administrateur du boîtier : gère les utilisateurs, les entreprises et le journal.
    is_admin: Mapped[bool] = mapped_column(server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    failed_logins: Mapped[int] = mapped_column(server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base):
    """Rattachement d'un utilisateur à une entreprise, avec son rôle."""

    __tablename__ = "memberships"
    __table_args__ = (CheckConstraint("role IN ('owner', 'manager', 'viewer')", name="role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20))

    user: Mapped[User] = relationship(back_populates="memberships")
    company: Mapped[Company] = relationship(back_populates="memberships")


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Seule l'empreinte du jeton est conservée : une fuite de la base ne donne pas de session.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    # Dernière confirmation du mot de passe : exigée pour les opérations sensibles (niveau 3).
    reauth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditEvent(Base):
    """Journal d'activité : qui a fait quoi, quand, avec quel résultat."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Conservé en clair pour que le journal reste lisible si le compte est supprimé.
    actor_label: Mapped[str | None] = mapped_column(String(254))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20))
    target: Mapped[str | None] = mapped_column(String(300))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(String(45))


# --- Données financières (Phase 2) ---------------------------------------------------------

Money = Numeric(14, 2)


class Party(Base):
    """Tiers : fournisseur ou client."""

    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("company_id", "kind", "name_key", name="uq_parties_company_kind_name"),
        CheckConstraint("kind IN ('supplier', 'customer')", name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200))
    # Nom normalisé (minuscules, sans accents ni forme juridique) pour le rapprochement.
    name_key: Mapped[str] = mapped_column(String(200))
    siren: Mapped[str | None] = mapped_column(String(9))
    category: Mapped[str | None] = mapped_column(String(40))
    # Coordonnées utilisées par les actions (relances, demandes aux fournisseurs).
    email: Mapped[str | None] = mapped_column(String(254))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """Fichier importé, conservé tel quel sur le boîtier."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("company_id", "sha256", name="uq_documents_company_sha256"),
        CheckConstraint(
            "status IN ('verified', 'to_review', 'validated', 'duplicate', 'ignored', 'failed')",
            name="status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    # Méthode de lecture (texte du PDF ou OCR), durée, nombre de pages, extrait du texte.
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    invoice: Mapped["Invoice | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (CheckConstraint("direction IN ('purchase', 'sale')", name="direction"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    direction: Mapped[str] = mapped_column(String(10))
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id", ondelete="SET NULL"), index=True)
    number: Mapped[str | None] = mapped_column(String(60))
    issue_date: Mapped[date | None] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    category: Mapped[str | None] = mapped_column(String(40))
    total_ht: Mapped[Decimal | None] = mapped_column(Money)
    total_tva: Mapped[Decimal | None] = mapped_column(Money)
    total_ttc: Mapped[Decimal | None] = mapped_column(Money)
    # Ventilation de la TVA : [{"rate": "5.5", "base": "100.00", "amount": "5.50"}].
    vat_breakdown: Mapped[list[dict[str, str]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # Fiabilité de chaque champ : confirmed, estimated, missing ou inconsistent.
    field_status: Mapped[dict[str, str]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    issues: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    paid_on: Mapped[date | None] = mapped_column(Date)
    validated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="invoice")
    party: Mapped[Party | None] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    # Désignation normalisée : permet de suivre le prix d'un même article dans le temps.
    product_key: Mapped[str | None] = mapped_column(String(200), index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total_ht: Mapped[Decimal | None] = mapped_column(Money)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class DataImport(Base):
    """Import d'un fichier tabulaire : relevé bancaire ou journal de caisse."""

    __tablename__ = "data_imports"
    __table_args__ = (CheckConstraint("kind IN ('bank', 'sales')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    rows_total: Mapped[int] = mapped_column(Integer)
    rows_added: Mapped[int] = mapped_column(Integer)
    rows_skipped: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    warnings: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (UniqueConstraint("company_id", "fingerprint", name="uq_bank_transactions_company_fingerprint"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_imports.id", ondelete="CASCADE"), index=True)
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Money)
    balance: Mapped[Decimal | None] = mapped_column(Money)
    category: Mapped[str] = mapped_column(String(40))
    # Comment la catégorie a été obtenue : rule, party, invoice ou user.
    category_source: Mapped[str] = mapped_column(String(10))
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parties.id", ondelete="SET NULL"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    # Empreinte stable : réimporter un relevé qui chevauche le précédent ne crée pas de doublon.
    fingerprint: Mapped[str] = mapped_column(String(64))


class SalesDay(Base):
    """Journée de caisse (ticket Z) : chiffre d'affaires et fréquentation."""

    __tablename__ = "sales_days"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_imports.id", ondelete="CASCADE"))
    covers: Mapped[int | None] = mapped_column(Integer)
    food_ht: Mapped[Decimal | None] = mapped_column(Money)
    drinks_ht: Mapped[Decimal | None] = mapped_column(Money)
    total_ht: Mapped[Decimal] = mapped_column(Money)
    total_tva: Mapped[Decimal | None] = mapped_column(Money)
    total_ttc: Mapped[Decimal | None] = mapped_column(Money)
    card: Mapped[Decimal | None] = mapped_column(Money)
    cash: Mapped[Decimal | None] = mapped_column(Money)
    meal_vouchers: Mapped[Decimal | None] = mapped_column(Money)


class AnomalyReview(Base):
    """Décision du dirigeant sur une alerte détectée (traitée, ignorée)."""

    __tablename__ = "anomaly_reviews"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(500))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Conseiller IA (Phase 3) --------------------------------------------------------------


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    """Un échange du conseiller. Les réponses conservent les faits calculés qui les fondent."""

    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="role"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    # Agents sollicités, faits utilisés (avec leurs sources), actions suggérées.
    agents: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    suggestions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # Rédaction : modèle utilisé (ou « moteur » sans IA), contrôle des chiffres, durée.
    generation: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


# --- Exécution d'actions (Phase 4) -----------------------------------------------------------


class ActionPolicy(Base):
    """Ce que le dirigeant autorise pour chaque type d'action."""

    __tablename__ = "action_policies"
    __table_args__ = (CheckConstraint("mode IN ('forbidden', 'approval', 'automatic')", name="mode"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    action_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Action(Base):
    """Opération proposée, autorisée puis exécutée : le journal d'activité des agents."""

    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'executing', 'done', 'failed', 'rejected', 'cancelled', 'undone')",
            name="status",
        ),
        CheckConstraint("risk_level IN (1, 2, 3)", name="risk_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(60))
    risk_level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), index=True)
    # Qui a proposé : un agent (« agent:executif ») ou une personne (« user »).
    proposed_by: Mapped[str] = mapped_column(String(40))
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Donnée déclenchante : alerte, document, message du conseiller.
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Autorisation obtenue : mode de la règle, personne, date, réauthentification.
    authorization: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    reversible: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(Base):
    """Tâche interne créée par une personne ou un agent (action de niveau 1)."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str | None] = mapped_column(Text)
    due_on: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(server_default=text("false"))
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboundEmail(Base):
    """Courriel émis par le boîtier : envoyé par SMTP, ou conservé dans la boîte d'envoi locale."""

    __tablename__ = "outbound_emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id", ondelete="SET NULL"))
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(String(20))  # smtp ou outbox
    message_id: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Connecteurs (Phase 5) -----------------------------------------------------------------


class Connection(Base):
    """Un logiciel ou une source connectée à une entreprise."""

    __tablename__ = "connections"
    __table_args__ = (CheckConstraint("status IN ('active', 'error', 'expired', 'paused')", name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    connector: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"))
    # Réglages non secrets (dossier, serveur, compte bancaire…).
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Identifiants chiffrés (AES-GCM) : jamais lisibles en base ni renvoyés par l'API.
    secret: Mapped[bytes | None] = mapped_column(LargeBinary)
    permissions: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    interval_minutes: Mapped[int] = mapped_column(Integer, server_default=text("60"))
    cursor: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(20))  # schedule ou manual
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # running, success, partial, failed
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)


class ConnectorItem(Base):
    """Élément déjà récupéré par une connexion : il n'est jamais importé deux fois."""

    __tablename__ = "connector_items"
    __table_args__ = (UniqueConstraint("connection_id", "external_id", name="uq_connector_items_connection_external"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    outcome: Mapped[str] = mapped_column(String(30))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
