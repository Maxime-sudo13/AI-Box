import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { errorMessage } from "../api";
import { Sparkline } from "../components/charts/Sparkline";
import { formatValue, SeverityBadge } from "../components/finance-ui";
import { Alert as Notice, PageHeader } from "../components/ui";
import { financeApi } from "../finance";
import type { Alert } from "../finance";
import { dateFr, eur } from "../format";
import { useSession } from "../session";

type Filter = "open" | "done" | "all";

const STATUS_LABELS: Record<Alert["status"], string> = {
  open: "Ouverte",
  acknowledged: "Prise en compte",
  resolved: "Traitée",
  dismissed: "Ignorée",
};

export function Alerts() {
  const { company, canEditData } = useSession();
  const [items, setItems] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("open");
  const { hash } = useLocation();
  const target = hash ? decodeURIComponent(hash.slice(1)) : null;

  const load = useCallback(() => {
    if (!company) return;
    financeApi.alerts(company.id).then((r) => setItems(r.items), (e) => setError(errorMessage(e)));
  }, [company]);
  useEffect(load, [load]);

  useEffect(() => {
    if (target && items) document.getElementById(`alert-${target}`)?.scrollIntoView({ block: "start" });
  }, [target, items]);

  if (!company) return null;
  const open = items?.filter((a) => a.status === "open") ?? [];
  const done = items?.filter((a) => a.status !== "open") ?? [];
  const shown = filter === "open" ? open : filter === "done" ? done : (items ?? []);

  return (
    <>
      <PageHeader
        title="Alertes et opportunités"
        lead="Ce que le boîtier a repéré dans vos données. Chaque alerte cite ses sources et détaille son calcul ; les montants sont des estimations."
      />
      {error && <Notice>{error}</Notice>}
      {items && (
        <div className="alert-summary">
          <div>
            <span className="kpi-value">{open.length}</span>
            <span className="muted small">alerte{open.length > 1 ? "s" : ""} ouverte{open.length > 1 ? "s" : ""}</span>
          </div>
          <div>
            <span className="kpi-value">{open.filter((a) => a.severity === "high").length}</span>
            <span className="muted small">prioritaire(s)</span>
          </div>
          <div>
            <span className="kpi-value">{open.filter((a) => a.severity === "medium").length}</span>
            <span className="muted small">importante(s)</span>
          </div>
        </div>
      )}
      <div className="segmented" role="tablist" aria-label="Filtrer les alertes">
        {(
          [
            ["open", `Ouvertes (${open.length})`],
            ["done", `Traitées ou ignorées (${done.length})`],
            ["all", "Toutes"],
          ] as [Filter, string][]
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={filter === key} className={filter === key ? "on" : ""} onClick={() => setFilter(key)}>
            {label}
          </button>
        ))}
      </div>
      {items && shown.length === 0 && (
        <section className="card empty">
          <p className="muted">{filter === "open" ? "Aucune alerte ouverte. Tout est en ordre." : "Rien à afficher."}</p>
        </section>
      )}
      <div className="alert-list">
        {shown.map((a) => (
          <AlertCard
            key={a.fingerprint}
            alert={a}
            companyId={company.id}
            canEdit={canEditData}
            initiallyOpen={a.fingerprint === target}
            onChanged={load}
          />
        ))}
      </div>
    </>
  );
}

function AlertCard({
  alert,
  companyId,
  canEdit,
  initiallyOpen,
  onChanged,
}: {
  alert: Alert;
  companyId: string;
  canEdit: boolean;
  initiallyOpen: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [note, setNote] = useState(alert.review_note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function review(status: Alert["status"]) {
    setBusy(true);
    setError(null);
    try {
      await financeApi.reviewAlert(companyId, alert.fingerprint, status, note);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article id={`alert-${alert.fingerprint}`} className={`card alert-card sev-border-${alert.severity}${alert.status !== "open" ? " closed" : ""}`}>
      <button type="button" className="alert-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="alert-meta">
          <SeverityBadge severity={alert.severity} />
          {alert.status !== "open" && <span className="tag">{STATUS_LABELS[alert.status]}</span>}
        </span>
        <span className="alert-title">{alert.title}</span>
        <span className="alert-summary-text muted">{alert.summary}</span>
        {alert.impact?.amount ? (
          <span className="alert-impact">
            <strong>{eur(alert.impact.amount)}</strong>
            <span className="muted small">{alert.impact.label}</span>
          </span>
        ) : null}
        <span className="chevron" aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <div className="alert-body">
          {alert.figures.length > 0 && (
            <dl className="figures">
              {alert.figures.map((f) => (
                <div key={f.label}>
                  <dt>{f.label}</dt>
                  <dd>{formatValue(f.value, f.unit)}</dd>
                </div>
              ))}
              {alert.series && alert.series.length > 2 && (
                <div>
                  <dt>Évolution du prix</dt>
                  <dd>
                    <Sparkline values={alert.series.map((p) => p.value)} label="Évolution du prix unitaire" />
                  </dd>
                </div>
              )}
            </dl>
          )}
          {alert.details.length > 0 && (
            <ul className="notes">
              {alert.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
          {alert.impact && (
            <p className="formula small">
              <span className="muted">Calcul : </span>
              {alert.impact.formula}
            </p>
          )}
          {alert.invoices.length > 0 && (
            <div>
              <h3>Documents concernés</h3>
              <ul className="evidence">
                {alert.invoices.map((inv) => (
                  <li key={inv.document_id}>
                    <Link to={`/donnees/documents/${inv.document_id}`}>
                      {inv.party} — n° {inv.number ?? "?"}
                    </Link>
                    <span className="muted">{dateFr(inv.date)}</span>
                    <span className="num">{eur(inv.amount, 2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {alert.transactions.length > 0 && (
            <div>
              <h3>Opérations bancaires concernées</h3>
              <ul className="evidence">
                {alert.transactions.map((t) => (
                  <li key={t.id}>
                    <span>{t.label}</span>
                    <span className="muted">{dateFr(t.date)}</span>
                    <span className="num">{eur(t.amount, 2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {canEdit && (
            <div className="alert-actions">
              <label className="field">
                <span className="field-label">Note (facultative)</span>
                <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Ex. : appelé le fournisseur le 14/11" />
              </label>
              <div className="form-actions">
                {alert.status === "open" ? (
                  <>
                    <button className="btn" disabled={busy} onClick={() => review("dismissed")}>
                      Ignorer
                    </button>
                    <button className="btn" disabled={busy} onClick={() => review("acknowledged")}>
                      Je m'en occupe
                    </button>
                    <button className="btn primary" disabled={busy} onClick={() => review("resolved")}>
                      Marquer comme traitée
                    </button>
                  </>
                ) : (
                  <button className="btn" disabled={busy} onClick={() => review("open")}>
                    Rouvrir
                  </button>
                )}
              </div>
              {error && <Notice>{error}</Notice>}
            </div>
          )}
          {alert.reviewed_at && (
            <p className="muted small">
              {STATUS_LABELS[alert.status]} le {dateFr(alert.reviewed_at)}
              {alert.review_note ? ` — « ${alert.review_note} »` : ""}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
