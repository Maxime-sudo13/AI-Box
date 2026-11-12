import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage } from "../api";
import { Alert, Brand, Field } from "../components/ui";
import { useSession } from "../session";

export function Login() {
  const { signedIn } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signedIn(await api.login(email, password));
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <main className="gate">
      <Brand />
      <h1>Connexion</h1>
      <form className="card form" onSubmit={submit}>
        <Field label="Adresse e-mail">
          <input
            required
            autoFocus
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Mot de passe">
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <Alert>{error}</Alert>}
        <button className="btn primary block" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>
      </form>
      <p className="muted small">Vos données restent sur ce boîtier, dans vos locaux.</p>
    </main>
  );
}
