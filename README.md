# Business AI Box

Le cerveau numérique privé de l'entreprise : un boîtier installé dans les locaux d'une TPE/PME,
qui centralise ses données, les analyse localement avec une IA embarquée et agit dans ses
logiciels dans les limites fixées par le dirigeant.

- **Cahier des charges** : [docs/cahier-des-charges.md](docs/cahier-des-charges.md)
- **Feuille de route et suivi** : [docs/feuille-de-route.md](docs/feuille-de-route.md)

## État actuel — v0.2.0 (Phase 2, intelligence financière)

![Tableau de bord du restaurant de démonstration](docs/captures/1-tableau-de-bord.png)

| Fonction | État |
|---|---|
| Installation, comptes, rôles, entreprises, modules, journal d'activité | ✅ Phase 1 |
| Import de factures par lots (PDF, scans, photos) avec lecture locale et OCR | ✅ |
| Contrôle croisé des montants, fiabilité champ par champ, écran de vérification | ✅ |
| Doublons (même fichier, même facture) et justificatifs manquants | ✅ |
| Import du relevé bancaire et du journal de caisse (CSV), rapprochement automatique | ✅ |
| Tableau de bord : CA, EBE, coût matière, masse salariale, ticket moyen | ✅ |
| Chaque indicateur explique sa formule et ses sources | ✅ |
| Prévision de trésorerie à 90 jours, composante par composante | ✅ |
| Alertes justifiées et chiffrées (8 détecteurs) | ✅ |
| Restaurant de démonstration complet | ✅ — voir [docs/demo.md](docs/demo.md) |
| Conseiller IA local, actions contrôlées, connecteurs | Phases 3 à 5 |

## Organisation

```
backend/    API Python (FastAPI, SQLAlchemy, Alembic) — PostgreSQL
frontend/   Interface React + TypeScript (Vite)
deploy/     Déploiement sur le boîtier : Docker Compose + Caddy (HTTPS local)
docs/       Cahier des charges et feuille de route
```

## Développement

Prérequis : Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, PostgreSQL 16, Tesseract (OCR).

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

Au premier accès, l'interface ouvre l'assistant d'installation. Pour charger le restaurant
de démonstration : `uv run python -m app.demo seed` (voir [docs/demo.md](docs/demo.md)).

La lecture des scans et des photos utilise Tesseract, installé sur le poste de développement
(`apt install tesseract-ocr tesseract-ocr-fra`) et dans l'image Docker du boîtier.

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
- **Indépendance vis-à-vis de l'IA** : tous les calculs, la lecture des factures et la
  détection des anomalies sont déterministes et n'utilisent aucun modèle d'IA. L'IA de la
  Phase 3 interprétera ces résultats, sans jamais les produire.
- **Rien n'est inventé** : un montant illisible reste « manquant », un montant déduit est
  marqué « estimé », et chaque impact chiffré affiche sa formule.
- **Moindre privilège** : chaque utilisateur ne voit que les entreprises auxquelles il est
  rattaché ; une entreprise étrangère est indiscernable d'une entreprise inexistante.
- **Traçabilité** : chaque opération sensible, réussie ou refusée, est journalisée sans
  jamais enregistrer de mot de passe.
