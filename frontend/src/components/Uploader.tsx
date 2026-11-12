import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { DragEvent } from "react";
import { ApiError, errorMessage } from "../api";
import { financeApi } from "../finance";
import type { DocumentItem } from "../finance";
import { eur, plural } from "../format";

type Kind = "document" | "bank" | "sales";

interface Item {
  id: number;
  file: File;
  kind: Kind;
  state: "waiting" | "running" | "done" | "error" | "skipped";
  message?: string;
  tone?: "ok" | "warn" | "muted" | "danger";
  documentId?: string;
}

const CONCURRENCY = 3;

/** Reconnaît un export CSV : relevé bancaire ou journal de caisse, d'après ses colonnes. */
async function sniffCsv(file: File): Promise<Kind | null> {
  const head = (await file.slice(0, 4000).text()).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  if (/couverts|nourriture|ticket z|boissons ht|journal de caisse/.test(head)) return "sales";
  if (/libelle|solde|debit|credit|operation/.test(head)) return "bank";
  return null;
}

function describe(doc: DocumentItem): Pick<Item, "message" | "tone"> {
  const inv = doc.invoice;
  const who = inv?.party ? `${inv.party}${inv.total_ttc !== null ? ` · ${eur(inv.total_ttc, 2)}` : ""}` : "";
  switch (doc.status) {
    case "verified":
      return { message: `Vérifiée automatiquement — ${who}`, tone: "ok" };
    case "to_review":
      return { message: `À vérifier — ${who || "informations incomplètes"}`, tone: "warn" };
    case "duplicate":
      return { message: `Doublon d'une facture déjà importée — ${who}`, tone: "muted" };
    case "failed":
      return { message: doc.error ?? "Document illisible", tone: "danger" };
    default:
      return { message: doc.status_label, tone: "ok" };
  }
}

export function Uploader({ companyId, onDone }: { companyId: string; onDone: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const counter = useRef(0);

  const update = (id: number, patch: Partial<Item>) =>
    setItems((list) => list.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  async function run(queue: Item[]) {
    let next = 0;
    const worker = async () => {
      while (next < queue.length) {
        const item = queue[next++];
        update(item.id, { state: "running" });
        try {
          if (item.kind === "document") {
            const doc = await financeApi.uploadDocument(companyId, item.file);
            update(item.id, { state: "done", documentId: doc.id, ...describe(doc) });
          } else {
            const res = await financeApi.importFile(companyId, item.kind, item.file);
            const what = item.kind === "bank" ? "opération(s) bancaire(s)" : "journée(s) de caisse";
            update(item.id, {
              state: "done",
              tone: "ok",
              message: `${res.rows_added} ${what} importée(s)${res.warnings.length ? ` — ${res.warnings.join(" ")}` : ""}`,
            });
          }
        } catch (e) {
          const already = e instanceof ApiError && e.status === 409;
          const detail = already ? (e.detail as { document_id?: string } | null) : null;
          update(item.id, {
            state: already ? "skipped" : "error",
            tone: already ? "muted" : "danger",
            message: errorMessage(e),
            documentId: detail?.document_id,
          });
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker));
    onDone();
  }

  async function add(files: FileList | File[]) {
    const queue: Item[] = [];
    for (const file of Array.from(files)) {
      const isCsv = /\.(csv|txt)$/i.test(file.name) || file.type === "text/csv";
      let kind: Kind = "document";
      if (isCsv) {
        const sniffed = await sniffCsv(file);
        if (!sniffed) {
          queue.push({ id: ++counter.current, file, kind: "bank", state: "error", tone: "danger",
            message: "Fichier CSV non reconnu : il doit s'agir d'un relevé bancaire ou d'un journal de caisse." });
          continue;
        }
        kind = sniffed;
      }
      queue.push({ id: ++counter.current, file, kind, state: "waiting" });
    }
    setItems((list) => [...queue, ...list.filter((i) => i.state === "running" || i.state === "waiting"), ...list.filter((i) => i.state !== "running" && i.state !== "waiting")]);
    void run(queue.filter((i) => i.state === "waiting"));
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (e.dataTransfer.files.length) void add(e.dataTransfer.files);
  }

  const total = items.length;
  const finished = items.filter((i) => i.state !== "waiting" && i.state !== "running").length;
  const busy = finished < total;
  const counts = {
    ok: items.filter((i) => i.tone === "ok").length,
    warn: items.filter((i) => i.tone === "warn").length,
    other: items.filter((i) => i.tone === "muted" || i.tone === "danger").length,
  };

  return (
    <section className="card uploader">
      <div
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <svg width="36" height="36" viewBox="0 0 24 24" aria-hidden="true" className="drop-icon">
          <path d="M12 16V4m0 0-4 4m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div>
          <strong>Déposez vos documents ici</strong>
          <p className="muted small">
            Factures en PDF ou en photo, relevé bancaire et journal de caisse en CSV — un ou plusieurs centaines à la fois.
            Tout est lu sur le boîtier, rien ne sort de l'entreprise.
          </p>
        </div>
        <button type="button" className="btn primary" onClick={() => input.current?.click()}>
          Choisir des fichiers
        </button>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          accept=".pdf,.jpg,.jpeg,.png,.csv,application/pdf,image/jpeg,image/png,text/csv"
          onChange={(e) => {
            if (e.target.files?.length) void add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {total > 0 && (
        <div className="upload-report">
          <div className="upload-head">
            <strong>{busy ? `Lecture en cours : ${finished} / ${total}` : `Import terminé : ${plural(total, "fichier", "fichiers")}`}</strong>
            <span className="muted small">
              {counts.ok} prêt(s) · {counts.warn} à vérifier · {counts.other} écarté(s)
            </span>
          </div>
          <progress max={total} value={finished} aria-label="Progression de l'import" />
          <ul className="upload-list">
            {items.slice(0, 200).map((item) => (
              <li key={item.id} className={`up-${item.tone ?? "pending"}`}>
                <span className="up-dot" aria-hidden="true" />
                <span className="up-name">{item.file.name}</span>
                <span className="up-msg">
                  {item.state === "waiting" ? "En attente" : item.state === "running" ? "Lecture…" : item.message}
                  {item.documentId && (item.tone === "warn" || item.tone === "muted") && (
                    <Link to={`/donnees/documents/${item.documentId}`} className="up-link">
                      Ouvrir
                    </Link>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
