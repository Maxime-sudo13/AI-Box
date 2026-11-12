import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, formatDateTime, PASSWORD_MIN_LENGTH, ROLE_LABELS } from "../api";
import type { Role, User } from "../api";
import { Alert, Dialog, Field, PageHeader } from "../components/ui";
import { useSession } from "../session";

export function Users() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const load = useCallback(() => {
    api.users().then(setUsers, (e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  return (
    <>
      <PageHeader
        title="Utilisateurs"
        lead="Chaque personne dispose de son propre compte et n'accède qu'aux entreprises qui lui sont rattachées."
        action={
          <button className="btn primary" onClick={() => setEditing("new")}>
            Nouvel utilisateur
          </button>
        }
      />
      {error && <Alert>{error}</Alert>}
      <section className="card flush">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Utilisateur</th>
                <th>Accès</th>
                <th>Dernière connexion</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {users?.map((user) => (
                <tr key={user.id} className={user.is_active ? "" : "inactive"}>
                  <td data-label="Utilisateur">
                    <span className="module-title">
                      <strong>{user.full_name}</strong>
                      {!user.is_active && <span className="tag danger">Désactivé</span>}
                    </span>
                    <div className="muted">{user.email}</div>
                  </td>
                  <td data-label="Accès">
                    {user.is_admin && <div>Administrateur du boîtier</div>}
                    {user.memberships.map((m) => (
                      <div key={m.company_id}>
                        {m.company_name} <span className="muted">— {ROLE_LABELS[m.role]}</span>
                      </div>
                    ))}
                    {!user.is_admin && user.memberships.length === 0 && (
                      <span className="muted">Aucun accès</span>
                    )}
                  </td>
                  <td className="nowrap" data-label="Dernière connexion">
                    {formatDateTime(user.last_login_at)}
                  </td>
                  <td className="actions">
                    <button className="btn" onClick={() => setEditing(user)}>
                      Modifier
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {editing && (
        <UserDialog
          user={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </>
  );
}

function UserDialog({
  user,
  onClose,
  onSaved,
}: {
  user: User | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { companies } = useSession();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false);
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [roles, setRoles] = useState<Record<string, Role | "">>(() =>
    Object.fromEntries(user?.memberships.map((m) => [m.company_id, m.role]) ?? []),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const memberships = Object.entries(roles)
      .filter((entry): entry is [string, Role] => entry[1] !== "")
      .map(([company_id, role]) => ({ company_id, role }));
    try {
      if (user) {
        await api.updateUser(user.id, {
          full_name: fullName,
          is_admin: isAdmin,
          is_active: isActive,
          memberships,
          ...(password ? { password } : {}),
        });
      } else {
        await api.createUser({
          email,
          full_name: fullName,
          password,
          is_admin: isAdmin,
          memberships,
        });
      }
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <Dialog title={user ? user.email : "Nouvel utilisateur"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="grid-2">
          <Field label="Nom complet">
            <input
              required
              maxLength={200}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </Field>
          {!user && (
            <Field label="Adresse e-mail">
              <input
                required
                type="email"
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
          )}
          <Field
            label={user ? "Nouveau mot de passe" : "Mot de passe initial"}
            hint={
              user
                ? "Laissez vide pour ne pas le changer. Sinon, la personne sera déconnectée."
                : `Au moins ${PASSWORD_MIN_LENGTH} caractères, à transmettre à la personne.`
            }
          >
            <input
              type="password"
              autoComplete="new-password"
              required={!user}
              minLength={PASSWORD_MIN_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        </div>

        <fieldset className="fieldset">
          <legend>Accès aux entreprises</legend>
          {companies.map((company) => (
            <label key={company.id} className="row-field">
              <span>{company.name}</span>
              <select
                value={roles[company.id] ?? ""}
                onChange={(e) =>
                  setRoles({ ...roles, [company.id]: e.target.value as Role | "" })
                }
              >
                <option value="">Aucun accès</option>
                {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>

        <label className="check">
          <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
          <span>
            Administrateur du boîtier
            <span className="muted module-text">
              Gère les utilisateurs, toutes les entreprises et le journal d'activité.
            </span>
          </span>
        </label>
        {user && (
          <label className="check">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            <span>
              Compte actif
              <span className="muted module-text">
                Un compte désactivé est déconnecté immédiatement et ne peut plus se connecter.
              </span>
            </span>
          </label>
        )}

        {error && <Alert>{error}</Alert>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Annuler
          </button>
          <button className="btn primary" disabled={busy}>
            {user ? "Enregistrer" : "Créer le compte"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
