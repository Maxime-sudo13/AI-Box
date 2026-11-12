import { useState } from "react";
import type { Treasury } from "../../finance";
import { dateFr, eur, eurCompact } from "../../format";
import { Legend, niceTicks, scale, Tooltip, TooltipRow, useWidth } from "./core";

const M = { top: 20, right: 16, bottom: 28, left: 56 };

/** Solde bancaire constaté (trait plein) puis prévu (trait clair), avec le seuil de vigilance. */
export function TreasuryChart({ data, height = 280, historyDays = 90 }: { data: Treasury; height?: number; historyDays?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const history = data.history.slice(-historyDays);
  const points = [
    ...history.map((p) => ({ ...p, forecast: false, inflow: 0, outflow: 0 })),
    ...data.forecast.map((p) => ({ ...p, forecast: true })),
  ];
  if (!points.length) return null;
  const H = height;
  if (width < 120) return <div className="chart" ref={ref} style={{ height: H }} />;
  const vals = points.map((p) => p.balance).concat(data.threshold ?? 0);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(...vals), 4);
  const y = scale(ticks[0], ticks[ticks.length - 1], H - M.bottom, M.top);
  const x = scale(0, points.length - 1, M.left, width - M.right);
  const split = history.length - 1;
  const past = points.slice(0, split + 1).map((p, i) => `${x(i)},${y(p.balance)}`).join(" L");
  const future = points.slice(split).map((p, i) => `${x(i + split)},${y(p.balance)}`).join(" L");
  const lowIndex = data.low_point ? points.findIndex((p) => p.date === data.low_point?.date && p.forecast) : -1;
  const below = data.low_point && data.threshold !== undefined && data.low_point.balance < data.threshold;

  // Repères d'axe : premier jour de chaque mois.
  const monthTicks = points
    .map((p, i) => ({ i, d: p.date }))
    .filter(({ d }) => d.endsWith("-01"));
  const active = hover !== null ? points[hover] : null;

  return (
    <div className="chart" ref={ref}>
      <Legend
        items={[
          { label: "Solde constaté", kind: "line", series: 1 },
          { label: "Solde prévu", kind: "line", series: 1 },
          { label: "Seuil de vigilance", kind: "ref" },
        ]}
      />
      <svg
        width={width}
        height={H}
        role="img"
        aria-label="Trésorerie constatée et prévue"
        onPointerMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - rect.left - M.left) / (width - M.left - M.right)) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className={t === 0 ? "axis" : "grid"} x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
            <text className="tick" x={M.left - 8} y={y(t) + 4} textAnchor="end">
              {eurCompact(t)}
            </text>
          </g>
        ))}
        {monthTicks.map(({ i, d }) => (
          <text key={d} className="tick" x={x(i)} y={H - 8} textAnchor="middle">
            {new Intl.DateTimeFormat("fr-FR", { month: "short" }).format(new Date(`${d}T12:00:00`))}
          </text>
        ))}
        <rect className="forecast-zone" x={x(split)} y={M.top} width={width - M.right - x(split)} height={H - M.top - M.bottom} />
        <line className="today" x1={x(split)} x2={x(split)} y1={M.top - 8} y2={H - M.bottom} />
        <text className="ref-label" x={x(split) + 6} y={M.top - 2}>
          Dernier relevé
        </text>
        {data.threshold !== undefined && (
          <>
            <line className="ref-line" x1={M.left} x2={width - M.right} y1={y(data.threshold)} y2={y(data.threshold)} />
            <text className="ref-label" x={M.left + 6} y={y(data.threshold) - 6}>
              Seuil de vigilance {eur(data.threshold)}
            </text>
          </>
        )}
        <path className="line s1" d={`M${past}`} fill="none" />
        <path className="line s1 forecast" d={`M${future}`} fill="none" />
        {hover !== null && <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={M.top} y2={H - M.bottom} />}
        {lowIndex >= 0 && data.low_point && (
          <g>
            <circle className={`dot ${below ? "critical" : "s1"}`} cx={x(lowIndex)} cy={y(data.low_point.balance)} r={5} />
            <text
              className="value-label"
              x={x(lowIndex)}
              y={y(data.low_point.balance) + 20}
              textAnchor={x(lowIndex) > width - 120 ? "end" : "middle"}
            >
              Point bas {eur(data.low_point.balance)} · {dateFr(data.low_point.date, "day")}
            </text>
          </g>
        )}
        {active && <circle className="dot s1" cx={x(hover as number)} cy={y(active.balance)} r={4} />}
      </svg>
      {active && hover !== null && (
        <Tooltip x={x(hover)} y={M.top} width={width}>
          <div className="tt-title">
            {dateFr(active.date, "long")} {active.forecast ? "· prévision" : ""}
          </div>
          <TooltipRow value={eur(active.balance)} label={active.forecast ? "Solde prévu" : "Solde constaté"} mark="line" />
          {active.forecast && active.outflow > 0 && <TooltipRow value={eur(-active.outflow)} label="Sorties prévues" mark="none" />}
          {active.forecast && active.inflow > 0 && <TooltipRow value={eur(active.inflow)} label="Entrées prévues" mark="none" />}
        </Tooltip>
      )}
    </div>
  );
}
