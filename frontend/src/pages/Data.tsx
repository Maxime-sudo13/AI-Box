import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api";
import { DocStatusBadge } from "../components/finance-ui";
import { Alert as Notice, PageHeader } from "../components/ui";
import { Uploader } from "../components/Uploader";
import { financeApi } from "../finance";
import type { Category, DataImport, DataSummary, DocStatus, DocumentItem, Transaction } from "../finance";
import { dateFr, eur, monthShort, num } from "../format";
import { useSession } from "../session";

type Tab = "factures" | "banque" | "imports";
const PAGE = 50;

const STATUS_FILTERS: { key: string; label: string; statuses: DocStatus[] }[] = [
  { key: "", label: "Tous", statuses: [] },
  { key: "to_review,failed", label: "À vérifier", statuses: ["to_review", "failed"] },
  { key: "verified,validated", label: "Vérifiés", statuses: ["verified", "validated"] },
  { key: "duplicate,ignored", label: "Écartés", statuses: ["duplicate", "ignored"] },
];

export function Data() {
  const { company, canEditData, hasModule } = useSession();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "factures";
  const [summary, setSummary] = useState<DataSummary | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [version, setVersion] = useState(0);

  const refresh = useCallback(() => {
    if (!company) return;
    financeApi.summary(company.id).then(setSummary, () => {});
    setVersion((v) => v + 1);
  }, [company]);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    financeApi.categories().then(setCategories, () => {});
  }, []);

  if (!company) return null;
  const setTab = (next: Tab) => setParams({ tab: next });
  const toReview = (summary?.documents.by_status.to_review ?? 0) + (summary?.documents.by_status.failed ?? 0);

  return (
    <>
      <PageHeader
        title="Données"
        lead="Tout ce que le boîtier connaît de l'entreprise, d'où cela vient, et ce qui reste à vérifier."
      />
      {summary && (
        <div className="data-cards">
          <div className="data-card">
            <span className="muted small">Factures</span>
            <strong>{num(summary.documents.total)}</strong>
            <span className="small">
              {summary.invoices.first ? `du ${dateFr(summary.invoices.first)} au ${dateFr(summary.invoices.last)}` : "aucune"}
            </span>
            {toReview > 0 && (
              <button className="link small" onClick={() => setParams({ tab: "factures", status: "to_review,failed" })}>
                {toReview} à vérifier
              </button>
            )}
          </div>
          <div className="data-card">
            <span className="muted small">Relevé bancaire</span>
            <strong>{num(summary.bank.count)} opérations</strong>
            <span className="small">{summary.bank.last ? `jusqu'au ${dateFr(summary.bank.last)}` : "non importé"}</span>
          </div>
          <div className="data-card">
            <span className="muted small">Journal de caisse</span>
            <strong>{num(summary.sales.days)} journées</strong>
            <span className="small">{summary.sales.last ? `jusqu'au ${dateFr(summary.sales.last)}` : "non importé"}</span>
          </div>
          <div className="data-card">
            <span className="muted small">Tiers reconnus</span>
            <strong>{summary.parties.suppliers} fournisseurs</strong>
            <span className="small">{summary.parties.customers} clients</span>
          </div>
        </div>
      )}
      {summary && summary.warnings.length > 0 && (
        <ul className="warnings">
          {summary.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {canEditData && hasModule("documents") && <Uploader companyId={company.id} onDone={refresh} />}

      <div className="segmented" role="tablist" aria-label="Type de données">
        {(
          [
            ["factures", "Factures"],
            ["banque", "Banque"],
            ["imports", "Historique des imports"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "factures" && <Invoices companyId={company.id} categories={categories} version={version} />}
      {tab === "banque" && <Bank companyId={company.id} categories={categories} canEdit={canEditData} version={version} />}
      {tab === "imports" && <Imports companyId={company.id} version={version} />}
    </>
  );
}

function Filters({ categories, children }: { categories: Category[]; children?: React.ReactNode }) {
  const [params, setParams] = useSearchParams();
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };
  return (
    <div className="filters">
      {children}
      <input
        type="search"
        placeholder="Rechercher…"
        aria-label="Rechercher"
        defaultValue={params.get("q") ?? ""}
        onChange={(e) => set("q", e.target.value)}
      />
      <select aria-label="Catégorie" value={params.get("category") ?? ""} onChange={(e) => set("category", e.target.value)}>
        <option value="">Toutes catégories</option>
        {categories.map((c) => (
          <option key={c.key} value={c.key}>
            {c.label}
          </option>
        ))}
      </select>
      <input type="month" aria-label="Mois" value={params.get("month") ?? ""} onChange={(e) => set("month", e.target.value)} />
    </div>
  );
}

function Pager({ total }: { total: number }) {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 0);
  const pages = Math.max(1, Math.ceil(total / PAGE));
  if (pages <= 1) return null;
  const go = (p: number) => {
    const next = new URLSearchParams(params);
    next.set("page", String(p));
    setParams(next, { replace: true });
  };
  return (
    <nav className="pager" aria-label="Pagination">
      <button className="btn" disabled={page === 0} onClick={() => go(page - 1)}>
        Précédent
      </button>
      <span className="muted">
        Page {page + 1} sur {pages} · {num(total)} éléments
      </span>
      <button className="btn" disabled={page + 1 >= pages} onClick={() => go(page + 1)}>
        Suivant
      </button>
    </nav>
  );
}

function Invoices({ companyId, categories, version }: { companyId: string; categories: Category[]; version: number }) {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<{ items: DocumentItem[]; total: number; counts: Partial<Record<DocStatus, number>> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const status = params.get("status") ?? "";
  const query = {
    status,
    q: params.get("q") ?? "",
    category: params.get("category") ?? "",
    month: params.get("month") ?? "",
    limit: PAGE,
    offset: Number(params.get("page") ?? 0) * PAGE,
  };
  const key = JSON.stringify(query);
  useEffect(() => {
    financeApi.documents(companyId, JSON.parse(key)).then(setData, (e) => setError(errorMessage(e)));
  }, [companyId, key, version]);

  const count = (statuses: DocStatus[]) =>
    statuses.length === 0
      ? Object.values(data?.counts ?? {}).reduce((s, n) => s + (n ?? 0), 0)
      : statuses.reduce((s, st) => s + (data?.counts[st] ?? 0), 0);

  return (
    <section className="card flush">
      <Filters categories={categories}>
        <div className="chips" role="group" aria-label="Statut">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              className={`chip${status === f.key ? " on" : ""}`}
              onClick={() => {
                const next = new URLSearchParams(params);
                if (f.key) next.set("status", f.key);
                else next.delete("status");
                next.delete("page");
                setParams(next, { replace: true });
              }}
            >
              {f.label} <span className="chip-count">{count(f.statuses)}</span>
            </button>
          ))}
        </div>
      </Filters>
      {error && <Notice>{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Tiers</th>
              <th>Catégorie</th>
              <th className="num">Montant TTC</th>
              <th>Statut</th>
              <th>Paiement</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((d) => (
              <tr key={d.id} className="clickable">
                <td className="nowrap" data-label="Date">
                  {dateFr(d.invoice?.issue_date)}
                </td>
                <td data-label="Tiers">
                  <Link to={`/donnees/documents/${d.id}`} className="row-link">
                    {d.invoice?.party ?? d.filename}
                  </Link>
                  <div className="muted small">
                    {d.invoice?.direction === "sale" ? "Vente · " : ""}
                    {d.invoice?.number ? `n° ${d.invoice.number}` : d.filename}
                    {d.method === "ocr" ? " · lu par OCR" : ""}
                  </div>
                </td>
                <td data-label="Catégorie">{d.invoice?.category_label ?? "—"}</td>
                <td className="num nowrap" data-label="Montant TTC">
                  {eur(d.invoice?.total_ttc, 2)}
                </td>
                <td data-label="Statut">
                  <DocStatusBadge status={d.status} label={d.status_label} />
                </td>
                <td className="nowrap" data-label="Paiement">
                  {d.invoice?.paid_on ? (
                    <span className="text-good">✓ {dateFr(d.invoice.paid_on)}</span>
                  ) : d.invoice?.due_date && ["verified", "validated", "to_review"].includes(d.status) ? (
                    <span className="muted">Échéance {dateFr(d.invoice.due_date)}</span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="muted empty-row">Aucun document ne correspond.</p>}
      </div>
      {data && <Pager total={data.total} />}
    </section>
  );
}

function Bank({ companyId, categories, canEdit, version }: { companyId: string; categories: Category[]; canEdit: boolean; version: number }) {
  const [params] = useSearchParams();
  const [data, setData] = useState<{ items: Transaction[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = {
    q: params.get("q") ?? "",
    category: params.get("category") ?? "",
    month: params.get("month") ?? "",
    limit: PAGE,
    offset: Number(params.get("page") ?? 0) * PAGE,
  };
  const key = JSON.stringify(query);
  const load = useCallback(() => {
    financeApi.transactions(companyId, JSON.parse(key)).then(setData, (e) => setError(errorMessage(e)));
  }, [companyId, key]);
  useEffect(load, [load, version]);

  async function recategorize(t: Transaction, category: string) {
    try {
      await financeApi.categorizeTransaction(companyId, t.id, category);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <section className="card flush">
      <Filters categories={categories} />
      {error && <Notice>{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Libellé</th>
              <th>Catégorie</th>
              <th className="num">Montant</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((t) => (
              <tr key={t.id}>
                <td className="nowrap" data-label="Date">
                  {dateFr(t.date)}
                </td>
                <td data-label="Libellé">
                  {t.label}
                  <div className="muted small">
                    {t.party ?? ""}
                    {t.document_id && (
                      <>
                        {t.party ? " · " : ""}
                        <Link to={`/donnees/documents/${t.document_id}`}>facture rapprochée</Link>
                      </>
                    )}
                  </div>
                </td>
                <td data-label="Catégorie">
                  {canEdit ? (
                    <select
                      className={`inline-select${t.category === "a_classer" ? " attention" : ""}`}
                      aria-label={`Catégorie de ${t.label}`}
                      value={t.category}
                      onChange={(e) => void recategorize(t, e.target.value)}
                    >
                      {categories.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    t.category_label
                  )}
                </td>
                <td className={`num nowrap ${t.amount > 0 ? "text-good" : ""}`} data-label="Montant">
                  {t.amount > 0 ? "+" : ""}
                  {eur(t.amount, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="muted empty-row">Aucune opération ne correspond.</p>}
      </div>
      {data && <Pager total={data.total} />}
    </section>
  );
}

function Imports({ companyId, version }: { companyId: string; version: number }) {
  const [items, setItems] = useState<DataImport[] | null>(null);
  useEffect(() => {
    financeApi.imports(companyId).then(setItems, () => setItems([]));
  }, [companyId, version]);
  return (
    <section className="card flush">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date d'import</th>
              <th>Fichier</th>
              <th>Période couverte</th>
              <th className="num">Lignes ajoutées</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((i) => (
              <tr key={i.id}>
                <td className="nowrap" data-label="Date d'import">
                  {dateFr(i.imported_at)}
                </td>
                <td data-label="Fichier">
                  {i.filename}
                  <div className="muted small">{i.kind === "bank" ? "Relevé bancaire" : "Journal de caisse"}</div>
                  {i.warnings.map((w) => (
                    <div key={w} className="small text-warn">
                      {w}
                    </div>
                  ))}
                </td>
                <td className="nowrap" data-label="Période">
                  {i.period_start ? `${monthShort(i.period_start.slice(0, 7))} → ${monthShort((i.period_end ?? "").slice(0, 7))}` : "—"}
                </td>
                <td className="num" data-label="Lignes ajoutées">
                  {num(i.rows_added)} / {num(i.rows_total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items && items.length === 0 && <p className="muted empty-row">Aucun import CSV pour l'instant.</p>}
      </div>
    </section>
  );
}
