#!/bin/bash
# Poste de l'éditeur : construit et signe un paquet de mise à jour.
#   ./construire-paquet.sh VERSION /chemin/cle-editeur.pem
# La clé privée ne quitte jamais ce poste ; seul le paquet signé est distribué.
set -euo pipefail
VERSION="${1:?Version manquante, par exemple 0.6.0}"
KEY="$(realpath "${2:?Clé privée de l éditeur manquante}")"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/dist"
WORK="$(mktemp -d)"
trap 'rm -rf -- "${WORK:?}"' EXIT
mkdir -p "$OUT"

grep -q "__version__ = \"$VERSION\"" "$ROOT/backend/app/__init__.py" || {
  echo "La version du code ($ROOT/backend/app/__init__.py) ne correspond pas à $VERSION." >&2; exit 1; }

docker build -t "business-ai-box-api:$VERSION" "$ROOT/backend"
docker build -t "business-ai-box-web:$VERSION" -f "$ROOT/deploy/Dockerfile.web" "$ROOT"
docker save -o "$WORK/business-ai-box-images.tar" "business-ai-box-api:$VERSION" "business-ai-box-web:$VERSION"
cp "$ROOT/deploy/docker-compose.yml" "$ROOT/deploy/Caddyfile" "$WORK/"
echo "BAB_VERSION=$VERSION" > "$WORK/version.env"

cd "$ROOT/backend"
uv run python -m app.ops signer "$VERSION" "$KEY" "$OUT/business-ai-box-$VERSION.babmaj" \
  "$WORK/business-ai-box-images.tar" "$WORK/docker-compose.yml" "$WORK/Caddyfile" "$WORK/version.env"
echo "Paquet prêt : $OUT/business-ai-box-$VERSION.babmaj"
