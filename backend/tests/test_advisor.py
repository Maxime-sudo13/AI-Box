"""Conseiller : réponses fondées sur les faits, cloisonnement des agents, contrôle du modèle."""

import re

import pytest

from app.ai.advisor import verify_numbers
from app.ai.llm import LLMReply, LLMUnavailable, set_llm
from tests.conftest import build_bistrot, truncate_all

pytestmark = pytest.mark.shared_data


class FakeLLM:
    """Remplace Ollama : renvoie une rédaction choisie par le test."""

    name = "faux-modele"

    def __init__(self, reply=None, available=True, fail=False):
        self.reply, self._available, self.fail, self.prompts = reply, available, fail, []

    def available(self):
        return self._available

    def chat(self, system, user, *, temperature=0.2):
        self.prompts.append((system, user))
        if self.fail:
            raise LLMUnavailable("délai dépassé")
        return LLMReply(self.reply(user) if callable(self.reply) else self.reply, self.name, 12)


@pytest.fixture(scope="module")
def bistrot(data_dir, demo_files):
    client = build_bistrot(demo_files, ["documents", "finance", "conseiller"])
    yield client
    set_llm(None)
    truncate_all()


@pytest.fixture(autouse=True)
def no_llm():
    set_llm(FakeLLM(available=False))
    yield
    set_llm(None)


def ask(client, question, conversation_id=None):
    r = client.post(f"{client.base}/advisor/ask", json={"question": question, "conversation_id": conversation_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_status_lists_agents(bistrot):
    status = bistrot.get(f"{bistrot.base}/advisor/status").json()
    assert {a["key"] for a in status["agents"]} == {"financier", "commercial", "achats", "administratif", "strategique"}
    assert status["available"] is False and status["examples"]


@pytest.mark.parametrize(
    "question,intent,expected",
    [
        ("Fais-moi un bilan complet de mon entreprise.", "bilan", "Sur 12 mois"),
        ("Où est-ce que je perds le plus d'argent ?", "losses", "Coût matière en hausse"),
        ("Combien puis-je réellement investir actuellement ?", "invest", "seuil de vigilance"),
        ("Si je recrute une personne supplémentaire à 2 500 € par mois ?", "hiring", "2 500 €"),
        ("Comment pourrais-je augmenter mon bénéfice de 10 % ?", "increase_profit", "déjà inclus dans la dérive"),
        ("Prépare un plan d'optimisation pour les 90 prochains jours.", "plan", "Semaine 1"),
        ("Quels sont mes cinq problèmes prioritaires ?", "priorities", "prioritaire"),
    ],
)
def test_specification_questions(bistrot, question, intent, expected):
    conv = ask(bistrot, question)
    reply = conv["messages"][-1]
    assert intent in reply["generation"]["intents"]
    assert expected.replace(" ", " ") in reply["content"].replace(" ", " ")
    assert reply["generation"]["writer"] == "engine"
    # Chaque référence [Fn] du texte renvoie à un fait conservé avec sa source.
    ids = {f["id"] for f in reply["facts"]}
    assert set(re.findall(r"\[(F\d+)\]", reply["content"])) <= ids
    assert all(f["source"] for f in reply["facts"])


def test_premise_is_corrected(bistrot):
    reply = ask(bistrot, "Pourquoi mon bénéfice a-t-il diminué en septembre ?")["messages"][-1]
    assert reply["generation"]["month"].endswith("-09")
    assert "n’a pas baissé" in reply["content"]


def test_follow_up_keeps_the_month(bistrot):
    conv = ask(bistrot, "Comment s'est passé le mois de juin ?")
    follow = ask(bistrot, "Et les principales dépenses ?", conv["id"])
    assert follow["messages"][-1]["generation"]["month"].endswith("-06")
    assert len(follow["messages"]) == 4


def test_llm_rewrite_is_kept_when_numbers_match(bistrot):
    def rewrite(prompt):
        engine_text = prompt.split("à reformuler de façon plus naturelle et plus synthétique :\n", 1)[1]
        first_line = next(line for line in engine_text.splitlines() if "[F" in line)
        return "En résumé : " + first_line.lstrip("- ")

    fake = FakeLLM(rewrite)
    set_llm(fake)
    reply = ask(bistrot, "Quelle est ma trésorerie ?")["messages"][-1]
    assert reply["generation"]["writer"] == "llm" and reply["generation"]["guard"] == "passed"
    assert reply["content"].startswith("En résumé")
    system, user = fake.prompts[0]
    assert "N'invente aucun chiffre" in system
    # Le modèle ne reçoit que des faits calculés, jamais le texte des documents.
    assert "Faits calculés" in user and "%PDF" not in user


def test_llm_invented_number_is_rejected(bistrot):
    set_llm(FakeLLM("Votre trésorerie atteindra 987 654 € [F1] l'an prochain, croyez-moi."))
    reply = ask(bistrot, "Quelle est ma trésorerie ?")["messages"][-1]
    assert reply["generation"]["writer"] == "engine"
    assert reply["generation"]["guard"] == "rejected"
    assert "987654" in reply["generation"]["unverified"]
    assert "987" not in reply["content"]


def test_llm_failure_falls_back_to_engine(bistrot):
    set_llm(FakeLLM(fail=True))
    reply = ask(bistrot, "Quelle est ma trésorerie ?")["messages"][-1]
    assert reply["generation"]["writer"] == "engine" and "n'a pas répondu" in reply["generation"]["note"]


def test_agents_only_see_their_data(bistrot):
    from app.ai.agents import AGENTS, scoped
    from app.config import today
    from app.db import SessionLocal
    from app.finance.data import load
    from app.models import Company

    with SessionLocal() as db:
        ds = load(db, db.get(Company, bistrot.company_id), today())
    achats = scoped(ds, AGENTS["achats"])
    assert achats.txs == [] and achats.sales == []
    assert all(inv.direction == "purchase" for inv in achats.invoices)
    commercial = scoped(ds, AGENTS["commercial"])
    assert all(inv.direction == "sale" for inv in commercial.invoices)
    admin = scoped(ds, AGENTS["administratif"])
    assert admin.txs and not any(t.category in ("salaires", "charges_sociales") for t in admin.txs)


def test_suggestions_link_to_executable_actions(bistrot):
    reply = ask(bistrot, "Quelles factures clients sont impayées ?")["messages"][-1]
    assert any(s["action_type"] == "email.payment_reminder" for s in reply["suggestions"])


def test_conversations_are_private_and_audited(bistrot):
    conv = ask(bistrot, "Quelle est ma trésorerie ?")
    assert any(c["id"] == conv["id"] for c in bistrot.get(f"{bistrot.base}/advisor/conversations").json())
    assert bistrot.get("/api/audit").json()["items"][0]["action"] == "advisor.ask"
    assert bistrot.delete(f"{bistrot.base}/advisor/conversations/{conv['id']}").status_code == 204


def test_verify_numbers_tolerates_rounding_only():
    facts = [{"value": 52477.18, "unit": "eur"}, {"value": 17.6, "unit": "pct"}]
    assert verify_numbers("CA de 52 477 € et marge de 17,6 %", "", facts) == []
    assert verify_numbers("CA de 53 000 €", "", facts) == ["53000"]
