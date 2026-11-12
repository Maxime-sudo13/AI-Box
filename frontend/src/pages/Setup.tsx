import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, PASSWORD_MIN_LENGTH } from "../api";
import type { Module } from "../api";
import { CompanyFields, emptyCompanyForm, toCompanyInput } from "../components/CompanyFields";
import { ModulePicker } from "../components/ModulePicker";
import { Alert, Brand, Field } from "../components/ui";
import { useSession } from "../session";

const STEPS = ["Compte administrateur", "Votre entreprise", "Modules"];

export function Setup() {
  const { signedIn } = useSession();
  const [step, setStep] = useState(0);
  const [admin, setAdmin] = useState({ full_name: "", email: "", password: "", confirm: "" });
  const [company, setCompany] = useState(emptyCompanyForm);
  const [catalog, setCatalog] = useState<Module[]>([]);
  const [modules, setModules] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.modules().then(setCatalog, (e) => setError(errorMessage(e)));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (step === 0 && admin.password !== admin.confirm) {
      return setError("Les deux mots de passe ne correspondent pas.");
    }
    if (step < STEPS.length - 1) return setStep(step + 1);

    setBusy(true);
    try {
      const user = await api.setup({
        admin: { full_name: admin.full_name, email: admin.email, password: admin.password },
        company: toCompanyInput(company),
        modules,
      });
      await signedIn(user);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <main className="gate wide">
      <Brand />
      <h1>Installation de votre boîtier</h1>
      <ol className="steps">
        {STEPS.map((label, index) => (
          <li
            key={label}
            className={index === step ? "current" : index < step ? "done" : ""}
            aria-current={index === step ? "step" : undefined}
          >
            <span className="step-index">{index + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      <form className="card form" onSubmit={submit}>
        {step === 0 && (
          <>
            <p className="muted">
              Ce compte administre le boîtier : utilisateurs, entreprises et autorisations. Il est
              créé et conservé uniquement sur cet appareil.
            </p>
            <div className="grid-2">
              <Field label="Nom complet">
                <input
                  required
                  autoFocus
                  autoComplete="name"
                  maxLength={200}
                  value={admin.full_name}
                  onChange={(e) => setAdmin({ ...admin, full_name: e.target.value })}
                />
              </Field>
              <Field label="Adresse e-mail">
                <input
                  required
                  type="email"
                  autoComplete="username"
                  value={admin.email}
                  onChange={(e) => setAdmin({ ...admin, email: e.target.value })}
                />
              </Field>
              <Field label="Mot de passe" hint={`Au moins ${PASSWORD_MIN_LENGTH} caractères.`}>
                <input
                  required
                  type="password"
                  autoComplete="new-password"
                  minLength={PASSWORD_MIN_LENGTH}
                  value={admin.password}
                  onChange={(e) => setAdmin({ ...admin, password: e.target.value })}
                />
              </Field>
              <Field label="Confirmation du mot de passe">
                <input
                  required
                  type="password"
                  autoComplete="new-password"
                  value={admin.confirm}
                  onChange={(e) => setAdmin({ ...admin, confirm: e.target.value })}
                />
              </Field>
            </div>
          </>
        )}

        {step === 1 && <CompanyFields value={company} onChange={setCompany} />}

        {step === 2 && (
          <>
            <p className="muted">
              Choisissez les domaines que le boîtier doit suivre. Ce choix reste modifiable à tout
              moment dans les paramètres.
            </p>
            <ModulePicker modules={catalog} selected={modules} onChange={setModules} />
          </>
        )}

        {error && <Alert>{error}</Alert>}

        <div className="form-actions">
          {step > 0 && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setError(null);
                setStep(step - 1);
              }}
            >
              Retour
            </button>
          )}
          <button className="btn primary" disabled={busy}>
            {step < STEPS.length - 1 ? "Continuer" : busy ? "Installation…" : "Terminer l'installation"}
          </button>
        </div>
      </form>
    </main>
  );
}
