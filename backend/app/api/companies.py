import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import Auth, get_admin, get_auth, get_company_for
from app.models import Company, Membership
from app.modules import CATALOG
from app.schemas import CompanyIn, CompanyOut, CompanyPatch, ModuleOut, ModulesIn

router = APIRouter(tags=["entreprises"])


def company_out(company: Company, role: str | None) -> CompanyOut:
    out = CompanyOut.model_validate(company)
    out.role = role
    return out


@router.get("/modules", response_model=list[ModuleOut])
def list_modules():
    # Public : l'assistant d'installation l'affiche avant qu'un compte n'existe,
    # et le catalogue ne contient aucune donnée du client.
    return CATALOG


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)):
    query = (
        select(Company, Membership.role)
        .outerjoin(
            Membership,
            (Membership.company_id == Company.id) & (Membership.user_id == auth.user.id),
        )
        .order_by(func.lower(Company.name))
    )
    if not auth.user.is_admin:
        query = query.where(Membership.user_id.is_not(None))
    return [company_out(company, role) for company, role in db.execute(query)]


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyIn,
    request: Request,
    auth: Auth = Depends(get_admin),
    db: Session = Depends(get_db),
):
    company = Company(**body.model_dump(), enabled_modules=[])
    db.add(company)
    db.flush()
    audit.record(db, request, "company.create", actor=auth.user, company_id=company.id, target=company.name)
    db.commit()
    return company_out(company, None)


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company, role = get_company_for(db, request, auth.user, company_id)
    return company_out(company, role)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    body: CompanyPatch,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company, role = get_company_for(db, request, auth.user, company_id, manage=True)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is None:
        changes.pop("name", None)
    for field, value in changes.items():
        setattr(company, field, value)
    audit.record(
        db,
        request,
        "company.update",
        actor=auth.user,
        company_id=company.id,
        target=company.name,
        details={"fields": sorted(changes)},
    )
    db.commit()
    return company_out(company, role)


@router.put("/companies/{company_id}/modules", response_model=CompanyOut)
def set_modules(
    company_id: uuid.UUID,
    body: ModulesIn,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company, role = get_company_for(db, request, auth.user, company_id, manage=True)
    before = set(company.enabled_modules)
    company.enabled_modules = body.modules
    after = set(body.modules)
    audit.record(
        db,
        request,
        "company.modules",
        actor=auth.user,
        company_id=company.id,
        target=company.name,
        details={"enabled": sorted(after - before), "disabled": sorted(before - after)},
    )
    db.commit()
    return company_out(company, role)
