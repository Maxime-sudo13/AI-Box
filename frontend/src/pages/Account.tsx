import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, PASSWORD_MIN_LENGTH, ROLE_LABELS } from "../api";
import { Alert, Field, PageHeader } from "../components/ui";
import { useSession } from "../session";

export function Account() {
  const { user } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    if (next !== confirm) {
      return setNotice({ kind: "error", text: "Les deux mots de passe ne correspondent pas." });
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      setNotice({
        kind: "ok",
        text: "Mot de passe modifié. Vos autres appareils ont été déconnectés.",
      });
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Mon compte" />
      <section className="card">
        <dl className="facts">
          <div>
            <dt>Nom</dt>
            <dd>{user.full_name}</dd>
          </div>
          <div>
            <dt>Adresse e-mail</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>Accès</dt>
            <dd>
              {user.is_admin && <div>Administrateur du boîtier</div>}
              {user.memberships.map((m) => (
                <div key={m.company_id}>
                  {m.company_name} — {ROLE_LABELS[m.role]}
                </div>
              ))}
              {!user.is_admin && user.memberships.length === 0 && "Aucun"}
            </dd>
          </div>
        </dl>
      </section>

      <form className="card form narrow" onSubmit={submit}>
        <h2>Changer de mot de passe</h2>
        <Field label="Mot de passe actuel">
          <input
            required
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field label="Nouveau mot de passe" hint={`Au moins ${PASSWORD_MIN_LENGTH} caractères.`}>
          <input
            required
            type="password"
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        <Field label="Confirmation">
          <input
            required
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
        <div className="form-actions">
          <button className="btn primary" disabled={busy}>
            Modifier le mot de passe
          </button>
        </div>
      </form>
    </>
  );
}
