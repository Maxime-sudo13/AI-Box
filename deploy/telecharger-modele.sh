#!/bin/sh
# Télécharge le modèle d'IA dans le volume du boîtier, une seule fois.
# Le service « ollama » du boîtier n'a pas accès à Internet : ce conteneur temporaire,
# lui, en a besoin le temps du téléchargement, puis il est supprimé.
set -eu
MODEL="${1:-qwen2.5:7b}"
IMAGE="${BAB_OLLAMA_IMAGE:-ollama/ollama:0.6.8}"
docker run --rm -v business-ai-box_ollama-models:/root/.ollama --entrypoint sh "$IMAGE" \
  -c "ollama serve >/dev/null 2>&1 & sleep 3 && ollama pull $MODEL"
echo "Modèle $MODEL installé. Redémarrez : docker compose restart ollama api"
