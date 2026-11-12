import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api";
import { TreasuryChart } from "../components/charts/TreasuryChart";
import { Alert as Notice, PageHeader } from "../components/ui";
import { financeApi } from "../finance";
import type { Treasury as TreasuryData } from "../finance";
import { dateFr, eur } from "../format";
import { useSession } from "../session";

export function Treasury() {
  const { company } = useSession();
  const [data, setData] = useState<TreasuryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (company) financeApi.treasury(company.id).then(setData, (e) => setError(errorMessage(e)));
  }, [company]);

  if (error) return <Notice>{error}</Notice>;
  if (!data) return <PageHeader title="Trésorerie" lead="Calcul en cours…" />;
  if (!data.available) {
    return (
      <>
        <PageHeader title="Trésorerie" />
        <section className="card empty">
          <p className="muted">{data.reason}</p>
          <div>
            <Link to="/donnees" className="btn primary">
              Importer un relevé
            </Link>
          </div>
        </section>
      </>
    );
  }
  const below = data.low_point && data.threshold !== undefined && data.low_point.balance < data.threshold;
  const events = showAll ? data.events : data.events.filter((e) => Math.abs(e.amount) >= 500).slice(0, 14);

  return (
    <>
      <PageHeader
        title="Trésorerie"
        lead={`Solde au ${dateFr(data.as_of, "long")}, d'après le dernier relevé bancaire importé, et prévision sur ${data.horizon_days} jours.`}
      />
      <div className="kpis three">
        <div className="kpi static">
          <span className="kpi-label">Solde actuel</span>
          <span className="kpi-value">{eur(data.balance)}</span>
          <span className="muted small">au {dateFr(data.as_of)}</span>
        </div>
        <div className={`kpi static${below ? " warn" : ""}`}>
          <span className="kpi-label">Point bas prévu</span>
          <span className="kpi-value">{eur(data.low_point?.balance)}</span>
          <span className="muted small">
            le {dateFr(data.low_point?.date, "long")}
            {below ? " · sous le seuil de vigilance" : ""}
          </span>
        </div>
        <div className="kpi static">
          <span className="kpi-label">Solde prévu dans {data.horizon_days} jours</span>
          <span className="kpi-value">{eur(data.end_balance)}</span>
          <span className="muted small">seuil de vigilance : {eur(data.threshold)}</span>
        </div>
      </div>

      <section className="card">
        <TreasuryChart data={data} height={320} historyDays={120} />
        <p className="muted small">Seuil de vigilance : {data.threshold_formula}.</p>
      </section>

      <div className="grid-main">
        <section className="card">
          <h2>Comment la prévision est construite</h2>
          <table className="inputs">
            <tbody>
              {data.components.map((c) => (
                <tr key={c.key}>
                  <td>
                    {c.label}
                    <span className={`tag ${c.certainty === "known" ? "status-ok" : ""}`}>{c.certainty === "known" ? "Connu" : "Estimé"}</span>
                    <div className="muted small">{c.detail}</div>
                    {c.suppliers && c.suppliers.length > 0 && (
                      <details className="small">
                        <summary>{c.suppliers.length} fournisseurs réguliers</summary>
                        <ul className="plain">
                          {c.suppliers.map((s) => (
                            <li key={s.party}>
                              {s.party} : ≈ {eur(s.monthly)} par mois, payé à {s.delay_days} jours
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </td>
                  <td className="num">{eur(c.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Variation prévue sur {data.horizon_days} jours</td>
                <td className="num">{eur((data.end_balance ?? 0) - (data.balance ?? 0))}</td>
              </tr>
            </tfoot>
          </table>
          {data.notes.length > 0 && (
            <ul className="notes">
              {data.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <div className="card-head">
            <h2>Prochaines échéances</h2>
            <button className="btn ghost" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Principales seulement" : `Toutes (${data.events.length})`}
            </button>
          </div>
          <ul className="events">
            {events.map((e, i) => (
              <li key={`${e.date}-${i}`}>
                <span className="ev-date">{dateFr(e.date, "day")}</span>
                <span className="ev-label">
                  {e.document_id ? <Link to={`/donnees/documents/${e.document_id}`}>{e.label}</Link> : e.label}
                  {e.certainty !== "known" && <span className="muted small"> · estimé</span>}
                </span>
                <span className={`num ${e.amount > 0 ? "text-good" : ""}`}>{eur(e.amount)}</span>
              </li>
            ))}
          </ul>
          {data.risky_receivables.length > 0 && (
            <>
              <h3>Créances non comptées</h3>
              <ul className="events">
                {data.risky_receivables.map((r) => (
                  <li key={r.document_id}>
                    <span className="ev-date">{r.overdue_days} j</span>
                    <span className="ev-label">
                      <Link to={`/donnees/documents/${r.document_id}`}>
                        {r.party} ({r.number})
                      </Link>
                    </span>
                    <span className="num">{eur(r.amount)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </>
  );
}
