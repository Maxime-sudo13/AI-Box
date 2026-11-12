"""Accès au modèle de langage local.

Le reste du logiciel ne dépend que de l'interface `LLMClient` : remplacer Qwen par un autre
modèle, ou Ollama par un autre moteur, ne change rien aux calculs, aux données ni aux
automatisations. Si le modèle est absent ou désactivé, le conseiller continue de répondre
avec le moteur de calcul seul.
"""

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings


class LLMUnavailable(Exception):
    pass


@dataclass
class LLMReply:
    text: str
    model: str
    duration_ms: int


class LLMClient(Protocol):
    name: str

    def available(self) -> bool: ...

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> LLMReply: ...


class OllamaClient:
    """Client de l'API HTTP d'Ollama, exécuté sur le boîtier (aucun appel extérieur)."""

    def __init__(self, url: str, model: str, timeout: float):
        self.url = url.rstrip("/")
        self.model = model
        self.name = model
        self.timeout = timeout
        self._checked_at = 0.0
        self._available = False

    def available(self) -> bool:
        # Vérification mise en cache 30 s : l'interface interroge souvent l'état du modèle.
        if time.monotonic() - self._checked_at < 30:
            return self._available
        self._checked_at = time.monotonic()
        try:
            tags = httpx.get(f"{self.url}/api/tags", timeout=3).json()
            names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
            self._available = self.model in names or f"{self.model}:latest" in names
        except (httpx.HTTPError, ValueError):
            self._available = False
        return self._available

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> LLMReply:
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "options": {"temperature": temperature, "num_ctx": 8192},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = response.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            self._checked_at = 0.0
            raise LLMUnavailable(str(exc)) from exc
        return LLMReply(text, self.model, int((time.monotonic() - started) * 1000))


_client: LLMClient | None = None


def get_llm() -> LLMClient | None:
    """Modèle configuré, ou None si l'IA est désactivée sur ce boîtier."""
    global _client
    settings = get_settings()
    if not settings.ai_enabled:
        return None
    if _client is None:
        _client = OllamaClient(settings.ollama_url, settings.ai_model, settings.ai_timeout_seconds)
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Remplace le modèle (tests, ou changement de modèle à chaud)."""
    global _client
    _client = client
