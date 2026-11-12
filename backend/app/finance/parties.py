import difflib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extraction.text import name_key
from app.models import Party


def find_party(db: Session, company_id: uuid.UUID, kind: str, name: str | None, siren: str | None) -> Party | None:
    """Retrouve un tiers par SIREN, puis par nom normalisé, puis par nom approchant."""
    if siren:
        party = db.scalar(select(Party).where(Party.company_id == company_id, Party.kind == kind, Party.siren == siren))
        if party:
            return party
    if not name:
        return None
    key = name_key(name)
    candidates = db.scalars(select(Party).where(Party.company_id == company_id, Party.kind == kind)).all()
    for party in candidates:
        if party.name_key == key:
            return party
    # Tolère une faute d'OCR ou une variante d'écriture (« Boucherie Marchant »).
    best, best_ratio = None, 0.0
    for party in candidates:
        ratio = difflib.SequenceMatcher(None, party.name_key, key).ratio()
        if ratio > best_ratio:
            best, best_ratio = party, ratio
    return best if best_ratio >= 0.9 else None


def find_or_create_party(
    db: Session,
    company_id: uuid.UUID,
    kind: str,
    name: str | None,
    siren: str | None,
    category: str | None = None,
) -> Party | None:
    party = find_party(db, company_id, kind, name, siren)
    if party is None and name:
        party = Party(
            company_id=company_id,
            kind=kind,
            name=name[:200],
            name_key=name_key(name)[:200],
            siren=siren,
            category=category,
        )
        db.add(party)
        db.flush()
    elif party is not None:
        if siren and not party.siren:
            party.siren = siren
        if category and not party.category:
            party.category = category
    return party
