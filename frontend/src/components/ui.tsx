import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
        <rect width="32" height="32" rx="7" className="brand-mark" />
        <path
          d="M9 22V10h5.400c2.400 0 3.800 1.200 3.800 3.100 0 1.300-.7 2.200-1.900 2.600 1.500.3 2.400 1.400 2.400 2.900 0 2.100-1.600 3.400-4.100 3.400zm2.500-7h2.500c1 0 1.700-.5 1.700-1.400s-.7-1.400-1.700-1.400h-2.500zm0 4.800h2.800c1.200 0 1.900-.5 1.900-1.500s-.7-1.500-1.900-1.500h-2.800z"
          fill="#fff"
        />
        <circle cx="23.500" cy="10.500" r="2" className="brand-dot" />
      </svg>
      {!compact && <span className="brand-name">Business AI Box</span>}
    </span>
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "ok"; children: ReactNode }) {
  return (
    <p className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </p>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function PageHeader({
  title,
  lead,
  action,
}: {
  title: string;
  lead?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {lead && <p className="muted">{lead}</p>}
      </div>
      {action}
    </header>
  );
}

export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="dialog-body">
        <header className="dialog-header">
          <h2>{title}</h2>
          <button type="button" className="btn ghost" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
