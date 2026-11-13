# Ubuntu 24.04 LTS : même base que le système du boîtier, maintenue jusqu'en 2029.
FROM ubuntu:24.04

# Python 3.12, reconnaissance de caractères en français (scans, photos) et outils PostgreSQL
# (pg_dump, pg_restore) pour les sauvegardes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 python3-venv tesseract-ocr tesseract-ocr-fra postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# uv installe les dépendances exactes du fichier uv.lock, avec le Python du système.
RUN python3 -m venv /opt/uv && /opt/uv/bin/pip install --no-cache-dir uv==0.11.32 && ln -s /opt/uv/bin/uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/bin/python3 UV_PYTHON_DOWNLOADS=never PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

RUN useradd --system --uid 10001 bab && mkdir -p /data /depot /sauvegardes && chown bab /data /sauvegardes
USER bab
ENV BAB_DATA_DIR=/data

EXPOSE 8000
# Les migrations sont appliquées à chaque démarrage : une mise à jour du boîtier
# met donc la base à niveau sans intervention.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
