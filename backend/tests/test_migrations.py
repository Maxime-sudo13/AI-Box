from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import engine
from app.models import Base


def test_migrations_match_models():
    """Un modèle modifié sans migration correspondante fait échouer ce test."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
