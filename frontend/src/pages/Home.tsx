import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api";
import { ActivityChart } from "../components/charts/ActivityChart";
import { RatioChart } from "../components/charts/RatioChart";
import { TreasuryChart } from "../components/charts/TreasuryChart";
import { Breakdown, formatValue, KpiDetail, KpiTile, SeverityBadge } from "../components/finance-ui";
import { Alert as Notice, PageHeader } from "../components/ui";
import { financeApi } from "../finance";
import type { Kpi, Overview, SeriesPoint, Treasury } from "../finance";
import { dateFr, eur } from "../format";
import { useSession } from "../session";

const TREND: Record<string, keyof SeriesPoint> = {
  revenue: "revenue",
  ebe: "ebe",
  food_cost: "food_cost_pct",
  drinks_cost: "drinks_cost_pct",
  payroll: "payroll_pct",
};

export function Home() {
  const { user, company, hasModule } = useSession();
  if (!user) return null;
  const firstName = user.full_name.split(" ")[0];

  if (!company) {
    return (
      <>
        <PageHeader title={`Bonjour ${firstName}`} />
        <section className="card empty">
          <h2>Aucune entreprise ne vous est rattachée</h2>
          <p className="muted">Demandez à l'administrateur du boîtier de vous donner accès à une entreprise.</p>
        </section>
      </>
    );
  }
  if (!hasModule("finance")) {
    return (
      <>
        <PageHeader title={`Bonjour ${firstName}`} lead={company.name} />
        <section className="card empty">
          <h2>Activez le module « Gestion financière »</h2>
          <p className="muted">
            Le tableau de bord s'appuie sur ce module. Il s'active dans{" "}
            <Link to="/parametres/entreprise">Entreprise et modules</Link>.
          </p>
        </section>
      </>
    );
  }
  return <Dashboard companyId={company.id} companyName={company.name} firstName={firstName} />;
}

function Dashboard({ companyId, companyName, firstName }: { companyId: string; companyName: string; firstName: string }) {
  const [params, setParams] = useSearchParams();
  const month = params.get("mois") ?? undefined;
  const [data, setData] = useState<Overview | null>(null);
  const [treasury, setTreasury] = useState<Treasury | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Kpi | null>(null);

  const load = useCallback(() => {
    setError(null);
    financeApi.overview(companyId, month).then(setData, (e) => setError(errorMessage(e)));
    financeApi.treasury(companyId).then(setTreasury, () => setTreasury(null));
  }, [companyId, month]);
  useEffect(load, [load]);

  const selectMonth = (value: string) => setParams(value ? { mois: value } : {}, { replace: true });

  if (error) return <Notice>{error}</Notice>;
  if (!data) {
    return (
      <div className="skeleton-page" aria-busy="true">
        <PageHeader title={`Bonjour ${firstName}`} lead="Analyse en cours…" />
        <div className="kpis">{Array.from({ length: 6 }, (_, i) => <div key={i} className="kpi skeleton" />)}</div>
      </div>
    );
  }
  if (data.empty) return <Onboarding firstName={firstName} companyName={companyName} />;

  const complete = data.series.filter((p) => !p.partial);
  const highlight = complete.findIndex((p) => p.month === data.month);

  return (
    <>
      <PageHeader
        title={`Bonjour ${firstName}`}
        lead={`${companyName} — voici l'essentiel de ${data.month_label}.`}
        action={
          <label className="month-select">
            <span className="sr-only">Mois analysé</span>
            <select value={data.month} onChange={(e) => selectMonth(e.target.value)}>
              {data.months.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label.charAt(0).toUpperCase() + m.label.slice(1)}
                </option>
              ))}
            </select>
          </label>
        }
      />

      {data.alerts.open > 0 && (
        <Link to="/alertes" className={`alert-strip${data.alerts.high ? " high" : ""}`}>
          <span className="strip-count">{data.alerts.open}</span>
          <span>
            <strong>
              {data.alerts.open} point{data.alerts.open > 1 ? "s" : ""} d'attention
              {data.alerts.high ? `, dont ${data.alerts.high} prioritaire${data.alerts.high > 1 ? "s" : ""}` : ""}
            </strong>
            <span className="muted"> — chacun est justifié par ses documents et son calcul</span>
          </span>
          <span className="strip-go" aria-hidden="true">→</span>
        </Link>
      )}

      <div className="kpis">
        {data.kpis.map((kpi) => (
          <KpiTile
            key={kpi.key}
            kpi={kpi}
            trend={complete.map((p) => (TREND[kpi.key] ? (p[TREND[kpi.key]] as number | null) : null))}
            highlight={highlight}
            onOpen={() => setDetail(kpi)}
          />
        ))}
        {data.treasury.available && (
          <Link to="/tresorerie" className="kpi">
            <span className="kpi-label">Trésorerie</span>
            <span className="kpi-value">{eur(data.treasury.balance)}</span>
            <span className="kpi-foot">
              <span className="muted small">au {dateFr(data.treasury.as_of)}</span>
            </span>
            {data.treasury.low_point && (
              <span className="kpi-secondary">
                Point bas prévu :{" "}
                <strong className={data.treasury.low_point.balance < (data.treasury.threshold ?? 0) ? "text-bad" : ""}>
                  {eur(data.treasury.low_point.balance)}
                </strong>{" "}
                le {dateFr(data.treasury.low_point.date, "day")}
              </span>
            )}
            <span className="kpi-how">
              <span className="kpi-link">Voir la prévision à 90 jours</span>
            </span>
          </Link>
        )}
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Activité sur 12 mois</h2>
            <p className="muted small">Cliquez sur un mois pour l'analyser. Le mois en cours apparaît en clair.</p>
          </div>
        </div>
        <ActivityChart points={data.series} selected={data.month} onSelect={selectMonth} />
      </section>

      <div className="grid-main">
        <section className="card">
          <div className="card-head">
            <h2>Priorités</h2>
            <Link to="/alertes" className="btn ghost">
              Tout voir
            </Link>
          </div>
          {data.alerts.top.length === 0 ? (
            <p className="muted">Aucun point d'attention : tout est en ordre.</p>
          ) : (
            <ol className="priorities">
              {data.alerts.top.map((a) => (
                <li key={a.fingerprint}>
                  <Link to={`/alertes#${encodeURIComponent(a.fingerprint)}`}>
                    <SeverityBadge severity={a.severity} />
                    <span className="prio-title">{a.title}</span>
                    {a.impact?.amount ? (
                      <span className="prio-impact">
                        {eur(a.impact.amount)} <span className="muted">{a.impact.label}</span>
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </section>
        <section className="card">
          <div className="card-head">
            <h2>Trésorerie à 90 jours</h2>
            <Link to="/tresorerie" className="btn ghost">
              Détail
            </Link>
          </div>
          {treasury?.available ? (
            <TreasuryChart data={treasury} height={220} historyDays={45} />
          ) : (
            <p className="muted">{data.treasury.reason ?? "Chargement…"}</p>
          )}
        </section>
      </div>

      <div className="grid-main">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Où va l'argent en {data.month_label}</h2>
              <p className="muted small">Comparé à la moyenne des trois mois précédents.</p>
            </div>
          </div>
          <Breakdown rows={data.breakdown.slice(0, 10)} month={data.month} />
        </section>
        {data.is_restaurant && (
          <section className="card">
            <div className="card-head">
              <div>
                <h2>Coût matière cuisine</h2>
                <p className="muted small">Achats alimentaires rapportés au CA nourriture, mois par mois.</p>
              </div>
            </div>
            <RatioChart
              points={data.series.map((p) => ({ month: p.month, label: p.label, value: p.food_cost_pct, partial: p.partial }))}
              label="Coût matière cuisine"
              selected={data.month}
            />
            <table className="mini-table">
              <tbody>
                {data.kpis
                  .filter((k) => ["food_cost", "drinks_cost", "payroll"].includes(k.key))
                  .map((k) => (
                    <tr key={k.key}>
                      <td>{k.label}</td>
                      <td className="num">{formatValue(k.value, k.unit)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </section>
        )}
      </div>

      <p className="muted small footnote">
        Calculé sur le boîtier en {data.computed_in_ms} ms, sans aucune connexion extérieure. Chaque chiffre est
        cliquable pour afficher sa formule et ses sources.
      </p>
      {detail && <KpiDetail kpi={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function Onboarding({ firstName, companyName }: { firstName: string; companyName: string }) {
  const steps = [
    { title: "Vos factures", text: "Fournisseurs et clients, en PDF ou en photo. Elles sont lues et vérifiées sur le boîtier." },
    { title: "Votre relevé bancaire", text: "Export CSV de votre banque : il donne la trésorerie et confirme les paiements." },
    { title: "Vos ventes", text: "Journal de caisse ou export de votre logiciel de facturation, au format CSV." },
  ];
  return (
    <>
      <PageHeader title={`Bienvenue ${firstName}`} lead={companyName} />
      <section className="card onboarding">
        <h2>Trois imports suffisent pour obtenir un premier diagnostic</h2>
        <ol className="onboarding-steps">
          {steps.map((s, i) => (
            <li key={s.title}>
              <span className="step-index">{i + 1}</span>
              <span>
                <strong>{s.title}</strong>
                <span className="muted module-text">{s.text}</span>
              </span>
            </li>
          ))}
        </ol>
        <div>
          <Link to="/donnees" className="btn primary">
            Importer mes données
          </Link>
        </div>
      </section>
    </>
  );
}
