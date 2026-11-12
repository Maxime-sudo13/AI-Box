from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration du boîtier, lue depuis les variables d'environnement BAB_*."""

    model_config = SettingsConfigDict(env_prefix="BAB_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bab:bab@localhost:5432/bab"
    # Dossier où sont conservés les documents originaux (à placer sur un disque chiffré).
    data_dir: str = "./data"
    max_upload_mb: int = 25
    # Langue utilisée pour la reconnaissance de caractères des documents scannés.
    ocr_lang: str = "fra"

    # Le cookie de session n'est émis que sur HTTPS, sauf en développement local.
    cookie_secure: bool = True
    session_ttl_hours: int = 12

    password_min_length: int = 12
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # La documentation interactive charge des ressources depuis un CDN : elle reste
    # désactivée hors développement pour respecter le mode « zéro communication externe ».
    debug: bool = False

    # Date du jour imposée (tests, démonstrations figées). Vide en fonctionnement normal.
    today: date | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


def today() -> date:
    return get_settings().today or date.today()
