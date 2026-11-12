import { request } from "./api";

export interface ConnectorField {
  key: string;
  label: string;
  kind: "text" | "password" | "number" | "email";
  secret: boolean;
  required: boolean;
  hint: string | null;
  default: string | number | null;
}

export interface ConnectorPermission {
  key: string;
  label: string;
  write: boolean;
  default: boolean;
}

export interface ConnectorInfo {
  key: string;
  name: string;
  category: string;
  description: string;
  online: boolean;
  hosts: string[];
  data_notice: string;
  disabled_reason: string | null;
  fields: ConnectorField[];
  permissions: ConnectorPermission[];
}

export interface Catalog {
  offline_mode: boolean;
  import_root: string;
  available: ConnectorInfo[];
  planned: { key: string; name: string; category: string; description: string }[];
}

export interface SyncRun {
  id: number;
  trigger: "schedule" | "manual";
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "partial" | "failed";
  stats: Record<string, number | string[]>;
  error: string | null;
}

export interface ConnectionItem {
  id: string;
  connector: string;
  connector_name: string;
  category: string;
  label: string;
  status: "active" | "error" | "expired" | "paused";
  settings: Record<string, string | number>;
  secrets_set: string[];
  permissions: string[];
  interval_minutes: number;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string;
  last_run: SyncRun | null;
  test_message?: string;
}

const base = (c: string) => `/companies/${c}/connections`;

export const connectorsApi = {
  catalog: () => request<Catalog>("GET", "/connectors"),
  list: (c: string) => request<ConnectionItem[]>("GET", base(c)),
  create: (c: string, body: Record<string, unknown>) => request<ConnectionItem>("POST", base(c), body),
  update: (c: string, id: string, body: Record<string, unknown>) => request<ConnectionItem>("PATCH", `${base(c)}/${id}`, body),
  remove: (c: string, id: string) => request<void>("DELETE", `${base(c)}/${id}`),
  sync: (c: string, id: string) => request<{ run: SyncRun; connection: ConnectionItem }>("POST", `${base(c)}/${id}/sync`),
  runs: (c: string, id: string) => request<SyncRun[]>("GET", `${base(c)}/${id}/runs`),
};
