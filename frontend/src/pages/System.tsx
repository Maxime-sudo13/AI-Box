import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { errorMessage, formatDateTime, request } from "../api";
import { Alert as Notice, Dialog, Field, PageHeader } from "../components/ui";
import { fileSize } from "../format";

interface BackupItem {
  name: string;
  created_at: string;
  size: number;
  version: string;
  key_fingerprint: string;
  stats: { files?: number; files_bytes?: number };
}

interface Status {
  version: string;
  database_revision: string;
  offline_mode: boolean;
  scheduler_running: boolean;
  ai: { enabled: boolean; model: string; available: boolean };
  smtp_configured: boolean;
  disk: { total: number; free: number; used: number };
  database_bytes: number;
  documents: { count: number; bytes: number };
  pending_actions: number;
  backup: {
    configured: boolean;
    key_fingerprint: string | null;
    directory: string;
    distinct_medium: boolean;
    keep: number;
    count: number;
    last: BackupItem | null;
    last_automatic: { ok: boolean; message: string; at: string } | null;
    next_run: string | null;
  };
  update_keys: number;
  warnings: string[];
}

function Tile({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "ok" | "warn" }) {
  return (
    <div className={`data-card${tone === "warn" ? " tile-warn" : ""}`}>
      <span className="muted small">{label}</span>
      <strong>{value}</strong>
      {hint && <span className="small muted">{hint}</span>}
    </div>
  );
}

export function System() {
  const [status, setStatus] = useState<Status | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [verifying, setVerifying] = useState<BackupItem | null>(null);

  const load = useCallback(() => {
    request<Status>("GET", "/system/status").then(setStatus, (e) => setNotice({ kind: "error", text: errorMessage(e) }));
    request<BackupItem[]>("GET", "/system/backups").then(setBackups, () => {});
  }, []);
  useEffect(load, [load]);

  async function createKey() {
    setBusy(true);
    try {
      const r = await request<{ recovery_key: string }>("POST", "/system/backup-key");
      setNewKey(r.recovery_key);
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  async function backupNow() {
    setBusy(true);
    setNotice(null);
    try {
      const b = await request<BackupItem>("POST", "/system/backups");
      setNotice({ kind: "ok", text: `Sauvegarde créée : ${b.name} (${fileSize(b.size)}).` });
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  if (!status) return <PageHeader title="Système" lead="Chargement…" />;
  const diskPct = Math.round((status.disk.used / status.disk.total) * 100);

  return (
    <>
      <PageHeader title="Système" lead="État du boîtier, sauvegardes et mises à jour. Réservé aux administrateurs." />
      {status.warnings.length > 0 && (
        <ul className="warnings">
          {status.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}

      <div className="data-cards">
        <Tile label="Version" value={status.version} hint={`base : révision ${status.database_revision}`} />
        <Tile
          label="IA locale"
          value={!status.ai.enabled ? "Désactivée" : status.ai.available ? "Active" : "Indisponible"}
          hint={status.ai.model}
          tone={status.ai.enabled && !status.ai.available ? "warn" : undefined}
        />
        <Tile
          label="Communications externes"
          value={status.offline_mode ? "Aucune" : "Autorisées"}
          hint={status.offline_mode ? "mode « zéro communication externe »" : status.smtp_configured ? "connecteurs en ligne et SMTP" : "connecteurs en ligne"}
        />
        <Tile label="Disque" value={`${diskPct} % utilisé`} hint={`${fileSize(status.disk.free)} libres`} tone={diskPct > 90 ? "warn" : undefined} />
        <Tile label="Base de données" value={fileSize(status.database_bytes)} hint={`${status.documents.count} documents · ${fileSize(status.documents.bytes)}`} />
        <Tile label="Tâches planifiées" value={status.scheduler_running ? "En marche" : "Arrêtées"} hint={`${status.pending_actions} action(s) à valider`} />
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Sauvegardes</h2>
            <p className="muted small">
              Chiffrées : le boîtier peut les créer mais pas les relire. Seule la clé de récupération, conservée hors du boîtier,
              permet de les restaurer.
            </p>
          </div>
          {status.backup.configured ? (
            <button className="btn primary" disabled={busy} onClick={() => void backupNow()}>
              {busy ? "Sauvegarde…" : "Sauvegarder maintenant"}
            </button>
          ) : (
            <button className="btn primary" disabled={busy} onClick={() => void createKey()}>
              Créer la clé de récupération
            </button>
          )}
        </div>
        <dl className="facts">
          <div>
            <dt>Emplacement</dt>
            <dd className="mono">{status.backup.directory}</dd>
          </div>
          <div>
            <dt>Support</dt>
            <dd className={status.backup.distinct_medium ? "text-good" : "text-bad"}>
              {status.backup.distinct_medium ? "✓ distinct des données" : "✗ même disque que les données"}
            </dd>
          </div>
          <div>
            <dt>Planification</dt>
            <dd>
              {status.backup.next_run ? `prochaine le ${formatDateTime(status.backup.next_run)}` : "quotidienne"} · {status.backup.keep} conservées
            </dd>
          </div>
          <div>
            <dt>Empreinte de la clé</dt>
            <dd className="mono">{status.backup.key_fingerprint ?? "—"}</dd>
          </div>
        </dl>
        {status.backup.last_automatic && (
          <p className={`small ${status.backup.last_automatic.ok ? "muted" : "text-bad"}`}>
            Dernière sauvegarde ({formatDateTime(status.backup.last_automatic.at)}) : {status.backup.last_automatic.message}
          </p>
        )}
        {backups.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Contenu</th>
                  <th className="num">Taille</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.name}>
                    <td className="nowrap" data-label="Date">
                      {formatDateTime(b.created_at)}
                    </td>
                    <td data-label="Contenu" className="small">
                      Base complète + {b.stats.files ?? 0} fichier(s) · v{b.version}
                    </td>
                    <td className="num nowrap" data-label="Taille">
                      {fileSize(b.size)}
                    </td>
                    <td className="actions">
                      <button className="btn" onClick={() => setVerifying(b)}>
                        Vérifier
                      </button>{" "}
                      <a className="btn ghost" href={`/api/system/backups/${encodeURIComponent(b.name)}/download`}>
                        Télécharger
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <details className="small">
          <summary>Comment restaurer une sauvegarde</summary>
          <p className="muted">
            La restauration remplace toutes les données : elle se fait boîtier arrêté, depuis la console d'administration, avec
            la clé de récupération. Procédure détaillée : docs/industrialisation.md, section « Restaurer ».
          </p>
          <pre className="mono">docker compose exec api python -m app.ops restaurer /sauvegardes/NOM-DU-FICHIER.babk</pre>
        </details>
      </section>

      <section className="card">
        <h2>Mises à jour</h2>
        <p className="muted small">
          Les mises à jour arrivent sous forme de paquet signé par l'éditeur. Le boîtier vérifie la signature et l'empreinte de
          chaque fichier, refuse tout retour à une version antérieure et sauvegarde les données avant d'installer. Aucune donnée
          de l'entreprise n'est envoyée.
        </p>
        <p className="small">
          Clés d'éditeur reconnues : <strong>{status.update_keys}</strong>
          {status.update_keys === 0 && <span className="text-bad"> — aucune mise à jour ne pourra être acceptée.</span>}
        </p>
      </section>

      {newKey && (
        <Dialog title="Votre clé de récupération" onClose={() => setNewKey(null)}>
          <div className="form">
            <p>
              Notez ou imprimez cette clé et rangez-la <strong>hors du boîtier</strong> (coffre, chez l'expert-comptable…). Elle
              ne sera plus jamais affichée. Sans elle, les sauvegardes ne peuvent pas être restaurées.
            </p>
            <p className="recovery-key mono">{newKey}</p>
            <div className="form-actions">
              <button className="btn" onClick={() => window.print()}>
                Imprimer
              </button>
              <button className="btn primary" onClick={() => setNewKey(null)}>
                J'ai mis la clé en lieu sûr
              </button>
            </div>
          </div>
        </Dialog>
      )}
      {verifying && <VerifyDialog item={verifying} onClose={() => setVerifying(null)} />}
    </>
  );
}

function VerifyDialog({ item, onClose }: { item: BackupItem; onClose: () => void }) {
  const [key, setKey] = useState("");
  const [result, setResult] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const r = await request<{ manifest: { files: number; created_at: string } }>("POST", `/system/backups/${encodeURIComponent(item.name)}/verify`, {
        recovery_key: key,
      });
      setResult({ kind: "ok", text: `Sauvegarde intacte et restaurable : base de données lisible, ${r.manifest.files} fichier(s).` });
    } catch (err) {
      setResult({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Vérifier une sauvegarde" onClose={onClose}>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <p className="muted small">
          La sauvegarde est entièrement déchiffrée et contrôlée, sans rien modifier. La clé n'est ni conservée ni journalisée.
        </p>
        <Field label="Clé de récupération">
          <input className="mono" autoComplete="off" required value={key} onChange={(e) => setKey(e.target.value)} />
        </Field>
        {result && <Notice kind={result.kind}>{result.text}</Notice>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Fermer
          </button>
          <button className="btn primary" disabled={busy}>
            {busy ? "Vérification…" : "Vérifier"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
