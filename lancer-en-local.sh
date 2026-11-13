#!/bin/sh
# Business AI Box — test sur votre ordinateur (Mac ou Linux). Prérequis : Docker Desktop.
set -eu
cd "$(dirname "$0")"

# Récupère la dernière version du code si le dossier vient de « git clone » (désactiver : BAB_NO_PULL=1).
if [ -d .git ] && command -v git >/dev/null 2>&1 && [ "${BAB_NO_PULL:-}" != "1" ]; then
  echo "0/3  Récupération de la dernière version (git pull)…"
  git pull --ff-only || echo "  (mise à jour impossible : on continue avec la version présente sur ce poste)"
fi
cd deploy
COMPOSE="docker compose -f docker-compose.local.yml"

# Dossiers partagés avec le conteneur (utilisateur dédié, sans droits root).
mkdir -p depot sauvegardes && chmod 777 depot sauvegardes

echo "1/3  Construction et démarrage (la première fois : 5 à 10 minutes)…"
if [ "${BAB_NO_BUILD:-}" = "1" ]; then $COMPOSE up -d --no-build; else $COMPOSE up -d --build; fi

echo "2/3  Attente du serveur…"
i=0
until $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -gt 90 ] && { echo "Le serveur ne démarre pas : $COMPOSE logs api"; exit 1; }
  sleep 2
done

echo "3/3  Chargement du restaurant de démonstration (la première fois : environ 1 minute)…"
$COMPOSE exec -T api python -m app.demo seed --admin-email gerant@bistrot.local --admin-password demo-bistrot-2026

VERSION=$($COMPOSE exec -T api python -c "import app; print(app.__version__)")
echo
echo "Prêt : http://localhost:8080   (version $VERSION, affichée aussi en bas du menu de gauche)"
echo "  Adresse e-mail : gerant@bistrot.local"
echo "  Mot de passe   : demo-bistrot-2026"
echo "Arrêter : cd deploy && $COMPOSE down      (vos données sont conservées)"
command -v open >/dev/null 2>&1 && open http://localhost:8080 || command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:8080 || true
