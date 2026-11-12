export type Role = "owner" | "manager" | "viewer";

export interface Membership {
  company_id: string;
  company_name: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  memberships: Membership[];
}

export interface Company {
  id: string;
  name: string;
  legal_form: string | null;
  siren: string | null;
  sector: string | null;
  enabled_modules: string[];
  created_at: string;
  role: Role | null;
}

export interface CompanyInput {
  name: string;
  legal_form: string | null;
  siren: string | null;
  sector: string | null;
}

export interface Module {
  key: string;
  name: string;
  description: string;
  available: boolean;
}

export interface AuditEvent {
  id: number;
  occurred_at: string;
  actor_label: string | null;
  company_id: string | null;
  action: string;
  outcome: "success" | "denied" | "failure";
  target: string | null;
  details: Record<string, unknown>;
  ip: string | null;
}

export interface UserInput {
  email: string;
  full_name: string;
  password: string;
  is_admin: boolean;
  memberships: { company_id: string; role: Role }[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail: unknown = null,
  ) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;

/** Appelé quand le serveur signale que la session n'est plus valide. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

function describe(status: number, payload: unknown): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) {
    // Erreurs de validation : on garde les messages métier, rédigés en français.
    const messages = detail
      .map((item) => String(item?.msg ?? ""))
      .filter((msg) => msg.startsWith("Value error, "))
      .map((msg) => msg.slice("Value error, ".length));
    if (messages.length) return messages.join(" ");
    return "Certaines informations saisies ne sont pas valides.";
  }
  if (status >= 500) return "Le boîtier a rencontré une erreur. Réessayez dans un instant.";
  return "La demande n'a pas pu aboutir.";
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  const isForm = body instanceof FormData;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body === undefined || isForm ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Le boîtier ne répond pas. Vérifiez votre connexion au réseau local.");
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    // Un 401 sur la tentative de connexion elle-même est une erreur de saisie, pas une
    // session expirée.
    if (response.status === 401 && path !== "/auth/login") onUnauthorized?.();
    throw new ApiError(response.status, describe(response.status, payload), (payload as { detail?: unknown } | null)?.detail);
  }
  return payload as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("GET", "/health"),
  setupStatus: () => request<{ initialized: boolean }>("GET", "/setup/status"),
  setup: (body: {
    admin: { email: string; full_name: string; password: string };
    company: CompanyInput;
    modules: string[];
  }) => request<User>("POST", "/setup", body),

  login: (email: string, password: string) =>
    request<User>("POST", "/auth/login", { email, password }),
  logout: () => request<void>("POST", "/auth/logout"),
  me: () => request<User>("GET", "/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/auth/password", { current_password, new_password }),

  modules: () => request<Module[]>("GET", "/modules"),
  companies: () => request<Company[]>("GET", "/companies"),
  createCompany: (body: CompanyInput) => request<Company>("POST", "/companies", body),
  updateCompany: (id: string, body: Partial<CompanyInput>) =>
    request<Company>("PATCH", `/companies/${id}`, body),
  setModules: (id: string, modules: string[]) =>
    request<Company>("PUT", `/companies/${id}/modules`, { modules }),

  users: () => request<User[]>("GET", "/users"),
  createUser: (body: UserInput) => request<User>("POST", "/users", body),
  updateUser: (id: string, body: Partial<Omit<UserInput, "email">> & { is_active?: boolean }) =>
    request<User>("PATCH", `/users/${id}`, body),

  audit: (limit: number, offset: number) =>
    request<{ items: AuditEvent[]; total: number }>(
      "GET",
      `/audit?limit=${limit}&offset=${offset}`,
    ),
};

export const PASSWORD_MIN_LENGTH = 12;

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Dirigeant",
  manager: "Gestionnaire",
  viewer: "Lecture seule",
};

export const LEGAL_FORMS = ["EI", "EURL", "SARL", "SASU", "SAS", "SA", "SNC", "SCI", "Association"];

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Une erreur inattendue est survenue.";
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(iso),
  );
}
