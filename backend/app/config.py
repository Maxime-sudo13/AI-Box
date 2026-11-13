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

    # IA locale (Phase 3). Le logiciel fonctionne sans : les réponses sont alors rédigées par
    # le moteur à partir des mêmes faits calculés.
    ai_enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen2.5:7b"
    ai_timeout_seconds: int = 120

    # Envoi des courriels (Phase 4). Sans serveur SMTP, les courriels autorisés sont
    # conservés dans la boîte d'envoi locale, consultables et téléchargeables.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    mail_from: str | None = None

    # Mode « zéro communication externe » : aucun connecteur en ligne, aucun courriel envoyé
    # par SMTP. Le boîtier ne fonctionne qu'avec les données déposées localement.
    offline_mode: bool = False
    # Clé de chiffrement des identifiants des connecteurs (32 octets en base64). Vide : une
    # clé est générée dans le dossier de données, lisible par le seul service.
    secret_key: str | None = None
    # Racine autorisée pour les dossiers surveillés : un connecteur ne lit rien en dehors.
    import_root: str | None = None
    # Sauvegardes : dossier sur un support distinct (disque USB, NAS). Vide : sous-dossier du
    # dossier de données, signalé comme insuffisant dans la page Système.
    backup_dir: str | None = None
    backup_keep: int = 14
    backup_hour: int = 2  # heure de la sauvegarde quotidienne (UTC)

    # Planificateur des synchronisations (désactivé dans les tests).
    scheduler_enabled: bool = True

    # Validité d'une réauthentification pour une action de niveau 3.
    reauth_minutes: int = 5

    # Date du jour imposée (tests, démonstrations figées). Vide en fonctionnement normal.
    today: date | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


def today() -> date:
    return get_settings().today or date.today()
