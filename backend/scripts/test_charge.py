"""Test de charge : des utilisateurs simultanés naviguent dans l'application.

    uv run python scripts/test_charge.py --url http://localhost:8080 --utilisateurs 10 --duree 60

Chaque utilisateur virtuel enchaîne les écrans d'un dirigeant (tableau de bord, alertes,
trésorerie, documents, conseiller) avec une courte pause entre deux clics. Le script affiche,
par écran, le nombre d'appels, les temps de réponse médian et 95e centile, et les erreurs.
Sert à dimensionner le matériel (cahier des charges, section 11).
"""

import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict

import httpx

QUESTIONS = [
    "Fais-moi un bilan complet de mon entreprise.",
    "Où est-ce que je perds le plus d'argent ?",
    "Quelle est ma trésorerie ?",
    "Quels sont mes cinq problèmes prioritaires ?",
]


async def user(base: str, email: str, password: str, deadline: float, stats: dict, think: float) -> None:
    async with httpx.AsyncClient(base_url=f"{base}/api", timeout=120, trust_env=False) as c:
        r = await c.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        company = (await c.get("/companies")).json()[0]["id"]
        screens = [
            ("tableau de bord", "GET", f"/companies/{company}/finance/overview", None),
            ("alertes", "GET", f"/companies/{company}/finance/alerts", None),
            ("trésorerie", "GET", f"/companies/{company}/finance/treasury", None),
            ("documents", "GET", f"/companies/{company}/documents?limit=50", None),
            ("banque", "GET", f"/companies/{company}/bank-transactions?limit=50", None),
        ]
        while time.monotonic() < deadline:
            if random.random() < 0.15:
                name, method, path, body = (
                    "conseiller",
                    "POST",
                    f"/companies/{company}/advisor/ask",
                    {"question": random.choice(QUESTIONS)},
                )
            else:
                name, method, path, body = random.choice(screens)
            started = time.monotonic()
            try:
                response = await c.request(method, path, json=body)
                ok = response.status_code < 400
            except httpx.HTTPError:
                ok = False
            stats[name].append((time.monotonic() - started) * 1000 if ok else None)
            await asyncio.sleep(random.uniform(0.5, 1.5) * think)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8080")
    p.add_argument("--email", default="gerant@bistrot.local")
    p.add_argument("--mot-de-passe", default="demo-bistrot-2026")
    p.add_argument("--utilisateurs", type=int, default=10)
    p.add_argument("--duree", type=int, default=60)
    p.add_argument("--pause", type=float, default=2.0, help="pause moyenne entre deux clics (secondes)")
    a = p.parse_args()
    stats: dict[str, list] = defaultdict(list)
    deadline = time.monotonic() + a.duree
    started = time.monotonic()
    await asyncio.gather(
        *(user(a.url, a.email, a.mot_de_passe, deadline, stats, a.pause) for _ in range(a.utilisateurs))
    )
    elapsed = time.monotonic() - started
    total = sum(len(v) for v in stats.values())
    print(
        f"\n{a.utilisateurs} utilisateurs simultanés pendant {elapsed:.0f} s : {total} requêtes ({total / elapsed:.1f}/s)\n"
    )
    print(f"{'Écran':<18}{'appels':>8}{'médiane':>10}{'95e cent.':>11}{'max':>9}{'erreurs':>9}")
    for name, values in sorted(stats.items()):
        ok = sorted(v for v in values if v is not None)
        errors = len(values) - len(ok)
        if not ok:
            print(f"{name:<18}{len(values):>8}{'—':>10}{'—':>11}{'—':>9}{errors:>9}")
            continue
        p95 = ok[min(len(ok) - 1, int(len(ok) * 0.95))]
        print(f"{name:<18}{len(values):>8}{statistics.median(ok):>8.0f}ms{p95:>9.0f}ms{ok[-1]:>7.0f}ms{errors:>9}")


if __name__ == "__main__":
    asyncio.run(main())
