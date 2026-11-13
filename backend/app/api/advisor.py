import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.ai.advisor import answer
from app.ai.agents import AGENTS
from app.ai.llm import get_llm
from app.config import get_settings, today
from app.db import get_db
from app.deps import Auth, company_access, get_auth
from app.finance import anomalies, engine, treasury
from app.finance.data import load
from app.models import Conversation, Message

router = APIRouter(tags=["conseiller"])

EXAMPLES = [
    "Fais-moi un bilan complet de mon entreprise.",
    "Où est-ce que je perds le plus d'argent ?",
    "Pourquoi mon bénéfice a-t-il changé ce mois-ci ?",
    "Combien puis-je réellement investir actuellement ?",
    "Comment pourrais-je augmenter mon bénéfice de 10 % ?",
    "Si je recrute une personne supplémentaire à 2 500 € par mois, quel sera l'impact ?",
    "Quels sont mes cinq problèmes prioritaires ?",
    "Qui sont mes meilleurs clients ?",
    "Prépare un plan d'optimisation pour les 90 prochains jours.",
]


def message_out(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "agents": m.agents,
        "facts": m.facts,
        "suggestions": m.suggestions,
        "generation": m.generation,
        "created_at": m.created_at,
    }


def conversation_out(c: Conversation, with_messages: bool = True) -> dict:
    out = {"id": str(c.id), "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at}
    if with_messages:
        out["messages"] = [message_out(m) for m in c.messages]
    return out


@router.get("/companies/{company_id}/advisor/status")
def advisor_status(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company_access(db, request, auth.user, company_id, module="conseiller")
    settings = get_settings()
    llm = get_llm()
    return {
        "ai_enabled": settings.ai_enabled,
        "model": settings.ai_model if settings.ai_enabled else None,
        "available": bool(llm and llm.available()),
        "examples": EXAMPLES,
        "agents": [
            {"key": a.key, "name": a.name, "mission": a.mission, "domains": sorted(a.domains)} for a in AGENTS.values()
        ],
    }


@router.get("/companies/{company_id}/advisor/conversations")
def list_conversations(
    company_id: uuid.UUID, request: Request, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
):
    company = company_access(db, request, auth.user, company_id, module="conseiller")
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.company_id == company.id, Conversation.user_id == auth.user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    return [conversation_out(c, with_messages=False) for c in rows]


def _get_conversation(
    db: Session, company_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conv = db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id, Conversation.company_id == company_id, Conversation.user_id == user_id
        )
        .options(selectinload(Conversation.messages))
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable.")
    return conv


@router.get("/companies/{company_id}/advisor/conversations/{conversation_id}")
def get_conversation(
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="conseiller")
    return conversation_out(_get_conversation(db, company.id, auth.user.id, conversation_id))


@router.delete(
    "/companies/{company_id}/advisor/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="conseiller")
    db.delete(_get_conversation(db, company.id, auth.user.id, conversation_id))
    audit.record(db, request, "advisor.delete", actor=auth.user, company_id=company.id, target=str(conversation_id))
    db.commit()


class Question(BaseModel):
    question: Annotated[str, Field(min_length=2, max_length=1000)]
    conversation_id: uuid.UUID | None = None


@router.post("/companies/{company_id}/advisor/ask")
def ask(
    company_id: uuid.UUID,
    body: Question,
    request: Request,
    auth: Auth = Depends(get_auth),
    db: Session = Depends(get_db),
):
    company = company_access(db, request, auth.user, company_id, module="conseiller")
    if "finance" not in company.enabled_modules:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Le conseiller s'appuie sur le module « Gestion financière » : activez-le."
        )
    if body.conversation_id:
        conv = _get_conversation(db, company.id, auth.user.id, body.conversation_id)
    else:
        conv = Conversation(company_id=company.id, user_id=auth.user.id, title=body.question.strip()[:200])
        db.add(conv)
        db.flush()
    previous_month = next((m.generation.get("month") for m in reversed(conv.messages) if m.role == "assistant"), None)

    ds = load(db, company, today())
    months = engine.build_months(ds)
    forecast = treasury.forecast(ds)
    alerts = anomalies.detect(db, ds, months, forecast)
    result = answer(body.question, ds, months, forecast, alerts, get_llm(), previous_month=previous_month)

    from app.actions.drafts import drafts_for_alert

    by_fp = {a["fingerprint"]: a for a in alerts}
    suggestions = []
    for fp in result.alert_refs:
        if fp in by_fp and by_fp[fp]["status"] == "open":
            for d in drafts_for_alert(db, company, by_fp[fp]):
                suggestions.append({"alert": fp, "action_type": d["action_type"], "title": d["title"]})
    db.add(Message(conversation=conv, role="user", content=body.question.strip()))
    reply = Message(
        conversation=conv,
        role="assistant",
        content=result.text,
        agents=result.agents,
        facts=result.facts,
        suggestions=suggestions[:6],
        generation={
            **result.generation,
            "intents": result.intents,
            "month": result.month,
            "engine_text": result.engine_text,
        },
    )
    db.add(reply)
    conv.updated_at = datetime.now(UTC)
    # Le journal retient la question posée et l'auteur de la rédaction, pas la réponse complète.
    audit.record(
        db,
        request,
        "advisor.ask",
        actor=auth.user,
        company_id=company.id,
        target=body.question[:300],
        details={
            "agents": result.agents,
            "writer": result.generation.get("writer"),
            "guard": result.generation.get("guard"),
        },
    )
    db.commit()
    return conversation_out(_get_conversation(db, company.id, auth.user.id, conv.id))
