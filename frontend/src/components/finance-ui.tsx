import { Link } from "react-router-dom";
import type { Alert, BreakdownRow, DocStatus, FieldStatus, Kpi, Quality } from "../finance";
import { eur, num, pct } from "../format";
import { Sparkline } from "./charts/Sparkline";
import { Dialog } from "./ui";

export function formatValue(value: number | null, unit: string): string {
  // Les petits montants (prix unitaires) gardent leurs centimes.
  if (unit === "eur") return eur(value, value !== null && Math.abs(value) < 100 ? 2 : 0);
  if (unit === "pct") return pct(value);
  if (unit === "days") return `${num(value)} j`;
  return num(value);
}

const QUALITY: Record<Quality, { label: string; hint: string }> = {
  confirmed: { label: "Données vérifiées", hint: "Calculé à partir de documents vérifiés et du relevé bancaire." },
  estimated: { label: "Estimation", hint: "Une partie des données est encore à vérifier ou a été déduite." },
  partial: { label: "Période incomplète", hint: "Les données ne couvrent pas toute la période." },
  missing: { label: "Données manquantes", hint: "Importez les données nécessaires à ce calcul." },
};

export function QualityBadge({ quality }: { quality: Quality }) {
  return (
    <span className={`quality q-${quality}`} title={QUALITY[quality].hint}>
      <span className="quality-dot" aria-hidden="true" />
      {QUALITY[quality].label}
    </span>
  );
}

/** Variation colorée selon qu'elle est favorable ou non, toujours accompagnée d'une flèche. */
export function Delta({
  change,
  unit,
  goodDirection,
  suffix = "vs mois précédent",
}: {
  change: number | null;
  unit: "pct" | "pts";
  goodDirection: "up" | "down";
  suffix?: string;
}) {
  if (change === null || Number.isNaN(change)) return <span className="delta neutral">—</span>;
  const flat = Math.abs(change) < 0.05;
  const good = flat ? null : (change > 0) === (goodDirection === "up");
  const arrow = flat ? "→" : change > 0 ? "↑" : "↓";
  const value =
    unit === "pts"
      ? `${change > 0 ? "+" : ""}${num(change, 1)} pt`
      : `${change > 0 ? "+" : ""}${num(change, 1)} %`;
  return (
    <span className={`delta ${good === null ? "neutral" : good ? "good" : "bad"}`}>
      <span aria-hidden="true">{arrow}</span> {value} <span className="delta-suffix">{suffix}</span>
    </span>
  );
}

export function KpiTile({
  kpi,
  trend,
  highlight,
  onOpen,
}: {
  kpi: Kpi;
  trend: (number | null)[];
  highlight: number;
  onOpen: () => void;
}) {
  const ratio = kpi.unit === "pct";
  const change = ratio ? kpi.change : kpi.change_pct;
  return (
    <button type="button" className="kpi" onClick={onOpen} aria-label={`${kpi.label} : ${formatValue(kpi.value, kpi.unit)}. Voir le détail du calcul`}>
      <span className="kpi-label">{kpi.label}</span>
      <span className="kpi-value">{formatValue(kpi.value, kpi.unit)}</span>
      <span className="kpi-foot">
        <Delta change={change} unit={ratio ? "pts" : "pct"} goodDirection={kpi.good_direction} />
        <Sparkline values={trend} highlight={highlight} label={`Tendance sur 12 mois : ${kpi.label}`} />
      </span>
      {kpi.secondary && (
        <span className="kpi-secondary">
          {kpi.secondary.label} : <strong>{formatValue(kpi.secondary.value, kpi.secondary.unit)}</strong>
        </span>
      )}
      <span className="kpi-how">
        {kpi.quality !== "confirmed" && <QualityBadge quality={kpi.quality} />}
        <span className="kpi-link">Comment est-ce calculé ?</span>
      </span>
    </button>
  );
}

function inputLink(link: { month?: string; category?: string } | null, label: string): string | null {
  if (!link?.category) return null;
  const params = new URLSearchParams();
  if (link.month) params.set("month", link.month);
  params.set("category", link.category);
  const bankOnly = /salaires|cotisations|rémunération|loyer|assurances|impôts|frais bancaires/i.test(label);
  params.set("tab", bankOnly ? "banque" : "factures");
  return `/donnees?${params}`;
}

export function KpiDetail({ kpi, onClose }: { kpi: Kpi; onClose: () => void }) {
  return (
    <Dialog title={kpi.label} onClose={onClose}>
      <div className="detail">
        <div className="detail-head">
          <span className="detail-value">{formatValue(kpi.value, kpi.unit)}</span>
          <span className="muted">{kpi.period}</span>
          <QualityBadge quality={kpi.quality} />
        </div>
        <section>
          <h3>Formule</h3>
          <p className="formula">{kpi.formula}</p>
        </section>
        <section>
          <h3>Données utilisées</h3>
          <table className="inputs">
            <tbody>
              {kpi.inputs.map((input) => {
                const href = inputLink(input.link, input.label);
                return (
                  <tr key={input.label}>
                    <td>
                      {input.label}
                      <div className="muted small">
                        {href ? <Link to={href}>{input.source}</Link> : input.source}
                      </div>
                    </td>
                    <td className="num">{formatValue(input.value, input.unit)}</td>
                  </tr>
                );
              })}
            </tbody>
            {kpi.unit === "eur" && kpi.key === "ebe" && (
              <tfoot>
                <tr>
                  <td>EBE estimé</td>
                  <td className="num">{formatValue(kpi.value, kpi.unit)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </section>
        {kpi.previous !== null && (
          <p className="muted small">
            Mois précédent : {formatValue(kpi.previous, kpi.unit)}
          </p>
        )}
        {kpi.notes.length > 0 && (
          <section>
            <h3>À savoir</h3>
            <ul className="notes">
              {kpi.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Dialog>
  );
}

export function Breakdown({ rows, month }: { rows: BreakdownRow[]; month: string }) {
  const max = Math.max(...rows.map((r) => r.amount), 1);
  return (
    <ul className="breakdown">
      {rows.map((row) => {
        const change = row.change_vs_average_pct;
        const notable = change !== null && Math.abs(change) >= 10 && row.amount > 300;
        const tab = row.invoices ? "factures" : "banque";
        return (
          <li key={row.category}>
            <Link to={`/donnees?tab=${tab}&month=${month}&category=${row.category}`} className="bd-row">
              <span className="bd-label">
                {row.label}
                <span className="muted small">{row.group_label}</span>
              </span>
              <span className="bd-bar" aria-hidden="true">
                <span style={{ width: `${Math.max(1.5, (row.amount / max) * 100)}%` }} />
              </span>
              <span className="bd-value">{eur(row.amount)}</span>
              <span className={`bd-change ${notable ? (change! > 0 ? "bad" : "good") : "neutral"}`}>
                {change === null ? "—" : `${change > 0 ? "↑ +" : change < 0 ? "↓ " : ""}${num(change, 0)} %`}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

const SEVERITY = {
  high: { label: "Prioritaire", icon: "!" },
  medium: { label: "Important", icon: "•" },
  low: { label: "À noter", icon: "i" },
} as const;

export function SeverityBadge({ severity }: { severity: Alert["severity"] }) {
  return (
    <span className={`severity sev-${severity}`}>
      <span className="sev-icon" aria-hidden="true">
        {SEVERITY[severity].icon}
      </span>
      {SEVERITY[severity].label}
    </span>
  );
}

const DOC_STATUS: Record<DocStatus, string> = {
  verified: "ok",
  validated: "ok",
  to_review: "warn",
  duplicate: "muted",
  ignored: "muted",
  failed: "danger",
};

export function DocStatusBadge({ status, label }: { status: DocStatus; label: string }) {
  return <span className={`tag status-${DOC_STATUS[status]}`}>{label}</span>;
}

export const FIELD_STATUS: Record<FieldStatus, string> = {
  confirmed: "Vérifié",
  estimated: "Estimé",
  missing: "Manquant",
  inconsistent: "Incohérent",
};
