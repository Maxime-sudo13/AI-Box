import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime } from "../api";
import type { AuditEvent } from "../api";
import { Alert, PageHeader } from "../components/ui";

const PAGE_SIZE = 50;

const ACTIONS: Record<string, string> = {
  "setup.complete": "Installation du boîtier",
  "auth.login": "Connexion",
  "auth.logout": "Déconnexion",
  "auth.password_change": "Changement de mot de passe",
  "user.create": "Création d'un utilisateur",
  "user.update": "Modification d'un utilisateur",
  "company.create": "Création d'une entreprise",
  "company.update": "Modification d'une entreprise",
  "company.modules": "Modification des modules",
  "access.admin": "Accès à l'administration",
  "access.company": "Modification d'une entreprise",
};

const OUTCOMES: Record<AuditEvent["outcome"], { label: string; className: string }> = {
  success: { label: "Réussi", className: "tag ok" },
  failure: { label: "Échec", className: "tag danger" },
  denied: { label: "Refusé", className: "tag danger" },
};

export function Audit() {
  const [page, setPage] = useState(0);
  const [data, setData] = useState<{ items: AuditEvent[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.audit(PAGE_SIZE, page * PAGE_SIZE).then(setData, (e) => setError(errorMessage(e)));
  }, [page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="Journal d'activité"
        lead="Toutes les opérations sensibles sont enregistrées ici, y compris les tentatives refusées."
      />
      {error && <Alert>{error}</Alert>}
      <section className="card flush">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Opération</th>
                <th>Résultat</th>
                <th>Auteur</th>
                <th>Adresse</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((event) => (
                <tr key={event.id}>
                  <td className="nowrap" data-label="Date">
                    {formatDateTime(event.occurred_at)}
                  </td>
                  <td data-label="Opération">
                    {ACTIONS[event.action] ?? event.action}
                    {event.target && <div className="muted">{event.target}</div>}
                  </td>
                  <td data-label="Résultat">
                    <span className={OUTCOMES[event.outcome].className}>
                      {OUTCOMES[event.outcome].label}
                    </span>
                  </td>
                  <td data-label="Auteur">{event.actor_label ?? "—"}</td>
                  <td className="nowrap muted" data-label="Adresse">
                    {event.ip ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {pages > 1 && (
        <nav className="pager" aria-label="Pagination">
          <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Plus récent
          </button>
          <span className="muted">
            Page {page + 1} sur {pages}
          </span>
          <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
            Plus ancien
          </button>
        </nav>
      )}
    </>
  );
}
