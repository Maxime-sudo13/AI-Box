const NBSP = " ";

export function eur(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Montant compact pour les axes : 12 k€, 1,2 M€. */
export function eurCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })}${NBSP}M€`;
  if (abs >= 10_000) return `${Math.round(value / 1000).toLocaleString("fr-FR")}${NBSP}k€`;
  return `${Math.round(value).toLocaleString("fr-FR")}${NBSP}€`;
}

export function pct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${NBSP}%`;
}

export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function dateFr(iso: string | null | undefined, style: "short" | "long" | "day" = "short"): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (style === "day") return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(d);
  if (style === "long") return new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" }).format(d);
  return new Intl.DateTimeFormat("fr-FR").format(d);
}

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

export function monthShort(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${String(y).slice(2)}`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
  return `${(bytes / 1024 ** 3).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Go`;
}

export function plural(n: number, one: string, many: string): string {
  return `${num(n)} ${n > 1 ? many : one}`;
}
