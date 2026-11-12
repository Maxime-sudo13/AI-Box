import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { errorMessage, formatDateTime } from "../api";
import { connectorsApi } from "../connectors";
import type { Catalog, ConnectionItem, ConnectorInfo, SyncRun } from "../connectors";
import { Alert as Notice, Dialog, Field, PageHeader } from "../components/ui";
import { useSession } from "../session";

const STATUS: Record<ConnectionItem["status"], { label: string; tone: string }> = {
  active: { label: "Active", tone: "ok" },
  error: { label: "En erreur", tone: "danger" },
  expired: { label: "Accès à renouveler", tone: "danger" },
  paused: { label: "En pause", tone: "muted" },
};

const ICONS: Record<string, string> = { folder: "📁", imap: "✉️", qonto: "🏦" };

function describeRun(run: SyncRun): string {
  if (run.status === "failed") return run.error ?? "Échec";
  const s = run.stats as Record<string, number>;
  const parts = [];
  if (s.documents) parts.push(`${s.documents} document(s)`);
  if (s.tables) parts.push(`${s.tables} export(s) CSV`);
  if (s.transactions) parts.push(`${s.transactions} opération(s) bancaire(s)`);
  if (s.duplicates) parts.push(`${s.duplicates} déjà connu(s)`);
  if (s.to_review) parts.push(`${s.to_review} à vérifier`);
  return parts.length ? parts.join(" · ") : "Rien de nouveau";
}

export function Connectors() {
  const { company, canManageCompany, canEditData } = useSession();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [items, setItems] = useState<ConnectionItem[] | null>(null);
  const [adding, setAdding] = useState<ConnectorInfo | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!company) return;
    connectorsApi.list(company.id).then(setItems, (e) => setNotice({ kind: "error", text: errorMessage(e) }));
  }, [company]);
  useEffect(() => {
    connectorsApi.catalog().then(setCatalog, (e) => setNotice({ kind: "error", text: errorMessage(e) }));
    load();
  }, [load]);

  if (!company) return null;

  async function sync(c: ConnectionItem) {
    setBusy(c.id);
    setNotice(null);
    try {
      const { run } = await connectorsApi.sync(company!.id, c.id);
      setNotice({ kind: run.status === "failed" ? "error" : "ok", text: `${c.label} : ${describeRun(run)}.` });
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  async function update(c: ConnectionItem, body: Record<string, unknown>, message: string) {
    try {
      await connectorsApi.update(company!.id, c.id, body);
      setNotice({ kind: "ok", text: message });
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    }
  }

  async function remove(c: ConnectionItem) {
    if (!window.confirm(`Déconnecter « ${c.label} » ? Ses identifiants seront effacés ; les données déjà importées restent.`)) return;
    try {
      await connectorsApi.remove(company!.id, c.id);
      setNotice({ kind: "ok", text: `« ${c.label} » déconnecté.` });
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    }
  }

  const info = (key: string) => catalog?.available.find((a) => a.key === key);

  return (
    <>
      <PageHeader
        title="Logiciels connectés"
        lead="Le boîtier récupère lui-même vos données, uniquement avec les droits que vous accordez. Les identifiants sont chiffrés et ne quittent jamais le boîtier."
      />
      {catalog?.offline_mode && (
        <div className="callout">
          <strong>Mode « zéro communication externe » actif.</strong> Les connecteurs en ligne sont désactivés : le boîtier ne
          contacte aucun service extérieur. Seuls les dépôts locaux fonctionnent.
        </div>
      )}
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}

      <section className="card flush">
        <div className="card-head card-pad">
          <h2>Connexions de {company.name}</h2>
        </div>
        {items && items.length === 0 && <p className="muted empty-row">Aucune connexion. Choisissez un connecteur ci-dessous.</p>}
        <ul className="plain conn-list">
          {items?.map((c) => {
            const meta = info(c.connector);
            return (
              <li key={c.id} className="conn">
                <div className="conn-main">
                  <span className="conn-icon" aria-hidden="true">
                    {ICONS[c.connector] ?? "🔌"}
                  </span>
                  <div>
                    <strong>{c.label}</strong>
                    <span className={`tag status-${STATUS[c.status].tone}`}>{STATUS[c.status].label}</span>
                    <div className="muted small">
                      {c.connector_name} · toutes les {c.interval_minutes} min ·{" "}
                      {c.last_sync_at ? `dernière synchronisation le ${formatDateTime(c.last_sync_at)}` : "jamais synchronisée"}
                    </div>
                    {c.last_run && c.status !== "expired" && c.status !== "error" && (
                      <div className="small">Dernier passage : {describeRun(c.last_run)}</div>
                    )}
                    {c.last_error && <div className="small text-bad">{c.last_error}</div>}
                  </div>
                </div>
                <div className="conn-perms">
                  {meta?.permissions.map((p) => (
                    <label key={p.key} className="check small">
                      <input
                        type="checkbox"
                        checked={c.permissions.includes(p.key)}
                        disabled={!canManageCompany}
                        onChange={(e) =>
                          void update(
                            c,
                            {
                              permissions: e.target.checked
                                ? [...c.permissions, p.key]
                                : c.permissions.filter((k) => k !== p.key),
                            },
                            `Permission « ${p.label} » ${e.target.checked ? "accordée" : "retirée"}.`,
                          )
                        }
                      />
                      <span>
                        {p.label}
                        <span className={`perm ${p.write ? "write" : "read"}`}>{p.write ? "écriture" : "lecture"}</span>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="conn-actions">
                  {canEditData && c.status !== "paused" && (
                    <button className="btn primary" disabled={busy === c.id} onClick={() => void sync(c)}>
                      {busy === c.id ? "Synchronisation…" : "Synchroniser"}
                    </button>
                  )}
                  {canManageCompany && (
                    <>
                      <button
                        className="btn"
                        onClick={() => void update(c, { paused: c.status !== "paused" }, c.status === "paused" ? "Connexion reprise." : "Connexion mise en pause.")}
                      >
                        {c.status === "paused" ? "Reprendre" : "Pause"}
                      </button>
                      <button className="btn ghost" onClick={() => void remove(c)}>
                        Déconnecter
                      </button>
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card">
        <h2>Ajouter une connexion</h2>
        <div className="connector-grid">
          {catalog?.available.map((c) => (
            <div key={c.key} className="connector-card">
              <div className="connector-top">
                <span className="conn-icon" aria-hidden="true">
                  {ICONS[c.key] ?? "🔌"}
                </span>
                <span>
                  <strong>{c.name}</strong>
                  <span className="muted small module-text">{c.category}</span>
                </span>
              </div>
              <p className="small">{c.description}</p>
              <p className="muted small">
                {c.online ? `En ligne${c.hosts.length ? ` : contacte uniquement ${c.hosts.join(", ")}` : ""}.` : "Fonctionne sans Internet."}
              </p>
              <button
                className="btn"
                disabled={!canManageCompany || Boolean(c.disabled_reason)}
                title={c.disabled_reason ?? undefined}
                onClick={() => setAdding(c)}
              >
                Connecter
              </button>
            </div>
          ))}
          {catalog?.planned.map((p) => (
            <div key={p.key} className="connector-card planned">
              <div className="connector-top">
                <span className="conn-icon" aria-hidden="true">
                  🔌
                </span>
                <span>
                  <strong>{p.name}</strong>
                  <span className="muted small module-text">{p.category}</span>
                </span>
              </div>
              <p className="small muted">{p.description}</p>
              <span className="tag">À venir</span>
            </div>
          ))}
        </div>
        {!canManageCompany && <p className="muted small">Seul le dirigeant peut connecter un logiciel.</p>}
      </section>

      {adding && catalog && (
        <ConnectDialog
          connector={adding}
          importRoot={catalog.import_root}
          companyId={company.id}
          onClose={() => setAdding(null)}
          onDone={(c) => {
            setAdding(null);
            setNotice({ kind: "ok", text: `${c.label} connecté. ${c.test_message ?? ""}` });
            load();
          }}
        />
      )}
    </>
  );
}

function ConnectDialog({
  connector,
  importRoot,
  companyId,
  onClose,
  onDone,
}: {
  connector: ConnectorInfo;
  importRoot: string;
  companyId: string;
  onClose: () => void;
  onDone: (c: ConnectionItem) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(connector.fields.map((f) => [f.key, f.default === null ? "" : String(f.default)])),
  );
  const [perms, setPerms] = useState<string[]>(connector.permissions.filter((p) => p.default).map((p) => p.key));
  const [interval, setInterval_] = useState(connector.key === "folder" ? 15 : 60);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const settings: Record<string, string | number> = {};
    const secrets: Record<string, string> = {};
    for (const f of connector.fields) {
      if (f.secret) secrets[f.key] = values[f.key];
      else settings[f.key] = f.kind === "number" ? Number(values[f.key]) : values[f.key];
    }
    try {
      onDone(await connectorsApi.create(companyId, { connector: connector.key, settings, secrets, permissions: perms, interval_minutes: interval }));
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Connecter : ${connector.name}`} onClose={onClose}>
      <form className="form" onSubmit={(e) => void submit(e)}>
        {connector.key === "folder" && (
          <p className="muted small">
            Racine des dépôts du boîtier : <span className="mono">{importRoot}</span>. Le connecteur ne peut rien lire en dehors.
          </p>
        )}
        {connector.fields.map((f) => (
          <Field key={f.key} label={`${f.label}${f.required ? "" : " (facultatif)"}`} hint={f.hint ?? undefined}>
            <input
              type={f.kind === "password" ? "password" : f.kind === "number" ? "number" : f.kind === "email" ? "email" : "text"}
              autoComplete={f.secret ? "new-password" : "off"}
              required={f.required}
              value={values[f.key]}
              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
            />
          </Field>
        ))}
        <fieldset className="fieldset">
          <legend>Ce que vous autorisez</legend>
          {connector.permissions.map((p) => (
            <label key={p.key} className="check small">
              <input
                type="checkbox"
                checked={perms.includes(p.key)}
                onChange={(e) => setPerms(e.target.checked ? [...perms, p.key] : perms.filter((k) => k !== p.key))}
              />
              <span>
                {p.label}
                <span className={`perm ${p.write ? "write" : "read"}`}>{p.write ? "écriture" : "lecture"}</span>
              </span>
            </label>
          ))}
          <p className="muted small">Les droits d'écriture ne sont jamais cochés par défaut.</p>
        </fieldset>
        <Field label="Synchroniser toutes les">
          <select value={interval} onChange={(e) => setInterval_(Number(e.target.value))}>
            {[15, 30, 60, 240, 1440].map((m) => (
              <option key={m} value={m}>
                {m < 60 ? `${m} minutes` : m === 60 ? "heure" : m === 1440 ? "24 heures" : `${m / 60} heures`}
              </option>
            ))}
          </select>
        </Field>
        <p className="muted small">{connector.data_notice}</p>
        {error && <Notice>{error}</Notice>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Annuler
          </button>
          <button className="btn primary" disabled={busy}>
            {busy ? "Test de la connexion…" : "Tester et connecter"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
