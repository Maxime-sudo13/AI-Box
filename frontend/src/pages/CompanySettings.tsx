import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, ROLE_LABELS } from "../api";
import type { Company, Module } from "../api";
import { CompanyFields, emptyCompanyForm, toCompanyInput } from "../components/CompanyFields";
import type { CompanyForm } from "../components/CompanyFields";
import { ModulePicker } from "../components/ModulePicker";
import { Alert, Dialog, PageHeader } from "../components/ui";
import { useSession } from "../session";

function formOf(company: Company): CompanyForm {
  return {
    name: company.name,
    legal_form: company.legal_form ?? "",
    siren: company.siren ?? "",
    sector: company.sector ?? "",
  };
}

type Notice = { kind: "ok" | "error"; text: string } | null;

export function CompanySettings() {
  const { user, company, canManageCompany, reloadCompanies, selectCompany } = useSession();
  const [catalog, setCatalog] = useState<Module[]>([]);
  const [form, setForm] = useState(emptyCompanyForm);
  const [modules, setModules] = useState<string[]>([]);
  const [infoNotice, setInfoNotice] = useState<Notice>(null);
  const [moduleNotice, setModuleNotice] = useState<Notice>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.modules().then(setCatalog, () => {});
  }, []);

  // Recharge les formulaires quand on change d'entreprise ou après un enregistrement.
  useEffect(() => {
    if (!company) return;
    setForm(formOf(company));
    setModules(company.enabled_modules);
  }, [company]);

  const addButton = user?.is_admin && (
    <button className="btn" onClick={() => setCreating(true)}>
      Ajouter une entreprise
    </button>
  );
  const createDialog = creating && (
    <CreateCompany
      onClose={() => setCreating(false)}
      onCreated={async (created) => {
        await reloadCompanies();
        selectCompany(created.id);
        setCreating(false);
      }}
    />
  );

  if (!company) {
    return (
      <>
        <PageHeader title="Entreprise et modules" action={addButton} />
        <section className="card empty">
          <p className="muted">Aucune entreprise ne vous est rattachée.</p>
        </section>
        {createDialog}
      </>
    );
  }

  async function saveInfo(event: FormEvent) {
    event.preventDefault();
    setInfoNotice(null);
    try {
      await api.updateCompany(company!.id, toCompanyInput(form));
      await reloadCompanies();
      setInfoNotice({ kind: "ok", text: "Informations enregistrées." });
    } catch (e) {
      setInfoNotice({ kind: "error", text: errorMessage(e) });
    }
  }

  async function saveModules() {
    setModuleNotice(null);
    try {
      await api.setModules(company!.id, modules);
      await reloadCompanies();
      setModuleNotice({ kind: "ok", text: "Modules enregistrés." });
    } catch (e) {
      setModuleNotice({ kind: "error", text: errorMessage(e) });
    }
  }

  const modulesChanged =
    [...modules].sort().join() !== [...company.enabled_modules].sort().join();

  return (
    <>
      <PageHeader
        title="Entreprise et modules"
        lead={
          canManageCompany
            ? company.name
            : `${company.name} — votre rôle (${
                company.role ? ROLE_LABELS[company.role] : "aucun"
              }) ne permet pas de modifier ces réglages.`
        }
        action={addButton}
      />

      <form className="card form" onSubmit={saveInfo}>
        <h2>Informations</h2>
        <CompanyFields value={form} onChange={setForm} disabled={!canManageCompany} />
        {infoNotice && <Alert kind={infoNotice.kind}>{infoNotice.text}</Alert>}
        {canManageCompany && (
          <div className="form-actions">
            <button className="btn primary">Enregistrer</button>
          </div>
        )}
      </form>

      <section className="card form">
        <h2>Modules</h2>
        <p className="muted">
          Le boîtier ne suit que les domaines activés ici. Les modules marqués « À venir » seront
          livrés par les prochaines mises à jour.
        </p>
        <ModulePicker
          modules={catalog}
          selected={modules}
          onChange={setModules}
          disabled={!canManageCompany}
        />
        {moduleNotice && <Alert kind={moduleNotice.kind}>{moduleNotice.text}</Alert>}
        {canManageCompany && (
          <div className="form-actions">
            <button className="btn primary" disabled={!modulesChanged} onClick={saveModules}>
              Enregistrer les modules
            </button>
          </div>
        )}
      </section>
      {createDialog}
    </>
  );
}

function CreateCompany({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (company: Company) => Promise<void>;
}) {
  const [form, setForm] = useState(emptyCompanyForm);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onCreated(await api.createCompany(toCompanyInput(form)));
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <Dialog title="Nouvelle entreprise" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <CompanyFields value={form} onChange={setForm} />
        {error && <Alert>{error}</Alert>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Annuler
          </button>
          <button className="btn primary" disabled={busy}>
            Créer l'entreprise
          </button>
        </div>
      </form>
    </Dialog>
  );
}
