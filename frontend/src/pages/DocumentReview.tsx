import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { errorMessage } from "../api";
import { DocStatusBadge, FIELD_STATUS } from "../components/finance-ui";
import { Alert as Notice, Field } from "../components/ui";
import { financeApi } from "../finance";
import type { Category, DocumentDetail, FieldStatus } from "../finance";
import { dateFr, eur, fileSize, num } from "../format";
import { useSession } from "../session";

interface Form {
  direction: "purchase" | "sale";
  party_name: string;
  number: string;
  issue_date: string;
  due_date: string;
  category: string;
  total_ht: string;
  total_tva: string;
  total_ttc: string;
}

function toForm(doc: DocumentDetail): Form {
  const inv = doc.invoice;
  const n = (v: number | null | undefined) => (v === null || v === undefined ? "" : v.toFixed(2).replace(".", ","));
  return {
    direction: inv?.direction ?? "purchase",
    party_name: inv?.party ?? "",
    number: inv?.number ?? "",
    issue_date: inv?.issue_date ?? "",
    due_date: inv?.due_date ?? "",
    category: inv?.category ?? "a_classer",
    total_ht: n(inv?.total_ht),
    total_tva: n(inv?.total_tva),
    total_ttc: n(inv?.total_ttc),
  };
}

function Marker({ status }: { status: FieldStatus | undefined }) {
  if (!status || status === "confirmed") return <span className="fmark ok" title="Lu et recoupé">✓</span>;
  return (
    <span className={`fmark ${status}`} title={FIELD_STATUS[status]}>
      {FIELD_STATUS[status]}
    </span>
  );
}

export function DocumentReview() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { company, canEditData } = useSession();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [applyToParty, setApplyToParty] = useState(true);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!company || !id) return;
    financeApi.document(company.id, id).then(
      (d) => {
        setDoc(d);
        setForm(toForm(d));
      },
      (e) => setNotice({ kind: "error", text: errorMessage(e) }),
    );
  }, [company, id]);
  useEffect(() => {
    setNotice(null);
    load();
  }, [load]);
  useEffect(() => {
    financeApi.categories().then(setCategories, () => {});
  }, []);

  if (!company) return null;
  if (!doc || !form) return notice ? <Notice>{notice.text}</Notice> : <p className="muted">Chargement…</p>;

  const inv = doc.invoice;
  const fs = inv?.field_status ?? {};
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const fileUrl = financeApi.documentFileUrl(company.id, doc.id);
  const readOnly = !canEditData;
  const original = toForm(doc);

  async function save(event: FormEvent | null, validate: boolean) {
    event?.preventDefault();
    if (!form || !doc) return;
    setBusy(true);
    setNotice(null);
    const body: Record<string, unknown> = { validate };
    const amount = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[\s\u202f]/g, "").replace(",", ".")));
    if (form.direction !== original.direction) body.direction = form.direction;
    if (form.party_name.trim() && form.party_name !== original.party_name) body.party_name = form.party_name.trim();
    if (form.number !== original.number) body.number = form.number || null;
    if (form.issue_date !== original.issue_date) body.issue_date = form.issue_date || null;
    if (form.due_date !== original.due_date) body.due_date = form.due_date || null;
    if (form.category !== original.category) {
      body.category = form.category;
      body.apply_category_to_party = applyToParty;
    }
    for (const k of ["total_ht", "total_tva", "total_ttc"] as const) {
      if (form[k] !== original[k]) body[k] = amount(form[k]);
    }
    try {
      const updated = await financeApi.updateInvoice(company!.id, doc.id, body);
      setDoc(updated);
      setForm(toForm(updated));
      if (validate && updated.status === "validated" && updated.next_to_review) {
        navigate(`/donnees/documents/${updated.next_to_review}`);
        setNotice({ kind: "ok", text: "Facture validée. Voici le document suivant à vérifier." });
      } else {
        setNotice({ kind: "ok", text: validate ? `Statut : ${updated.status_label}.` : "Modifications enregistrées." });
      }
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  async function action(kind: "ignore" | "restore" | "not_duplicate") {
    setBusy(true);
    setNotice(null);
    try {
      await financeApi.documentAction(company!.id, doc!.id, kind);
      load();
      setNotice({ kind: "ok", text: kind === "ignore" ? "Document écarté des calculs." : "Document réintégré." });
    } catch (e) {
      setNotice({ kind: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  const parse = (v: string) => Number(v.replace(/[\s\u202f]/g, "").replace(",", ".")) || 0;
  const ht = parse(form.total_ht);
  const tva = parse(form.total_tva);
  const ttc = parse(form.total_ttc);
  const consistent = form.total_ht && form.total_tva && form.total_ttc ? Math.abs(ht + tva - ttc) <= 0.05 : null;

  return (
    <div className="review">
      <div className="review-top">
        <Link to="/donnees?tab=factures" className="btn ghost">
          ← Données
        </Link>
        <div className="review-title">
          <h1>{inv?.party ?? doc.filename}</h1>
          <p className="muted small">
            {doc.filename} · {fileSize(doc.size)} · {doc.extraction.method === "ocr" ? "lu par reconnaissance de caractères" : "texte du PDF"}
            {doc.extraction.duration_ms !== undefined ? ` en ${num(doc.extraction.duration_ms / 1000, 1)} s` : ""}
          </p>
        </div>
        <DocStatusBadge status={doc.status} label={doc.status_label} />
        {doc.next_to_review && (
          <Link className="btn" to={`/donnees/documents/${doc.next_to_review}`}>
            Suivant à vérifier →
          </Link>
        )}
      </div>

      <div className="review-grid">
        <div className="viewer card flush">
          <div className="pages">
            {Array.from({ length: Math.min(doc.extraction.pages ?? 1, 10) }, (_, i) => (
              <img
                key={i}
                src={financeApi.documentPreviewUrl(company.id, doc.id, i + 1)}
                alt={`Page ${i + 1} du document original : ${doc.filename}`}
                loading={i ? "lazy" : "eager"}
              />
            ))}
          </div>
          <a className="btn ghost viewer-open" href={fileUrl} target="_blank" rel="noopener">
            Ouvrir l'original
          </a>
        </div>

        <div className="review-side">
          {notice && <Notice kind={notice.kind}>{notice.text}</Notice>}
          {doc.status === "duplicate" && doc.duplicate_of && (
            <div className="callout">
              Cette facture a déjà été importée sous{" "}
              <Link to={`/donnees/documents/${doc.duplicate_of.id}`}>« {doc.duplicate_of.filename} »</Link>. Elle est exclue des
              calculs pour ne pas être comptée deux fois.
              {canEditData && (
                <button className="btn" disabled={busy} onClick={() => void action("not_duplicate")}>
                  Ce n'est pas un doublon
                </button>
              )}
            </div>
          )}
          {doc.error && <Notice>{doc.error}</Notice>}
          {inv && inv.issues.length > 0 && (
            <div className="callout warn">
              <strong>Points à vérifier</strong>
              <ul className="plain">
                {inv.issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
          )}

          {inv ? (
            <form className="card form" onSubmit={(e) => void save(e, false)}>
              <div className="grid-2">
                <Field label="Type">
                  <select disabled={readOnly} value={form.direction} onChange={(e) => set({ direction: e.target.value as Form["direction"] })}>
                    <option value="purchase">Facture d'achat</option>
                    <option value="sale">Facture de vente</option>
                  </select>
                </Field>
                <Field label={form.direction === "sale" ? "Client" : "Fournisseur"}>
                  <span className="with-mark">
                    <input disabled={readOnly} required value={form.party_name} onChange={(e) => set({ party_name: e.target.value })} />
                    <Marker status={fs.party} />
                  </span>
                </Field>
                <Field label="Numéro">
                  <span className="with-mark">
                    <input disabled={readOnly} value={form.number} onChange={(e) => set({ number: e.target.value })} />
                    <Marker status={fs.number} />
                  </span>
                </Field>
                <Field label="Catégorie">
                  <select disabled={readOnly} value={form.category} onChange={(e) => set({ category: e.target.value })}>
                    {categories.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Date de facture">
                  <span className="with-mark">
                    <input disabled={readOnly} type="date" value={form.issue_date} onChange={(e) => set({ issue_date: e.target.value })} />
                    <Marker status={fs.issue_date} />
                  </span>
                </Field>
                <Field label="Échéance">
                  <span className="with-mark">
                    <input disabled={readOnly} type="date" value={form.due_date} onChange={(e) => set({ due_date: e.target.value })} />
                    <Marker status={fs.due_date} />
                  </span>
                </Field>
              </div>
              {form.category !== original.category && inv.party && (
                <label className="check small">
                  <input type="checkbox" checked={applyToParty} onChange={(e) => setApplyToParty(e.target.checked)} />
                  <span>Appliquer cette catégorie à toutes les factures et paiements de {inv.party}</span>
                </label>
              )}
              <div className="amounts">
                {(
                  [
                    ["total_ht", "Total HT"],
                    ["total_tva", "TVA"],
                    ["total_ttc", "Total TTC"],
                  ] as const
                ).map(([k, label]) => (
                  <Field key={k} label={label}>
                    <span className="with-mark">
                      <input
                        disabled={readOnly}
                        inputMode="decimal"
                        className="num"
                        value={form[k]}
                        onChange={(e) => set({ [k]: e.target.value } as Partial<Form>)}
                      />
                      <Marker status={fs[k]} />
                    </span>
                  </Field>
                ))}
              </div>
              {consistent !== null && (
                <p className={`small ${consistent ? "text-good" : "text-bad"}`}>
                  {consistent ? "✓ HT + TVA = TTC : les montants se recoupent." : "✗ HT + TVA ≠ TTC : corrigez l'un des montants."}
                </p>
              )}
              {inv.payment ? (
                <p className="small">
                  <span className="text-good">✓ Payée le {dateFr(inv.payment.date)}</span>
                  <span className="muted"> — rapprochée de l'opération « {inv.payment.label} »</span>
                </p>
              ) : (
                <p className="small muted">Aucun paiement rapproché dans le relevé bancaire.</p>
              )}
              {canEditData && (
                <div className="form-actions">
                  {doc.status === "ignored" ? (
                    <button type="button" className="btn" disabled={busy} onClick={() => void action("restore")}>
                      Réintégrer
                    </button>
                  ) : (
                    <button type="button" className="btn" disabled={busy} onClick={() => void action("ignore")}>
                      Ignorer ce document
                    </button>
                  )}
                  <button className="btn" disabled={busy}>
                    Enregistrer
                  </button>
                  {doc.status !== "validated" && doc.status !== "duplicate" && (
                    <button type="button" className="btn primary" disabled={busy || consistent === false} onClick={() => void save(null, true)}>
                      Valider la facture
                    </button>
                  )}
                </div>
              )}
            </form>
          ) : (
            canEditData && (
              <div className="form-actions">
                <button className="btn" disabled={busy} onClick={() => void action(doc.status === "ignored" ? "restore" : "ignore")}>
                  {doc.status === "ignored" ? "Réintégrer" : "Ignorer ce document"}
                </button>
              </div>
            )
          )}

          {inv && inv.lines.length > 0 && (
            <section className="card flush">
              <h2 className="card-pad">Lignes lues ({inv.lines.length})</h2>
              <div className="table-wrap">
                <table className="lines">
                  <thead>
                    <tr>
                      <th>Désignation</th>
                      <th className="num">Qté</th>
                      <th className="num">P.U. HT</th>
                      <th className="num">Total HT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inv.lines.map((l, i) => (
                      <tr key={i}>
                        <td data-label="Désignation">{l.description}</td>
                        <td className="num nowrap" data-label="Qté">
                          {num(l.quantity, l.quantity !== null && l.quantity % 1 ? 1 : 0)} {l.unit ?? ""}
                        </td>
                        <td className="num nowrap" data-label="P.U. HT">
                          {eur(l.unit_price, 2)}
                        </td>
                        <td className="num nowrap" data-label="Total HT">
                          {eur(l.total_ht, 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
