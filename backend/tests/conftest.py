import os

# La configuration doit être en place avant l'import de l'application.
TEST_DATABASE_URL = os.environ.get("BAB_TEST_DATABASE_URL", "postgresql+psycopg://bab:bab@localhost:5432/bab_test")
os.environ["BAB_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["BAB_COOKIE_SECURE"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

PASSWORD = "mot-de-passe-solide"

SETUP = {
    "admin": {"email": "Dirigeante@Exemple.fr", "full_name": "Claire Martin", "password": PASSWORD},
    "company": {"name": "Atelier Martin", "legal_form": "SARL", "siren": "123456789"},
    "modules": ["finance", "documents"],
}


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Reconstruit le schéma par les migrations : elles sont testées en même temps."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


def truncate_all() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def clean_tables(schema, request):
    yield
    # Les modules marqués « shared_data » partagent un jeu de données coûteux à construire :
    # il est nettoyé à la fin du module (voir la fixture correspondante).
    if not request.node.get_closest_marker("shared_data"):
        truncate_all()


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("bab-data")
    os.environ["BAB_DATA_DIR"] = str(path)
    from app.config import get_settings

    get_settings.cache_clear()
    return path


@pytest.fixture(scope="session")
def demo_files(tmp_path_factory):
    """Fichiers du restaurant de démonstration, générés une fois pour toute la session."""
    from app.demo.restaurant import generate

    out = tmp_path_factory.mktemp("demo") / "restaurant"
    generate(out)
    return out


@pytest.fixture
def anon():
    return TestClient(app)


@pytest.fixture
def admin():
    """Client connecté en tant qu'administrateur, boîtier configuré."""
    client = TestClient(app)
    response = client.post("/api/setup", json=SETUP)
    assert response.status_code == 201, response.text
    client.user = response.json()
    client.company_id = client.user["memberships"][0]["company_id"]
    return client


@pytest.fixture
def make_user(admin):
    """Crée un utilisateur et retourne un client connecté avec ce compte."""

    def _make(email: str, role: str | None = "viewer", **extra) -> TestClient:
        memberships = [{"company_id": admin.company_id, "role": role}] if role else []
        body = {
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
            "memberships": memberships,
            **extra,
        }
        created = admin.post("/api/users", json=body)
        assert created.status_code == 201, created.text
        client = TestClient(app)
        logged = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert logged.status_code == 200, logged.text
        client.user = created.json()
        return client

    return _make
