#!/bin/bash
# Installe une mise à jour signée sur le boîtier, sans connexion à l'éditeur.
#   sudo ./mettre-a-jour.sh /chemin/business-ai-box-X.Y.Z.babmaj
# Étapes : vérification de la signature et des empreintes, sauvegarde des données, chargement
# des nouvelles images, redémarrage, contrôle de santé ; retour automatique à la version
# précédente si le boîtier ne redémarre pas correctement.
set -euo pipefail
cd "$(dirname "$0")"
PACKAGE="$(realpath "${1:?Chemin du paquet .babmaj manquant}")"
COMPOSE="docker compose"
WORK="$(mktemp -d)"
trap 'rm -rf -- "${WORK:?}"' EXIT
chmod 777 "$WORK"

current=$(grep -E '^BAB_VERSION=' .env | cut -d= -f2 || echo dev)
installed=$($COMPOSE exec -T api python -c "import app; print(app.__version__)" 2>/dev/null || echo 0.0.0)

echo "1/5  Vérification du paquet (signature de l'éditeur, empreintes, version)…"
$COMPOSE run --rm --no-deps -T -v "$PACKAGE:/maj/paquet.babmaj:ro" -v "$WORK:/maj/extrait" api \
  python -m app.ops verifier-maj /maj/paquet.babmaj --extraire /maj/extrait --version-installee "$installed"
new=$(grep -E '^BAB_VERSION=' "$WORK/version.env" | cut -d= -f2)
[ -n "$new" ] || { echo "Paquet sans version.env : refusé." >&2; exit 1; }

echo "2/5  Sauvegarde des données avant mise à jour…"
if ! $COMPOSE exec -T api python -m app.ops sauvegarder; then
  read -r -p "Sauvegarde impossible (clé de récupération créée ?). Continuer quand même ? Tapez OUI : " answer
  [ "$answer" = "OUI" ] || exit 1
fi

echo "3/5  Chargement des images $new…"
docker load -i "$WORK/business-ai-box-images.tar"
for f in docker-compose.yml Caddyfile; do
  if [ -f "$WORK/$f" ]; then cp "$f" "$f.avant-$new" && cp "$WORK/$f" "$f"; fi
done

echo "4/5  Redémarrage en version $new…"
sed -i "s/^BAB_VERSION=.*/BAB_VERSION=$new/" .env
$COMPOSE up -d --no-build

echo "5/5  Contrôle de santé…"
for _ in $(seq 1 60); do
  if $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" >/dev/null 2>&1; then
    echo "Mise à jour terminée : version $new."
    exit 0
  fi
  sleep 3
done

echo "Le boîtier ne répond pas en version $new : retour à la version $current." >&2
sed -i "s/^BAB_VERSION=.*/BAB_VERSION=$current/" .env
for f in docker-compose.yml Caddyfile; do
  if [ -f "$f.avant-$new" ]; then mv "$f.avant-$new" "$f"; fi
done
$COMPOSE up -d --no-build
exit 1
