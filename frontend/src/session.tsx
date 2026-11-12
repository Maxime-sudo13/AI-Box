import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, setUnauthorizedHandler } from "./api";
import type { Company, User } from "./api";

type Phase = "loading" | "unreachable" | "setup" | "anonymous" | "ready";

interface SessionState {
  phase: Phase;
  user: User | null;
  companies: Company[];
  company: Company | null;
  /** Peut modifier l'entreprise courante : administrateur du boîtier ou dirigeant. */
  canManageCompany: boolean;
  selectCompany: (id: string) => void;
  signedIn: (user: User) => Promise<void>;
  signOut: () => Promise<void>;
  reloadCompanies: () => Promise<void>;
  retry: () => void;
}

const SessionContext = createContext<SessionState | null>(null);
const COMPANY_KEY = "bab.company";

function storedCompanyId(): string | null {
  try {
    return localStorage.getItem(COMPANY_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<string | null>(storedCompanyId);
  const [attempt, setAttempt] = useState(0);

  const reloadCompanies = useCallback(async () => {
    setCompanies(await api.companies());
  }, []);

  const signedIn = useCallback(
    async (next: User) => {
      setUser(next);
      await reloadCompanies();
      setPhase("ready");
    },
    [reloadCompanies],
  );

  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    (async () => {
      try {
        const { initialized } = await api.setupStatus();
        if (cancelled) return;
        if (!initialized) return setPhase("setup");
        try {
          const me = await api.me();
          if (!cancelled) await signedIn(me);
        } catch (error) {
          if (cancelled) return;
          if (error instanceof ApiError && error.status === 401) setPhase("anonymous");
          else setPhase("unreachable");
        }
      } catch {
        if (!cancelled) setPhase("unreachable");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt, signedIn]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setCompanies([]);
      setPhase((current) => (current === "ready" ? "anonymous" : current));
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setCompanies([]);
      setPhase("anonymous");
    }
  }, []);

  const selectCompany = useCallback((id: string) => {
    setCompanyId(id);
    try {
      localStorage.setItem(COMPANY_KEY, id);
    } catch {
      // Stockage indisponible (navigation privée) : le choix vaut pour la session en cours.
    }
  }, []);

  const value = useMemo<SessionState>(() => {
    const company = companies.find((c) => c.id === companyId) ?? companies[0] ?? null;
    return {
      phase,
      user,
      companies,
      company,
      canManageCompany: Boolean(user && company && (user.is_admin || company.role === "owner")),
      selectCompany,
      signedIn,
      signOut,
      reloadCompanies,
      retry: () => setAttempt((n) => n + 1),
    };
  }, [phase, user, companies, companyId, selectCompany, signedIn, signOut, reloadCompanies]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession doit être utilisé dans SessionProvider");
  return value;
}
