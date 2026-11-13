import { request } from "./api";

export interface Fact {
  id: string;
  label: string;
  value: number | string | null;
  unit: string;
  display: string;
  quality: "confirmed" | "estimated" | "hypothesis";
  source: string;
  link: string | null;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  agents: string[];
  facts: Fact[];
  suggestions: { alert: string; action_type: string; title: string }[];
  generation: {
    writer?: "llm" | "engine";
    model?: string | null;
    note?: string;
    guard?: "passed" | "rejected";
    unverified?: string[];
    misread?: string[];
    routing?: "keywords" | "model";
    duration_ms?: number;
    intents?: string[];
    month?: string;
  };
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: ChatMessage[];
}

export interface AdvisorStatus {
  ai_enabled: boolean;
  model: string | null;
  available: boolean;
  examples: string[];
  agents: { key: string; name: string; mission: string; domains: string[] }[];
}

export type ActionStatus = "pending" | "approved" | "executing" | "done" | "failed" | "rejected" | "cancelled" | "undone";

export interface Action {
  id: string;
  action_type: string;
  type_label: string;
  risk_level: 1 | 2 | 3;
  title: string;
  status: ActionStatus;
  status_label: string;
  proposed_by: string;
  trigger: { alert?: string; kind?: string };
  payload: Record<string, string | null>;
  authorization: {
    mode?: string;
    decision?: string;
    by?: string;
    at?: string;
    reauthenticated_at?: string | null;
    modified_fields?: string[];
    reason?: string | null;
  };
  result: { summary?: string; transport?: string; to?: string; filename?: string; undone_by?: string };
  error: string | null;
  reversible: boolean;
  has_file: boolean;
  created_at: string;
  decided_at: string | null;
  executed_at: string | null;
}

export interface CatalogItem {
  key: string;
  label: string;
  level: 1 | 2 | 3;
  description: string;
  reversible: boolean;
  mode: "forbidden" | "approval" | "automatic";
  allowed_modes: ("forbidden" | "approval" | "automatic")[];
}

const base = (c: string) => `/companies/${c}`;

export const agentsApi = {
  status: (c: string) => request<AdvisorStatus>("GET", `${base(c)}/advisor/status`),
  conversations: (c: string) => request<Conversation[]>("GET", `${base(c)}/advisor/conversations`),
  conversation: (c: string, id: string) => request<Conversation>("GET", `${base(c)}/advisor/conversations/${id}`),
  deleteConversation: (c: string, id: string) => request<void>("DELETE", `${base(c)}/advisor/conversations/${id}`),
  ask: (c: string, question: string, conversationId?: string) =>
    request<Conversation>("POST", `${base(c)}/advisor/ask`, { question, conversation_id: conversationId ?? null }),

  catalog: (c: string) => request<{ can_edit: boolean; items: CatalogItem[] }>("GET", `${base(c)}/actions/catalog`),
  setPolicy: (c: string, action_type: string, mode: string) =>
    request<void>("PUT", `${base(c)}/actions/policies`, { action_type, mode }),
  actions: (c: string, status?: string) =>
    request<{ items: Action[]; counts: Partial<Record<ActionStatus, number>>; can_approve: boolean }>(
      "GET",
      `${base(c)}/actions${status ? `?status=${status}` : ""}`,
    ),
  propose: (c: string, body: { action_type: string; title: string; payload: Record<string, unknown> }) =>
    request<Action>("POST", `${base(c)}/actions`, body),
  fromAlert: (c: string, alert: string, action_type: string) =>
    request<Action>("POST", `${base(c)}/actions/from-alert`, { alert, action_type }),
  approve: (c: string, id: string, body: { overrides?: Record<string, string>; confirmation?: string }) =>
    request<Action>("POST", `${base(c)}/actions/${id}/approve`, body),
  reject: (c: string, id: string, reason?: string) => request<Action>("POST", `${base(c)}/actions/${id}/reject`, { reason: reason || null }),
  undo: (c: string, id: string) => request<Action>("POST", `${base(c)}/actions/${id}/undo`),
  fileUrl: (c: string, id: string) => `/api${base(c)}/actions/${id}/file`,
  reauth: (password: string) => request<void>("POST", "/auth/reauth", { password }),
  tasks: (c: string) =>
    request<{ id: string; title: string; details: string | null; done: boolean; created_at: string }[]>("GET", `${base(c)}/tasks`),
  setTaskDone: (c: string, id: string, done: boolean) => request<void>("PATCH", `${base(c)}/tasks/${id}`, { done }),
  outbox: (c: string) =>
    request<{ id: string; to: string; subject: string; body: string; transport: string; sent_at: string }[]>("GET", `${base(c)}/outbox`),
  emlUrl: (c: string, id: string) => `/api${base(c)}/outbox/${id}.eml`,
};

export const AGENT_NAMES: Record<string, string> = {
  financier: "Agent financier",
  commercial: "Agent commercial",
  achats: "Agent achats",
  administratif: "Agent administratif",
  strategique: "Agent stratégique",
  executif: "Agent exécutif",
};

export const LEVELS: Record<1 | 2 | 3, { label: string; hint: string }> = {
  1: { label: "Niveau 1 · automatique", hint: "Sans conséquence financière ou juridique." },
  2: { label: "Niveau 2 · validation", hint: "Engage l'entreprise auprès d'un tiers." },
  3: { label: "Niveau 3 · validation renforcée", hint: "Opération sensible : mot de passe et confirmation explicite." },
};

export const MODE_LABELS = { forbidden: "Interdit", approval: "Sur validation", automatic: "Automatique" } as const;

export function proposerLabel(proposedBy: string): string {
  if (proposedBy === "user") return "Vous";
  const key = proposedBy.replace("agent:", "");
  return AGENT_NAMES[key] ?? proposedBy;
}
