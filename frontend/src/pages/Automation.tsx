import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, errorMessage, formatDateTime } from "../api";
import { agentsApi, LEVELS, MODE_LABELS, proposerLabel } from "../agents";
import type { Action, ActionStatus, CatalogItem } from "../agents";
import { Alert as Notice, Dialog, Field, PageHeader } from "../components/ui";
import { eur } from "../format";
import { useSession } from "../session";

type Tab = "pending" | "history" | "policies" | "outbox" | "tasks";

const STATUS_TONE: Record<ActionStatus, string> = {
  pending: "warn", approved: "ok", executing: "warn", done: "ok", failed: "danger",
  rejected: "muted", cancelled: "muted", undone: "muted",
};

export function Automation() {
  const { company } = useSession();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "pending";
  const highlight = params.get("action");
  const [data, setData] = useState<{ items: Action[]; counts: Partial<Record<ActionStatus, number>>; can_approve: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (company) agentsApi.actions(company.id).then(setData, (e) => setError(errorMessage(e)));
  }, [company]);
  useEffect(load, [load]);

  if (!company) return null;
  const pending = data?.items.filter((a) => a.status === "pending") ?? [];
  const history = data?.items.filter((a) => a.status !== "pending") ?? [];

  return (
    <>
      <PageHeader
        title="Centre d'automatisation"
        lead="Ce que les agents proposent, ce que vous avez autorisé, et tout ce qui a été exécuté. Rien de sensible ne part sans votre accord."
      />
      {error && <Notice>{error}</Notice>}
      <div className="segmented" role="tablist" aria-label="Sections">
        {(
          [
            ["pending", `À valider (${pending.length})`],
            ["history", "Historique"],
            ["policies", "Autorisations"],
            ["outbox", "Courriels envoyés"],
            ["tasks", "Tâches"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setParams({ tab: key })}>
            {label}
          </button>
        ))}
      </div>

      {tab === "pending" && (
        <div className="alert-list">
          {data && pending.length === 0 && (
            <section className="card empty">
              <p className="muted">
                Aucune action en attente. Les agents proposent des actions depuis les <Link to="/alertes">alertes</Link> et le{" "}
                <Link to="/conseiller">conseiller</Link>.
              </p>
            </section>
          )}
          {pending.map((a) => (
            <PendingAction key={a.id} action={a} companyId={company.id} canApprove={data?.can_approve ?? false} highlight={a.id === highlight} onDone={load} />
          ))}
        </div>
      )}
      {tab === "history" && (
        <History items={history} companyId={company.id} canApprove={data?.can_approve ?? false} highlight={highlight} onChanged={load} />
      )}
      {tab === "policies" && <Policies companyId={company.id} />}
      {tab === "outbox" && <Outbox companyId={company.id} />}
      {tab === "tasks" && <Tasks companyId={company.id} />}
    </>
  );
}

function LevelBadge({ level }: { level: 1 | 2 | 3 }) {
  return (
    <span className={`level level-${level}`} title={LEVELS[level].hint}>
      {LEVELS[level].label}
    </span>
  );
}

function PendingAction({
  action,
  companyId,
  canApprove,
  highlight,
  onDone,
}: {
  action: Action;
  companyId: string;
  canApprove: boolean;
  highlight: boolean;
  onDone: () => void;
}) {
  const isEmail = action.action_type.startsWith("email.");
  const [to, setTo] = useState(action.payload.to?.endsWith(".invalid") ? "" : (action.payload.to ?? ""));
  const [subject, setSubject] = useState(action.payload.subject ?? "");
  const [body, setBody] = useState(action.payload.body ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secure, setSecure] = useState(false);

  async function approve(confirmation?: string) {
    setBusy(true);
    setError(null);
    try {
      const overrides: Record<string, string> = {};
      if (isEmail) {
        if (to !== action.payload.to) overrides.to = to;
        if (subject !== action.payload.subject) overrides.subject = subject;
        if (body !== action.payload.body) overrides.body = body;
      }
      const result = await agentsApi.approve(companyId, action.id, { overrides, confirmation });
      if (result.status === "failed") setError(result.error ?? "L'exécution a échoué.");
      setSecure(false);
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 428) setSecure(true);
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    setBusy(true);
    try {
      await agentsApi.reject(companyId, action.id);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`card action-card lvl-border-${action.risk_level}${highlight ? " highlight" : ""}`} id={`action-${action.id}`}>
      <div className="action-head">
        <LevelBadge level={action.risk_level} />
        <span className="muted small">
          Proposée par {proposerLabel(action.proposed_by)} · {formatDateTime(action.created_at)}
          {action.trigger.alert && (
            <>
              {" · "}
              <Link to={`/alertes#${encodeURIComponent(action.trigger.alert)}`}>voir l'alerte à l'origine</Link>
            </>
          )}
        </span>
      </div>
      <h2>{action.title}</h2>
      {isEmail ? (
        <div className="email-preview">
          <Field label="Destinataire" hint={!action.payload.to || action.payload.to.endsWith(".invalid") ? "Adresse inconnue : saisissez-la. Elle sera mémorisée pour ce tiers." : undefined}>
            <input type="email" required value={to} disabled={!canApprove} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <Field label="Objet">
            <input value={subject} disabled={!canApprove} onChange={(e) => setSubject(e.target.value)} />
          </Field>
          <Field label="Message">
            <textarea rows={10} value={body} disabled={!canApprove} onChange={(e) => setBody(e.target.value)} />
          </Field>
        </div>
      ) : action.action_type === "payment.transfer" ? (
        <dl className="figures">
          <div>
            <dt>Bénéficiaire</dt>
            <dd>{action.payload.creditor_name}</dd>
          </div>
          <div>
            <dt>Montant</dt>
            <dd>{eur(Number(action.payload.amount), 2)}</dd>
          </div>
          <div>
            <dt>IBAN bénéficiaire</dt>
            <dd className="mono">{action.payload.creditor_iban}</dd>
          </div>
          <div>
            <dt>Référence</dt>
            <dd>{action.payload.reference}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">{action.payload.title ?? action.type_label}</p>
      )}
      {error && <Notice>{error}</Notice>}
      {canApprove ? (
        <div className="form-actions">
          <button className="btn" disabled={busy} onClick={() => void reject()}>
            Refuser
          </button>
          <button className="btn primary" disabled={busy || (isEmail && !to)} onClick={() => void approve()}>
            {action.risk_level === 3 ? "Valider (sécurisé)…" : isEmail ? "Autoriser l'envoi" : "Autoriser"}
          </button>
        </div>
      ) : (
        <p className="muted small">En attente de la validation du dirigeant.</p>
      )}
      {secure && <SecureApproval onCancel={() => setSecure(false)} onConfirm={(c) => approve(c)} busy={busy} />}
    </article>
  );
}

function SecureApproval({ onCancel, onConfirm, busy }: { onCancel: () => void; onConfirm: (c: string) => Promise<void>; busy: boolean }) {
  const [password, setPassword] = useState("");
  const [word, setWord] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await agentsApi.reauth(password);
      await onConfirm(word);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog title="Validation renforcée" onClose={onCancel}>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <p className="muted">
          Opération sensible. Confirmez votre mot de passe et tapez <strong>CONFIRMER</strong>. Cette validation est
          enregistrée dans le journal d'activité.
        </p>
        <Field label="Votre mot de passe">
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Tapez CONFIRMER">
          <input required value={word} onChange={(e) => setWord(e.target.value)} />
        </Field>
        {error && <Notice>{error}</Notice>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onCancel}>
            Annuler
          </button>
          <button className="btn primary" disabled={busy || word.trim().toUpperCase() !== "CONFIRMER"}>
            Valider l'opération
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function History({
  items,
  companyId,
  canApprove,
  highlight,
  onChanged,
}: {
  items: Action[];
  companyId: string;
  canApprove: boolean;
  highlight: string | null;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  async function undo(a: Action) {
    try {
      await agentsApi.undo(companyId, a.id);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return (
    <section className="card flush">
      {error && <Notice>{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Opération</th>
              <th>Proposée par</th>
              <th>Autorisation</th>
              <th>Résultat</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className={a.id === highlight ? "row-highlight" : ""}>
                <td className="nowrap" data-label="Date">
                  {formatDateTime(a.executed_at ?? a.decided_at ?? a.created_at)}
                </td>
                <td data-label="Opération">
                  <strong>{a.title}</strong>
                  <div className="small">
                    <LevelBadge level={a.risk_level} />
                  </div>
                </td>
                <td data-label="Proposée par">{proposerLabel(a.proposed_by)}</td>
                <td data-label="Autorisation" className="small">
                  {a.authorization.mode === "automatic"
                    ? "Règle automatique"
                    : a.authorization.mode === "forbidden"
                      ? "Bloquée par vos autorisations"
                      : `${a.authorization.decision ?? ""}${a.authorization.by ? ` par ${a.authorization.by}` : ""}`}
                  {a.authorization.reauthenticated_at && <div className="muted">mot de passe confirmé</div>}
                  {a.authorization.modified_fields && a.authorization.modified_fields.length > 0 && (
                    <div className="muted">modifiée avant envoi : {a.authorization.modified_fields.join(", ")}</div>
                  )}
                </td>
                <td data-label="Résultat" className="small">
                  <span className={`tag status-${STATUS_TONE[a.status]}`}>{a.status_label}</span>
                  <div>{a.error ?? a.result.summary}</div>
                </td>
                <td className="actions" data-label="">
                  {a.has_file && canApprove && (
                    <a className="btn" href={agentsApi.fileUrl(companyId, a.id)}>
                      Télécharger
                    </a>
                  )}
                  {a.reversible && canApprove && (
                    <button className="btn" onClick={() => void undo(a)}>
                      Annuler
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && <p className="muted empty-row">Aucune opération pour l'instant.</p>}
      </div>
    </section>
  );
}

function Policies({ companyId }: { companyId: string }) {
  const [data, setData] = useState<{ can_edit: boolean; items: CatalogItem[] } | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const load = useCallback(() => {
    agentsApi.catalog(companyId).then(setData, (e) => setNotice({ kind: "error", text: errorMessage(e) }));
  }, [companyId]);
  useEffect(load, [load]);
  async function set(item: CatalogItem, mode: string) {
    try {
      await agentsApi.setPolicy(companyId, item.key, mode);
      setNotice({ kind: "ok", text: `« ${item.label} » : ${MODE_LABELS[mode as keyof typeof MODE_LABELS].toLowerCase()}.` });
      load();
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    }
  }
  return (
    <section className="card">
      <p className="muted">
        Vous décidez de ce que les agents peuvent faire. Une opération de niveau 3 n'est jamais automatique : elle exige toujours
        votre mot de passe et une confirmation explicite.
      </p>
      {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
      {([1, 2, 3] as const).map((level) => (
        <div key={level} className="policy-group">
          <h3>
            <span className={`level level-${level}`}>{LEVELS[level].label}</span>
            <span className="muted small"> {LEVELS[level].hint}</span>
          </h3>
          <ul className="plain">
            {data?.items
              .filter((i) => i.level === level)
              .map((i) => (
                <li key={i.key} className="policy-row">
                  <span>
                    <strong>{i.label}</strong>
                    <span className="muted small module-text">
                      {i.description} {i.reversible ? "Annulable." : "Irréversible."}
                    </span>
                  </span>
                  <select aria-label={`Autorisation pour ${i.label}`} value={i.mode} disabled={!data.can_edit} onChange={(e) => void set(i, e.target.value)}>
                    {i.allowed_modes.map((m) => (
                      <option key={m} value={m}>
                        {MODE_LABELS[m]}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function Outbox({ companyId }: { companyId: string }) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof agentsApi.outbox>> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    agentsApi.outbox(companyId).then(setItems, () => setItems([]));
  }, [companyId]);
  return (
    <section className="card flush">
      <ul className="plain mail-list">
        {items?.map((m) => (
          <li key={m.id}>
            <button className="mail-head" aria-expanded={open === m.id} onClick={() => setOpen(open === m.id ? null : m.id)}>
              <span>
                <strong>{m.subject}</strong>
                <span className="muted small module-text">
                  À {m.to} · {formatDateTime(m.sent_at)}
                </span>
              </span>
              <span className={`tag ${m.transport === "smtp" ? "status-ok" : ""}`}>{m.transport === "smtp" ? "Envoyé" : "Boîte d'envoi locale"}</span>
            </button>
            {open === m.id && (
              <div className="mail-body">
                <pre>{m.body}</pre>
                <a className="btn" href={agentsApi.emlUrl(companyId, m.id)}>
                  Télécharger (.eml)
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>
      {items && items.length === 0 && <p className="muted empty-row">Aucun courriel émis.</p>}
      {items && items.length > 0 && items.some((m) => m.transport !== "smtp") && (
        <p className="muted small empty-row">
          Sans serveur de messagerie configuré, les courriels autorisés restent dans cette boîte d'envoi : téléchargez-les pour
          les envoyer depuis votre messagerie, ou configurez SMTP sur le boîtier.
        </p>
      )}
    </section>
  );
}

function Tasks({ companyId }: { companyId: string }) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof agentsApi.tasks>> | null>(null);
  const load = useCallback(() => agentsApi.tasks(companyId).then(setItems, () => setItems([])), [companyId]);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <section className="card">
      <ul className="plain task-list">
        {items?.map((t) => (
          <li key={t.id}>
            <label className="check">
              <input type="checkbox" checked={t.done} onChange={(e) => void agentsApi.setTaskDone(companyId, t.id, e.target.checked).then(load)} />
              <span className={t.done ? "done" : ""}>
                {t.title}
                {t.details && <span className="muted small module-text">{t.details}</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {items && items.length === 0 && <p className="muted">Aucune tâche.</p>}
    </section>
  );
}
