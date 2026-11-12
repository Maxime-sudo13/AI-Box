import { useState } from "react";
import type { SeriesPoint } from "../../finance";
import { eur, eurCompact, monthShort, pct } from "../../format";
import { columnPath, Legend, niceTicks, scale, Tooltip, TooltipRow, useWidth } from "./core";

const H = 260;
const M = { top: 16, right: 12, bottom: 28, left: 52 };

/** Chiffre d'affaires (colonnes) et EBE (ligne) par mois, sur un seul axe en euros. */
export function ActivityChart({
  points,
  selected,
  onSelect,
}: {
  points: SeriesPoint[];
  selected: string;
  onSelect: (month: string) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  if (!points.length) return null;
  if (width < 120) return <div className="chart" ref={ref} style={{ height: H }} />;

  const values = points.flatMap((p) => [p.revenue ?? 0, p.ebe ?? 0]);
  const ticks = niceTicks(Math.min(0, ...values), Math.max(...values), 4);
  const y = scale(ticks[0], ticks[ticks.length - 1], H - M.bottom, M.top);
  const band = (width - M.left - M.right) / points.length;
  const barW = Math.min(24, band * 0.55);
  const cx = (i: number) => M.left + band * i + band / 2;
  const line = points
    .map((p, i) => (p.ebe === null ? null : `${cx(i)},${y(p.ebe)}`))
    .filter(Boolean)
    .join(" L");
  const step = width < 420 ? 3 : width < 640 ? 2 : 1;
  const active = hover ?? null;

  return (
    <div className="chart" ref={ref}>
      <Legend
        items={[
          { label: "Chiffre d'affaires HT", kind: "bar", series: 1 },
          { label: "EBE estimé", kind: "line", series: 2 },
        ]}
      />
      <svg width={width} height={H} role="img" aria-label="Chiffre d'affaires et EBE par mois">
        {ticks.map((t) => (
          <g key={t}>
            <line className={t === 0 ? "axis" : "grid"} x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
            <text className="tick" x={M.left - 8} y={y(t) + 4} textAnchor="end">
              {eurCompact(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) => (
          <g key={p.month}>
            {p.month === selected && (
              <rect className="band-selected" x={M.left + band * i} y={M.top} width={band} height={H - M.top - M.bottom} />
            )}
            {p.revenue !== null && (
              <path
                className={`bar s1${p.partial ? " partial" : ""}${active === i ? " hover" : ""}`}
                d={columnPath(cx(i) - barW / 2, barW, y(0), y(p.revenue))}
              />
            )}
            {i % step === (points.length - 1) % step && (
              <text className="tick" x={cx(i)} y={H - 8} textAnchor="middle">
                {monthShort(p.month)}
              </text>
            )}
          </g>
        ))}
        <path className="line s2" d={`M${line}`} fill="none" />
        {points.map((p, i) =>
          p.ebe === null ? null : (
            <circle key={p.month} className={`dot s2${p.partial ? " partial" : ""}`} cx={cx(i)} cy={y(p.ebe)} r={active === i ? 5 : 4} />
          ),
        )}
        {points.map((p, i) => (
          <rect
            key={p.month}
            className="hit"
            x={M.left + band * i}
            y={M.top}
            width={band}
            height={H - M.top - M.bottom}
            tabIndex={0}
            role="button"
            aria-label={`${p.label} : chiffre d'affaires ${eur(p.revenue)}, EBE ${eur(p.ebe)}`}
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            onClick={() => !p.partial && onSelect(p.month)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !p.partial) onSelect(p.month);
            }}
          />
        ))}
      </svg>
      {active !== null && (
        <Tooltip x={cx(active)} y={M.top} width={width}>
          <div className="tt-title">
            {points[active].label}
            {points[active].partial && " (en cours)"}
          </div>
          <TooltipRow value={eur(points[active].revenue)} label="Chiffre d'affaires HT" mark="bar" />
          <TooltipRow value={eur(points[active].ebe)} label="EBE estimé" mark="line" />
          <TooltipRow value={pct(points[active].ebe_pct)} label="Marge d'EBE" mark="none" />
          {!points[active].partial && points[active].month !== selected && <div className="tt-hint">Cliquer pour analyser ce mois</div>}
        </Tooltip>
      )}
    </div>
  );
}
