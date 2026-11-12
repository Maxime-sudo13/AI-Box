"""Boîte mail : récupère les factures reçues en pièce jointe (Gmail, Outlook, OVH… via IMAP).

Lecture seule par défaut : le dossier est ouvert en consultation et les messages sont lus sans
être marqués comme lus. Le marquage n'a lieu que si le dirigeant l'autorise explicitement.
"""

import email
import imaplib
import re
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from typing import Any

from .base import (
    AuthError,
    Connector,
    ConnectorError,
    DocumentRecord,
    Permission,
    SettingField,
    SyncContext,
    SyncResult,
)

ATTACHMENT_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MAX_MESSAGES = 200


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, LookupError):
        return value


class ImapConnector(Connector):
    key = "imap"
    name = "Boîte mail (factures reçues)"
    category = "Communication"
    description = "Importe les factures reçues en pièce jointe dans un dossier de votre messagerie."
    fields = (
        SettingField("host", "Serveur IMAP", hint="Par exemple imap.gmail.com ou outlook.office365.com."),
        SettingField("port", "Port", kind="number", default=993),
        SettingField("username", "Identifiant", kind="email"),
        SettingField(
            "password",
            "Mot de passe d'application",
            kind="password",
            secret=True,
            hint="Utilisez un mot de passe d'application dédié, révocable à tout moment.",
        ),
        SettingField(
            "folder", "Dossier", default="INBOX", hint="Idéalement un dossier dédié, par exemple « Factures »."
        ),
    )
    permissions = (
        Permission("read_attachments", "Lire les pièces jointes du dossier", default=True),
        Permission("mark_seen", "Marquer comme lus les courriels importés", write=True),
    )
    data_notice = "Seules les pièces jointes PDF et images sont copiées sur le boîtier ; le texte des courriels n'est pas conservé."
    imap_class = imaplib.IMAP4_SSL  # remplaçable dans les tests

    def _connect(self, settings: dict[str, Any], secrets: dict[str, Any]):
        try:
            client = self.imap_class(settings["host"], int(settings.get("port") or 993), timeout=30)
        except (TimeoutError, OSError, imaplib.IMAP4.error) as exc:
            raise ConnectorError(f"Serveur de messagerie injoignable ({settings.get('host')}).") from exc
        try:
            client.login(settings["username"], secrets.get("password", ""))
        except imaplib.IMAP4.error as exc:
            raise AuthError("Identifiant ou mot de passe refusé par la messagerie.") from exc
        return client

    def _select(self, client, folder: str, readonly: bool) -> None:
        status, _ = client.select(f'"{folder}"', readonly=readonly)
        if status != "OK":
            raise ConnectorError(f"Dossier « {folder} » introuvable dans la messagerie.")

    def test(self, settings: dict[str, Any], secrets: dict[str, Any]) -> str:
        client = self._connect(settings, secrets)
        try:
            self._select(client, settings.get("folder") or "INBOX", readonly=True)
            _, data = client.uid("SEARCH", None, "ALL")
            count = len(data[0].split()) if data and data[0] else 0
        finally:
            client.logout()
        return f"Connexion réussie : {count} message(s) dans le dossier."

    def sync(self, ctx: SyncContext) -> SyncResult:
        if not ctx.allowed("read_attachments"):
            raise ConnectorError("La lecture des pièces jointes n'est pas autorisée pour cette connexion.")
        mark = ctx.allowed("mark_seen")
        client = self._connect(ctx.settings, ctx.secrets)
        folder = ctx.settings.get("folder") or "INBOX"
        result = SyncResult()
        try:
            self._select(client, folder, readonly=not mark)
            since = ctx.cursor.get("since") or (datetime.now(UTC) - timedelta(days=90)).strftime("%d-%b-%Y")
            _, data = client.uid("SEARCH", None, "SINCE", since)
            uids = (data[0].split() if data and data[0] else [])[-MAX_MESSAGES:]
            by_message: dict[str, list[str]] = {}
            for uid in uids:
                uid_s = uid.decode()
                # BODY.PEEK : lire sans marquer le message comme lu.
                _, msg_data = client.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
                if raw is None:
                    continue
                message = email.message_from_bytes(raw)
                subject = _decode(message.get("Subject"))[:80]
                for index, part in enumerate(message.walk()):
                    ctype = part.get_content_type()
                    filename = _decode(part.get_filename())
                    ext = ATTACHMENT_TYPES.get(ctype) or (
                        re.search(r"\.(pdf|jpe?g|png)$", filename.lower()) and filename[-4:]
                    )
                    if not ext or part.get_content_maintype() == "multipart":
                        continue
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    external_id = f"{folder}:{uid_s}:{index}"
                    by_message.setdefault(uid_s, []).append(external_id)
                    if ctx.seen(external_id):
                        continue
                    name = filename or f"{subject or 'piece-jointe'}{ext}"
                    result.documents.append(DocumentRecord(external_id, name[:200], payload))
            result.cursor = {"since": (datetime.now(UTC) - timedelta(days=2)).strftime("%d-%b-%Y")}
        except Exception:
            client.logout()
            raise

        def finalize(done: set[str]) -> None:
            try:
                if mark:
                    for uid_s, ids in by_message.items():
                        if all(i in done or ctx.seen(i) for i in ids):
                            client.uid("STORE", uid_s.encode(), "+FLAGS", "(\\Seen)")
            finally:
                client.logout()

        result.finalize = finalize
        return result
