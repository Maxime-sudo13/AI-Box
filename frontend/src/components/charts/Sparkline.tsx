import { scale } from "./core";

/** Mini-courbe de tendance : historique discret, point du mois analysé accentué. */
export function Sparkline({ values, highlight, label }: { values: (number | null)[]; highlight?: number; label: string }) {
  const W = 96;
  const H = 28;
  const pts = values.map((v, i) => ({ v, i })).filter((p): p is { v: number; i: number } => p.v !== null);
  if (pts.length < 2) return null;
  const vs = pts.map((p) => p.v);
  const y = scale(Math.min(...vs), Math.max(...vs), H - 4, 4);
  const x = scale(0, values.length - 1, 3, W - 3);
  const h = highlight !== undefined && values[highlight] !== null ? highlight : pts[pts.length - 1].i;
  return (
    <svg width={W} height={H} className="sparkline" role="img" aria-label={label}>
      <path d={`M${pts.map((p) => `${x(p.i)},${y(p.v)}`).join(" L")}`} fill="none" />
      <circle cx={x(h)} cy={y(values[h] as number)} r={3.5} />
    </svg>
  );
}
