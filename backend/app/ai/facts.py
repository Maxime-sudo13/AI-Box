"""Faits vérifiables transmis au conseiller.

Un fait est un chiffre calculé par le moteur, avec son libellé, sa source et sa fiabilité.
Les réponses du conseiller ne peuvent citer que ces faits : chaque chiffre affiché renvoie à
un fait numéroté [F1], [F2]… que le dirigeant peut ouvrir.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from app.finance.data import money

Quality = str  # confirmed, estimated, hypothesis


def num_fr(v: float | Decimal, decimals: int = 0) -> str:
    text = f"{abs(float(v)):,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{'−' if float(v) < 0 else ''}{text}"


def fmt(value: Any, unit: str) -> str:
    if value is None:
        return "non disponible"
    if unit == "eur":
        return money(value, 2 if abs(float(value)) < 100 else 0)
    if unit == "pct":
        return f"{num_fr(value, 1)} %"
    if unit == "pts":
        return f"{'+' if float(value) > 0 else ''}{num_fr(value, 1)} pt"
    if unit == "count":
        return num_fr(value)
    if unit == "days":
        return f"{num_fr(value)} jours"
    return str(value)


@dataclass
class Fact:
    id: str
    label: str
    value: Any
    unit: str
    display: str
    quality: Quality
    source: str
    link: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if isinstance(self.value, Decimal):
            out["value"] = float(self.value)
        return out


@dataclass
class Composer:
    """Rassemble les faits d'une réponse et les lignes rédigées par le moteur."""

    facts: list[Fact] = field(default_factory=list)
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    _by_key: dict[str, Fact] = field(default_factory=dict)

    def fact(
        self,
        key: str,
        label: str,
        value: Any,
        unit: str = "eur",
        *,
        quality: Quality = "confirmed",
        source: str = "moteur de calcul",
        link: str | None = None,
    ) -> str:
        """Enregistre un fait (une seule fois par clé) et renvoie « valeur [Fn] »."""
        if key not in self._by_key:
            f = Fact(f"F{len(self.facts) + 1}", label, value, unit, fmt(value, unit), quality, source, link)
            self.facts.append(f)
            self._by_key[key] = f
        f = self._by_key[key]
        return f"{f.display} [{f.id}]"

    def section(self, title: str, lines: list[str]) -> None:
        lines = [line for line in lines if line]
        if lines:
            self.sections.append((title, lines))

    def text(self) -> str:
        parts = []
        for title, lines in self.sections:
            parts.append(f"**{title}**")
            parts.extend(f"- {line}" for line in lines)
            parts.append("")
        return "\n".join(parts).strip()

    def facts_for_prompt(self) -> str:
        return "\n".join(
            f"[{f.id}] {f.label} : {f.display} (source : {f.source}"
            + (", estimation" if f.quality == "estimated" else ", hypothèse" if f.quality == "hypothesis" else "")
            + ")"
            for f in self.facts
        )
