"""Qonto : opérations et solde du compte professionnel, par l'API officielle, en lecture seule.

Authentification par clé d'API (identifiant d'organisation + clé secrète), générée par le
dirigeant dans Qonto et révocable à tout moment. Aucune fonction de paiement n'est proposée :
un virement passe par l'action de niveau 3 (fichier SEPA à déposer).
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from .base import AuthError, BankRecord, Connector, ConnectorError, Permission, SettingField, SyncContext, SyncResult

API = "https://thirdparty.qonto.com/v2"


class QontoConnector(Connector):
    key = "qonto"
    name = "Qonto"
    category = "Banque"
    description = "Récupère les opérations et le solde de votre compte Qonto, chaque heure."
    hosts = ("thirdparty.qonto.com",)
    fields = (
        SettingField(
            "login",
            "Identifiant de l'organisation",
            hint="Dans Qonto : Paramètres › Intégrations et partenariats › Clé API.",
        ),
        SettingField("secret_key", "Clé secrète", kind="password", secret=True),
        SettingField(
            "iban", "IBAN du compte", required=False, hint="Facultatif : le compte principal est utilisé par défaut."
        ),
    )
    permissions = (
        Permission("read_transactions", "Lire les opérations bancaires", default=True),
        Permission("read_balance", "Lire le solde du compte", default=True),
    )
    data_notice = "Les opérations sont copiées sur le boîtier ; elles restent aussi hébergées par Qonto."
    transport: httpx.BaseTransport | None = None  # remplaçable dans les tests

    def _client(self, settings: dict[str, Any], secrets: dict[str, Any]) -> httpx.Client:
        return httpx.Client(
            base_url=API,
            transport=self.transport,
            timeout=30,
            headers={
                "Authorization": f"{settings.get('login', '')}:{secrets.get('secret_key', '')}",
                "Accept": "application/json",
            },
        )

    def _get(self, client: httpx.Client, path: str, params: dict | None = None) -> dict:
        try:
            response = client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ConnectorError("Qonto ne répond pas. Vérifiez l'accès Internet du boîtier.") from exc
        if response.status_code in (401, 403):
            raise AuthError("Clé d'API refusée par Qonto : elle a peut-être été révoquée.")
        if response.status_code == 429:
            raise ConnectorError("Trop de requêtes envoyées à Qonto : nouvel essai à la prochaine synchronisation.")
        if response.status_code >= 400:
            raise ConnectorError(f"Qonto a renvoyé une erreur ({response.status_code}).")
        return response.json()

    def _account(self, client: httpx.Client, iban: str | None) -> dict:
        accounts = self._get(client, "/organization").get("organization", {}).get("bank_accounts", [])
        if not accounts:
            raise ConnectorError("Aucun compte bancaire trouvé dans cette organisation Qonto.")
        if iban:
            wanted = iban.replace(" ", "").upper()
            match = next((a for a in accounts if (a.get("iban") or "").replace(" ", "").upper() == wanted), None)
            if match is None:
                raise ConnectorError("Cet IBAN ne correspond à aucun compte de l'organisation.")
            return match
        return next((a for a in accounts if a.get("main")), accounts[0])

    def test(self, settings: dict[str, Any], secrets: dict[str, Any]) -> str:
        with self._client(settings, secrets) as client:
            account = self._account(client, settings.get("iban"))
        return f"Connexion réussie : compte « {account.get('name', 'principal')} » ({account.get('iban', '')[-4:].rjust(8, '•')})."

    def sync(self, ctx: SyncContext) -> SyncResult:
        if not ctx.allowed("read_transactions"):
            raise ConnectorError("La lecture des opérations n'est pas autorisée pour cette connexion.")
        result = SyncResult()
        since = ctx.cursor.get("since") or (date.today() - timedelta(days=400)).isoformat()
        rows = []
        with self._client(ctx.settings, ctx.secrets) as client:
            account = self._account(client, ctx.settings.get("iban"))
            page = 1
            while page:
                data = self._get(
                    client,
                    "/transactions",
                    {
                        "iban": account["iban"],
                        "status[]": "completed",
                        "settled_at_from": f"{since}T00:00:00.000Z",
                        "sort_by": "settled_at:asc",
                        "per_page": 100,
                        "current_page": page,
                    },
                )
                rows.extend(data.get("transactions", []))
                page = (data.get("meta") or {}).get("next_page")
                if len(rows) > 20000:
                    break
        records = []
        for t in rows:
            raw = Decimal(str(t.get("amount", 0)))
            amount = raw if t.get("side") == "credit" else -abs(raw)
            settled = (t.get("settled_at") or t.get("emitted_at") or "")[:10]
            label = " ".join(filter(None, [t.get("label"), t.get("reference")]))[:300] or t.get(
                "operation_type", "Opération"
            )
            records.append(BankRecord(f"qonto:{t['transaction_id']}", date.fromisoformat(settled), label, amount))
        # Qonto donne le solde actuel : on reconstitue le solde après chaque opération récupérée.
        if ctx.allowed("read_balance") and account.get("balance") is not None and records:
            running = Decimal(str(account["balance"]))
            for record in reversed(records):
                record.balance = running
                running -= record.amount
        result.transactions = records
        last = max((r.booked_on for r in records), default=None)
        result.cursor = {"since": (last - timedelta(days=3)).isoformat() if last else since}
        result.notes.append(f"{len(records)} opération(s) lues depuis le {since}.")
        return result
