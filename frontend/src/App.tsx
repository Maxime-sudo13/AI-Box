import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Brand } from "./components/ui";
import { Account } from "./pages/Account";
import { Alerts } from "./pages/Alerts";
import { Audit } from "./pages/Audit";
import { CompanySettings } from "./pages/CompanySettings";
import { Data } from "./pages/Data";
import { DocumentReview } from "./pages/DocumentReview";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Setup } from "./pages/Setup";
import { Treasury } from "./pages/Treasury";
import { Users } from "./pages/Users";
import { useSession } from "./session";

export function App() {
  const { phase, user, retry } = useSession();

  if (phase === "loading") {
    return (
      <main className="gate" aria-busy="true">
        <Brand />
        <p className="muted">Connexion au boîtier…</p>
      </main>
    );
  }
  if (phase === "unreachable") {
    return (
      <main className="gate">
        <Brand />
        <h1>Le boîtier ne répond pas</h1>
        <p className="muted">
          Vérifiez qu'il est allumé et que cet appareil est connecté au réseau de l'entreprise.
        </p>
        <button className="btn primary" onClick={retry}>
          Réessayer
        </button>
      </main>
    );
  }
  if (phase === "setup") return <Setup />;
  if (phase === "anonymous" || !user) return <Login />;

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="alertes" element={<Alerts />} />
        <Route path="tresorerie" element={<Treasury />} />
        <Route path="donnees" element={<Data />} />
        <Route path="donnees/documents/:id" element={<DocumentReview />} />
        <Route path="parametres/entreprise" element={<CompanySettings />} />
        <Route path="parametres/compte" element={<Account />} />
        {user.is_admin && (
          <>
            <Route path="parametres/utilisateurs" element={<Users />} />
            <Route path="parametres/journal" element={<Audit />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
