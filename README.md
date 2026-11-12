# Business AI Box

Le cerveau numérique privé de l'entreprise : un boîtier installé dans les locaux d'une TPE/PME,
qui centralise ses données, les analyse localement avec une IA embarquée et agit dans ses
logiciels dans les limites fixées par le dirigeant.

- **Cahier des charges** : [docs/cahier-des-charges.md](docs/cahier-des-charges.md)
- **Feuille de route et suivi** : [docs/feuille-de-route.md](docs/feuille-de-route.md)

## État actuel — v0.1.0 (Phase 1, Fondations)

| Fonction | État |
|---|---|
| Assistant d'installation (administrateur, entreprise, modules) | ✅ |
| Authentification locale (Argon2, sessions révocables, verrouillage après 5 échecs) | ✅ |
| Gestion des entreprises (plusieurs par boîtier) et choix des modules | ✅ |
| Utilisateurs et rôles : Dirigeant, Gestionnaire, Lecture seule, Administrateur du boîtier | ✅ |
| Journal d'activité, y compris les tentatives refusées | ✅ |
| Interface web responsive (ordinateur et smartphone), aucune ressource externe | ✅ |
| Import de factures, tableau de bord financier, IA, actions | Phases suivantes |

## Organisation

```
backend/    API Python (FastAPI, SQLAlchemy, Alembic) — PostgreSQL
frontend/   Interface React + TypeScript (Vite)
deploy/     Déploiement sur le boîtier : Docker Compose + Caddy (HTTPS local)
docs/       Cahier des charges et feuille de route
```

## Développement

Prérequis : Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, PostgreSQL 16.

```bash
# Base de données
sudo -u postgres psql -c "CREATE ROLE bab LOGIN PASSWORD 'bab' CREATEDB"
sudo -u postgres createdb -O bab bab
sudo -u postgres createdb -O bab bab_test

# API — http://127.0.0.1:8000
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Interface — http://localhost:5173 (redirige /api vers l'API)
cd frontend
npm install
npm run dev
```

Au premier accès, l'interface ouvre l'assistant d'installation.

### Contrôles

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run build
```

Les tests reconstruisent le schéma de `bab_test` par les migrations et vérifient que celles-ci
correspondent aux modèles.

## Déploiement sur un boîtier

```bash
cd deploy
cp .env.example .env    # renseigner BAB_DB_PASSWORD
docker compose up -d --build
```

Le boîtier est alors joignable en HTTPS sur `https://businessaibox.local` (certificat émis par
l'autorité interne de Caddy). La base et l'API sont sur un réseau Docker sans accès sortant.

## Principes appliqués dès maintenant

- **Zéro communication externe** : l'interface n'appelle que le boîtier (polices système,
  pas de CDN, documentation d'API désactivée hors développement), pas de télémétrie.
- **Indépendance vis-à-vis de l'IA** : les données, droits et journaux ne dépendent d'aucun
  modèle ; l'IA sera un service remplaçable branché par-dessus.
- **Moindre privilège** : chaque utilisateur ne voit que les entreprises auxquelles il est
  rattaché ; une entreprise étrangère est indiscernable d'une entreprise inexistante.
- **Traçabilité** : chaque opération sensible, réussie ou refusée, est journalisée sans
  jamais enregistrer de mot de passe.
