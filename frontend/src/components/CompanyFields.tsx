import { LEGAL_FORMS } from "../api";
import type { CompanyInput } from "../api";
import { Field } from "./ui";

export interface CompanyForm {
  name: string;
  legal_form: string;
  siren: string;
  sector: string;
}

export const emptyCompanyForm: CompanyForm = { name: "", legal_form: "", siren: "", sector: "" };

export function toCompanyInput(form: CompanyForm): CompanyInput {
  return {
    name: form.name.trim(),
    legal_form: form.legal_form || null,
    siren: form.siren.replace(/\s/g, "") || null,
    sector: form.sector.trim() || null,
  };
}

export function CompanyFields({
  value,
  onChange,
  disabled = false,
}: {
  value: CompanyForm;
  onChange: (next: CompanyForm) => void;
  disabled?: boolean;
}) {
  const set = (patch: Partial<CompanyForm>) => onChange({ ...value, ...patch });
  // Une forme juridique saisie ailleurs que dans la liste reste proposée.
  const forms =
    value.legal_form && !LEGAL_FORMS.includes(value.legal_form)
      ? [...LEGAL_FORMS, value.legal_form]
      : LEGAL_FORMS;
  return (
    <div className="grid-2">
      <Field label="Nom de l'entreprise">
        <input
          required
          maxLength={200}
          disabled={disabled}
          value={value.name}
          onChange={(e) => set({ name: e.target.value })}
        />
      </Field>
      <Field label="Forme juridique">
        <select
          disabled={disabled}
          value={value.legal_form}
          onChange={(e) => set({ legal_form: e.target.value })}
        >
          <option value="">Non précisée</option>
          {forms.map((form) => (
            <option key={form}>{form}</option>
          ))}
        </select>
      </Field>
      <Field label="SIREN" hint="Facultatif — 9 chiffres.">
        <input
          inputMode="numeric"
          pattern="\s*(\d\s*){9}"
          title="9 chiffres"
          disabled={disabled}
          value={value.siren}
          onChange={(e) => set({ siren: e.target.value })}
        />
      </Field>
      <Field label="Secteur d'activité" hint="Facultatif.">
        <input
          maxLength={200}
          disabled={disabled}
          value={value.sector}
          onChange={(e) => set({ sector: e.target.value })}
        />
      </Field>
    </div>
  );
}
