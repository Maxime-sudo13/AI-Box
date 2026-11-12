import { useState } from "react";
import { monthShort, pct } from "../../format";
import { niceTicks, scale, Tooltip, TooltipRow, useWidth } from "./core";

const H = 200;
const M = { top: 16, right: 16, bottom: 28, left: 44 };

/** Évolution d'un ratio mensuel (en %), avec sa moyenne comme repère. */
export function RatioChart({
  points,
  label,
  selected,
}: {
  points: { month: string; label: string; value: number | null; partial: boolean }[];
  label: string;
  selected: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const complete = points.filter((p) => !p.partial && p.value !== null);
  if (complete.length < 2) return null;
  if (width < 120) return <div className="chart" ref={ref} style={{ height: H }} />;
  const shown = points.filter((p) => !p.partial);
  const avg = complete.reduce((s, p) => s + (p.value ?? 0), 0) / complete.length;
  const vals = complete.map((p) => p.value as number);
  const ticks = niceTicks(Math.max(0, Math.min(...vals) - 3), Math.max(...vals) + 2, 4);
  const y = scale(ticks[0], ticks[ticks.length - 1], H - M.bottom, M.top);
  const x = scale(0, shown.length - 1, M.left + 8, width - M.right - 8);
  const path = shown.map((p, i) => (p.value === null ? null : `${x(i)},${y(p.value)}`)).filter(Boolean).join(" L");
  const sel = shown.findIndex((p) => p.month === selected);
  const step = width < 420 ? 3 : width < 640 ? 2 : 1;

  return (
    <div className="chart" ref={ref}>
      <svg
        width={width}
        height={H}
        role="img"
        aria-label={`${label} par mois`}
        onPointerMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - rect.left - M.left - 8) / (width - M.left - M.right - 16)) * (shown.length - 1));
          setHover(Math.max(0, Math.min(shown.length - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
            <text className="tick" x={M.left - 8} y={y(t) + 4} textAnchor="end">
              {t.toLocaleString("fr-FR")} %
            </text>
          </g>
        ))}
        <line className="ref-line" x1={M.left} x2={width - M.right} y1={y(avg)} y2={y(avg)} />
        <text className="ref-label" x={width - M.right} y={y(avg) - 6} textAnchor="end">
          Moyenne {pct(avg)}
        </text>
        {shown.map(
          (p, i) =>
            i % step === (shown.length - 1) % step && (
              <text key={p.month} className="tick" x={x(i)} y={H - 8} textAnchor="middle">
                {monthShort(p.month)}
              </text>
            ),
        )}
        {hover !== null && <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={M.top} y2={H - M.bottom} />}
        <path className="line s1" d={`M${path}`} fill="none" />
        {sel >= 0 && shown[sel].value !== null && (
          <>
            <circle className="dot s1" cx={x(sel)} cy={y(shown[sel].value as number)} r={4} />
            <text className="value-label" x={x(sel)} y={y(shown[sel].value as number) - 10} textAnchor="middle">
              {pct(shown[sel].value)}
            </text>
          </>
        )}
        {hover !== null && shown[hover].value !== null && hover !== sel && (
          <circle className="dot s1" cx={x(hover)} cy={y(shown[hover].value as number)} r={4} />
        )}
      </svg>
      {hover !== null && (
        <Tooltip x={x(hover)} y={M.top} width={width}>
          <div className="tt-title">{shown[hover].label}</div>
          <TooltipRow value={pct(shown[hover].value)} label={label} mark="line" />
          <TooltipRow value={pct(avg)} label="Moyenne de la période" mark="none" />
        </Tooltip>
      )}
    </div>
  );
}
