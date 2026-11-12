import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage } from "../api";
import { AGENT_NAMES, agentsApi } from "../agents";
import type { AdvisorStatus, ChatMessage, Conversation, Fact } from "../agents";
import { Alert as Notice } from "../components/ui";
import { dateFr } from "../format";
import { useSession } from "../session";

/** Rendu sûr du texte du conseiller : gras, listes, références [Fn] cliquables. */
function RichText({ text, facts, onFact }: { text: string; facts: Fact[]; onFact: (f: Fact) => void }) {
  const byId = new Map(facts.map((f) => [f.id, f]));
  const inline = (line: string, key: string): ReactNode[] =>
    line.split(/(\*\*[^*]+\*\*|\[F\d+\])/g).map((part, i) => {
      const k = `${key}-${i}`;
      if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={k}>{part.slice(2, -2)}</strong>;
      const ref = part.match(/^\[(F\d+)\]$/);
      if (ref) {
        const fact = byId.get(ref[1]);
        return fact ? (
          <button key={k} type="button" className={`cite q-${fact.quality}`} onClick={() => onFact(fact)} title={fact.label}>
            {ref[1]}
          </button>
        ) : (
          <Fragment key={k}>{part}</Fragment>
        );
      }
      return <Fragment key={k}>{part}</Fragment>;
    });
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`ul-${blocks.length}`}>{list}</ul>);
    list = [];
  };
  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return flush();
    if (/^[-•*]\s+/.test(line)) list.push(<li key={i}>{inline(line.replace(/^[-•*]\s+/, ""), `l${i}`)}</li>);
    else {
      flush();
      blocks.push(<p key={i}>{inline(line, `p${i}`)}</p>);
    }
  });
  flush();
  return <div className="rich">{blocks}</div>;
}

const QUALITY_LABEL = { confirmed: "Donnée vérifiée", estimated: "Estimation", hypothesis: "Hypothèse" } as const;

export function Advisor() {
  const { company, canEditData } = useSession();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("c") ?? undefined;
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [list, setList] = useState<Conversation[]>([]);
  const [conv, setConv] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fact, setFact] = useState<Fact | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const refreshList = useCallback(() => {
    if (company) agentsApi.conversations(company.id).then(setList, () => {});
  }, [company]);

  useEffect(() => {
    if (!company) return;
    agentsApi.status(company.id).then(setStatus, (e) => setError(errorMessage(e)));
    refreshList();
  }, [company, refreshList]);

  useEffect(() => {
    if (!company) return;
    if (!conversationId) return setConv(null);
    agentsApi.conversation(company.id, conversationId).then(setConv, (e) => setError(errorMessage(e)));
  }, [company, conversationId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [conv, pending]);

  if (!company) return null;

  async function send(text: string, event?: FormEvent) {
    event?.preventDefault();
    const q = text.trim();
    if (!q || pending) return;
    setPending(q);
    setQuestion("");
    setError(null);
    try {
      const updated = await agentsApi.ask(company!.id, q, conv?.id);
      setConv(updated);
      if (!conv) setParams({ c: updated.id }, { replace: true });
      refreshList();
    } catch (e) {
      setError(errorMessage(e));
      setQuestion(q);
    } finally {
      setPending(null);
    }
  }

  async function prepare(alert: string, actionType: string) {
    try {
      const action = await agentsApi.fromAlert(company!.id, alert, actionType);
      navigate(`/automatisation?tab=${action.status === "pending" ? "pending" : "history"}&action=${action.id}`);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const messages = conv?.messages ?? [];

  return (
    <div className="advisor">
      <aside className="conv-list card">
        <button className="btn primary block" onClick={() => setParams({})}>
          Nouvelle question
        </button>
        <h3>Historique</h3>
        {list.length === 0 && <p className="muted small">Vos échanges apparaîtront ici. Ils restent sur le boîtier.</p>}
        <ul className="plain">
          {list.map((c) => (
            <li key={c.id}>
              <button className={`conv-item${c.id === conv?.id ? " on" : ""}`} onClick={() => setParams({ c: c.id })}>
                <span>{c.title}</span>
                <span className="muted small">{dateFr(c.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat card">
        <header className="chat-head">
          <div>
            <h1>Conseiller</h1>
            <p className="muted small">Il répond uniquement à partir de vos données ; chaque chiffre renvoie à sa source.</p>
          </div>
          {status && (
            <span className={`model-status ${status.available ? "on" : "off"}`} title={status.model ?? ""}>
              <span className="dot" aria-hidden="true" />
              {status.available
                ? `IA locale active · ${status.model}`
                : status.ai_enabled
                  ? "IA locale indisponible : réponses du moteur de calcul"
                  : "IA désactivée : réponses du moteur de calcul"}
            </span>
          )}
        </header>

        <div className="chat-body">
          {messages.length === 0 && !pending && (
            <div className="chat-empty">
              <h2>Que voulez-vous savoir sur votre entreprise ?</h2>
              <div className="examples">
                {status?.examples.map((ex) => (
                  <button key={ex} className="example" onClick={() => void send(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
              {status && (
                <details className="agents-info">
                  <summary>Comment le conseiller travaille</summary>
                  <p className="muted small">
                    Un agent central répartit votre question entre des agents spécialisés. Chacun n'accède qu'aux données de
                    sa mission, calcule des faits vérifiables, puis le modèle local reformule la réponse. Un contrôle refuse
                    toute rédaction contenant un chiffre absent des faits. Le conseiller n'exécute jamais rien : il peut
                    proposer des actions que vous validez.
                  </p>
                  <ul className="plain small">
                    {status.agents.map((a) => (
                      <li key={a.key}>
                        <strong>{a.name}</strong> — {a.mission} <span className="muted">Données : {a.domains.join(", ")}.</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          {messages.map((m) => (
            <MessageView key={m.id} message={m} onFact={setFact} onPrepare={canEditData ? prepare : undefined} />
          ))}
          {pending && (
            <>
              <div className="msg user">
                <p>{pending}</p>
              </div>
              <div className="msg assistant thinking" aria-busy="true">
                <span className="typing" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                Les agents analysent vos données…
              </div>
            </>
          )}
          <div ref={bottom} />
        </div>

        {error && <Notice>{error}</Notice>}
        <form className="chat-input" onSubmit={(e) => void send(question, e)}>
          <textarea
            rows={2}
            value={question}
            maxLength={1000}
            placeholder="Posez votre question… (par exemple : pourquoi ma marge a-t-elle baissé en septembre ?)"
            aria-label="Votre question"
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(question);
              }
            }}
          />
          <button className="btn primary" disabled={!question.trim() || Boolean(pending)}>
            Envoyer
          </button>
        </form>
      </section>

      {fact && (
        <aside className="fact-panel card" role="dialog" aria-label={`Source du fait ${fact.id}`}>
          <div className="card-head">
            <h2>
              {fact.id} · {fact.label}
            </h2>
            <button className="btn ghost" onClick={() => setFact(null)} aria-label="Fermer">
              ✕
            </button>
          </div>
          <p className="fact-value">{fact.display}</p>
          <span className={`quality q-${fact.quality === "confirmed" ? "confirmed" : "estimated"}`}>
            <span className="quality-dot" aria-hidden="true" />
            {QUALITY_LABEL[fact.quality]}
          </span>
          <p className="small">
            <span className="muted">Source : </span>
            {fact.source}
          </p>
          {fact.link && (
            <Link className="btn" to={fact.link}>
              Voir le détail
            </Link>
          )}
        </aside>
      )}
    </div>
  );
}

function MessageView({
  message,
  onFact,
  onPrepare,
}: {
  message: ChatMessage;
  onFact: (f: Fact) => void;
  onPrepare?: (alert: string, actionType: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="msg user">
        <p>{message.content}</p>
      </div>
    );
  }
  const g = message.generation;
  return (
    <div className="msg assistant">
      <RichText text={message.content} facts={message.facts} onFact={onFact} />
      {message.suggestions.length > 0 && onPrepare && (
        <div className="msg-actions">
          <span className="muted small">L'agent exécutif peut préparer :</span>
          {message.suggestions.map((s) => (
            <button key={`${s.alert}-${s.action_type}`} className="btn" onClick={() => onPrepare(s.alert, s.action_type)}>
              {s.title}
            </button>
          ))}
        </div>
      )}
      <div className="msg-meta">
        {message.agents.map((a) => (
          <span key={a} className="tag">
            {AGENT_NAMES[a] ?? a}
          </span>
        ))}
        <span className="muted small">
          {g.writer === "llm" ? `Rédigé par ${g.model} · chiffres contrôlés` : "Rédigé par le moteur de calcul"}
          {g.guard === "rejected" ? " · rédaction de l'IA écartée (chiffre non vérifié)" : ""} · {message.facts.length} fait(s)
        </span>
      </div>
    </div>
  );
}
