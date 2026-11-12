import { request } from "./api";

export type Quality = "confirmed" | "estimated" | "partial" | "missing";

export interface KpiInput {
  label: string;
  value: number | null;
  unit: string;
  source: string;
  count: number | null;
  link: { month?: string; category?: string } | null;
}

export interface Kpi {
  key: string;
  label: string;
  unit: "eur" | "pct" | "count";
  value: number | null;
  previous: number | null;
  change: number | null;
  change_pct: number | null;
  good_direction: "up" | "down";
  formula: string;
  inputs: KpiInput[];
  quality: Quality;
  notes: string[];
  period: string;
  secondary?: { label: string; value: number | null; unit: string; change_pct?: number | null };
}

export interface SeriesPoint {
  month: string;
  label: string;
  partial: boolean;
  revenue: number | null;
  matieres: number | null;
  externes: number | null;
  personnel: number | null;
  ebe: number | null;
  ebe_pct: number | null;
  food_cost_pct: number | null;
  drinks_cost_pct: number | null;
  payroll_pct: number | null;
  covers: number | null;
}

export interface BreakdownRow {
  category: string;
  label: string;
  group: string;
  group_label: string;
  amount: number;
  share_of_revenue: number | null;
  average_3m: number | null;
  change_vs_average_pct: number | null;
  invoices: number;
  bank: number;
}

export interface AlertRef {
  invoice_id: string;
  document_id: string;
  number: string | null;
  party: string;
  date: string | null;
  amount: number | null;
}

export interface Alert {
  fingerprint: string;
  kind: string;
  severity: "high" | "medium" | "low";
  title: string;
  summary: string;
  details: string[];
  impact: { amount: number | null; label: string; formula: string } | null;
  figures: { label: string; value: number | null; unit: string }[];
  invoices: AlertRef[];
  transactions: { id: number; date: string; label: string; amount: number }[];
  series?: { date: string; value: number }[];
  module: string;
  status: "open" | "acknowledged" | "resolved" | "dismissed";
  review_note: string | null;
  reviewed_at: string | null;
  action?: string;
  proposals?: { action_type: string; title: string; needs_recipient: boolean }[];
  actions?: { id: string; title: string; status: string; status_label: string; risk_level: number }[];
}

export interface TreasurySummary {
  available: boolean;
  reason?: string;
  as_of?: string;
  balance?: number;
  threshold?: number;
  low_point?: { date: string; balance: number };
  end_balance?: number;
}

export interface Treasury extends TreasurySummary {
  horizon_days: number;
  threshold_formula: string;
  history: { date: string; balance: number }[];
  forecast: { date: string; balance: number; inflow: number; outflow: number }[];
  components: {
    key: string;
    label: string;
    amount: number;
    certainty: "known" | "estimated";
    detail: string;
    suppliers?: { party: string; monthly: number; delay_days: number }[];
    count?: number;
  }[];
  events: { date: string; label: string; amount: number; kind: string; certainty: string; document_id?: string }[];
  notes: string[];
  risky_receivables: { document_id: string; number: string; party: string; amount: number; overdue_days: number }[];
}

export interface Overview {
  empty: boolean;
  month: string;
  month_label: string;
  months: { value: string; label: string }[];
  is_restaurant: boolean;
  kpis: Kpi[];
  series: SeriesPoint[];
  breakdown: BreakdownRow[];
  treasury: TreasurySummary;
  alerts: { open: number; high: number; impact: number | null; top: Alert[] };
  computed_in_ms: number;
}

export type DocStatus = "verified" | "to_review" | "validated" | "duplicate" | "ignored" | "failed";
export type FieldStatus = "confirmed" | "estimated" | "missing" | "inconsistent";

export interface InvoiceSummary {
  id: string;
  direction: "purchase" | "sale";
  party: string | null;
  party_id: string | null;
  number: string | null;
  issue_date: string | null;
  due_date: string | null;
  total_ht: number | null;
  total_tva: number | null;
  total_ttc: number | null;
  category: string | null;
  category_label: string | null;
  paid_on: string | null;
  issues: string[];
  field_status: Record<string, FieldStatus>;
}

export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  status: DocStatus;
  status_label: string;
  uploaded_at: string;
  method: "text" | "ocr" | "none" | null;
  error: string | null;
  duplicate_of_id: string | null;
  invoice: InvoiceSummary | null;
}

export interface DocumentDetail extends DocumentItem {
  extraction: { method?: string; pages?: number; duration_ms?: number };
  invoice:
    | (InvoiceSummary & {
        lines: { description: string; quantity: number | null; unit: string | null; unit_price: number | null; vat_rate: number | null; total_ht: number | null }[];
        vat_breakdown: { rate: string; base?: string; amount: string }[];
        payment: { date: string; label: string; amount: number } | null;
      })
    | null;
  duplicate_of?: { id: string; filename: string } | null;
  next_to_review: string | null;
}

export interface DataImport {
  id: string;
  kind: "bank" | "sales";
  filename: string;
  rows_total: number;
  rows_added: number;
  rows_skipped: number;
  period_start: string | null;
  period_end: string | null;
  warnings: string[];
  imported_at: string;
}

export interface Transaction {
  id: number;
  date: string;
  label: string;
  amount: number;
  balance: number | null;
  category: string;
  category_label: string;
  category_source: string;
  party: string | null;
  document_id: string | null;
}

export interface DataSummary {
  documents: { total: number; by_status: Partial<Record<DocStatus, number>> };
  invoices: { first: string | null; last: string | null };
  bank: { count: number; first: string | null; last: string | null; to_classify: number };
  sales: { days: number; first: string | null; last: string | null };
  parties: { suppliers: number; customers: number };
  warnings: string[];
}

export interface Category {
  key: string;
  label: string;
  group: string;
}

function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<T>("POST", path, form);
}

const base = (companyId: string) => `/companies/${companyId}`;

export const financeApi = {
  overview: (c: string, month?: string) =>
    request<Overview>("GET", `${base(c)}/finance/overview${month ? `?month=${month}` : ""}`),
  treasury: (c: string) => request<Treasury>("GET", `${base(c)}/finance/treasury`),
  alerts: (c: string) => request<{ items: Alert[]; computed_in_ms: number }>("GET", `${base(c)}/finance/alerts`),
  reviewAlert: (c: string, fingerprint: string, status: Alert["status"], note?: string) =>
    request<void>("POST", `${base(c)}/finance/alerts/review`, { fingerprint, status, note: note || null }),
  summary: (c: string) => request<DataSummary>("GET", `${base(c)}/data/summary`),
  categories: () => request<Category[]>("GET", "/categories"),

  documents: (c: string, params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") query.set(k, String(v));
    return request<{ items: DocumentItem[]; total: number; counts: Partial<Record<DocStatus, number>> }>(
      "GET",
      `${base(c)}/documents?${query}`,
    );
  },
  document: (c: string, id: string) => request<DocumentDetail>("GET", `${base(c)}/documents/${id}`),
  documentFileUrl: (c: string, id: string) => `/api${base(c)}/documents/${id}/file`,
  documentPreviewUrl: (c: string, id: string, page: number) => `/api${base(c)}/documents/${id}/preview/${page}`,
  uploadDocument: (c: string, file: File) => upload<DocumentItem>(`${base(c)}/documents`, file),
  updateInvoice: (c: string, id: string, body: Record<string, unknown>) =>
    request<DocumentDetail>("PATCH", `${base(c)}/documents/${id}/invoice`, body),
  documentAction: (c: string, id: string, action: "ignore" | "restore" | "not_duplicate") =>
    request<DocumentItem>("POST", `${base(c)}/documents/${id}/status`, { action }),
  parties: (c: string, kind?: "supplier" | "customer") =>
    request<{ id: string; name: string; kind: string; category: string | null }[]>(
      "GET",
      `${base(c)}/parties${kind ? `?kind=${kind}` : ""}`,
    ),

  imports: (c: string) => request<DataImport[]>("GET", `${base(c)}/imports`),
  importFile: (c: string, kind: "bank" | "sales", file: File) => upload<DataImport>(`${base(c)}/imports/${kind}`, file),
  transactions: (c: string, params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") query.set(k, String(v));
    return request<{ items: Transaction[]; total: number }>("GET", `${base(c)}/bank-transactions?${query}`);
  },
  categorizeTransaction: (c: string, id: number, category: string) =>
    request<void>("PATCH", `${base(c)}/bank-transactions/${id}`, { category }),
};
