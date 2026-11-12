import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.modules import MODULE_KEYS

Role = Literal["owner", "manager", "viewer"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def _normalize_email(value: str) -> str:
    # Validation volontairement souple : un boîtier hors ligne peut utiliser des
    # adresses internes (prenom@entreprise.local) qu'un validateur strict refuserait.
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Adresse e-mail invalide.")
    return value


def _check_modules(value: list[str]) -> list[str]:
    unknown = sorted(set(value) - MODULE_KEYS)
    if unknown:
        raise ValueError(f"Modules inconnus : {', '.join(unknown)}")
    return sorted(set(value))


Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(_normalize_email)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# La longueur minimale dépend de la configuration : elle est vérifiée dans l'API.
Password = Annotated[str, StringConstraints(max_length=200)]
ModuleKeys = Annotated[list[str], AfterValidator(_check_modules)]
Siren = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{9}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Entreprises ---------------------------------------------------------------------------


class CompanyIn(BaseModel):
    name: Name
    legal_form: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    siren: Siren | None = None
    sector: ShortText | None = None


class CompanyPatch(CompanyIn):
    name: Name | None = None


class CompanyOut(ORMModel):
    id: uuid.UUID
    name: str
    legal_form: str | None
    siren: str | None
    sector: str | None
    enabled_modules: list[str]
    created_at: datetime
    # Rôle de l'utilisateur courant ; None pour un administrateur non rattaché.
    role: Role | None = None


class ModulesIn(BaseModel):
    modules: ModuleKeys


class ModuleOut(ORMModel):
    key: str
    name: str
    description: str
    available: bool


# --- Utilisateurs --------------------------------------------------------------------------


class MembershipIn(BaseModel):
    company_id: uuid.UUID
    role: Role


class MembershipOut(BaseModel):
    company_id: uuid.UUID
    company_name: str
    role: Role


class UserCreate(BaseModel):
    email: Email
    full_name: Name
    password: Password
    is_admin: bool = False
    memberships: list[MembershipIn] = Field(default_factory=list)


class UserPatch(BaseModel):
    full_name: Name | None = None
    password: Password | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    memberships: list[MembershipIn] | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    memberships: list[MembershipOut]


# --- Installation et authentification ------------------------------------------------------


class SetupAdmin(BaseModel):
    email: Email
    full_name: Name
    password: Password


class SetupIn(BaseModel):
    admin: SetupAdmin
    company: CompanyIn
    modules: ModuleKeys = Field(default_factory=list)


class SetupStatus(BaseModel):
    initialized: bool


class LoginIn(BaseModel):
    email: Email
    password: Password


class PasswordChange(BaseModel):
    current_password: Password
    new_password: Password


# --- Journal d'activité --------------------------------------------------------------------


class AuditEventOut(ORMModel):
    id: int
    occurred_at: datetime
    actor_label: str | None
    company_id: uuid.UUID | None
    action: str
    outcome: str
    target: str | None
    details: dict[str, Any]
    ip: str | None


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    total: int
