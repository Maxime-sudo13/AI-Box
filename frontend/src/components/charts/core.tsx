import { useLayoutEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";

/** Largeur disponible d'un conteneur, mise à jour quand il change de taille. */
export function useWidth<T extends HTMLElement>(initial = 600): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function scale(d0: number, d1: number, r0: number, r1: number) {
  const span = d1 - d0 || 1;
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0);
}

/** Graduations « rondes » couvrant [min, max]. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) max = min + 1;
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

/** Barre verticale arrondie (4 px) côté données, carrée côté ligne de base. */
export function columnPath(x: number, w: number, yBase: number, yValue: number): string {
  const h = Math.abs(yBase - yValue);
  const r = Math.min(4, w / 2, h);
  if (yValue <= yBase) {
    return `M${x},${yBase}V${yValue + r}Q${x},${yValue} ${x + r},${yValue}H${x + w - r}Q${x + w},${yValue} ${x + w},${yValue + r}V${yBase}Z`;
  }
  return `M${x},${yBase}V${yValue - r}Q${x},${yValue} ${x + r},${yValue}H${x + w - r}Q${x + w},${yValue} ${x + w},${yValue - r}V${yBase}Z`;
}

export function Tooltip({
  x,
  y,
  width,
  children,
}: {
  x: number;
  y: number;
  width: number;
  children: ReactNode;
}) {
  // Bascule à gauche du pointeur quand il approche du bord droit.
  const flip = x > width - 200;
  return (
    <div
      className="chart-tooltip"
      role="status"
      style={{ left: flip ? undefined : x + 14, right: flip ? width - x + 14 : undefined, top: Math.max(0, y) }}
    >
      {children}
    </div>
  );
}

export function TooltipRow({ value, label, mark }: { value: string; label: string; mark?: "line" | "bar" | "none"; color?: string }) {
  return (
    <div className="tt-row">
      {mark && mark !== "none" && <span className={`tt-key ${mark}`} aria-hidden="true" />}
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; kind: "bar" | "line" | "ref"; series?: 1 | 2 }[] }) {
  return (
    <ul className="legend">
      {items.map((item) => (
        <li key={item.label}>
          <span className={`legend-key ${item.kind} s${item.series ?? 1}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
