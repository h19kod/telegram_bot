/** Single-series charts: one accent hue, recessive grid, hover tooltip, and a table view. */
import { useMemo, useRef, useState } from "react";

import { useSession } from "../lib/session";

export interface Point { label: string; value: number; sub?: string }

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function compact(v: number, lang: string): string {
  return new Intl.NumberFormat(lang === "ar" ? "ar-IQ" : "en", { notation: "compact",
    numberingSystem: "latn", maximumFractionDigits: 1 }).format(v);
}

export function AreaChart({ data, format, height = 220, label }: { data: Point[];
  format: (v: number) => string; height?: number; label: string }) {
  const { lang } = useSession();
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = height, padL = 44, padR = 12, padT = 12, padB = 26;
  const max = niceMax(Math.max(...data.map((d) => d.value), 0));
  const x = (i: number) => padL + (data.length <= 1 ? 0 : (i / (data.length - 1)) * (W - padL - padR));
  const y = (v: number) => padT + (1 - v / max) * (H - padT - padB);
  const path = useMemo(() => data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.value)}`).join(""),
    [data, max]); // eslint-disable-line react-hooks/exhaustive-deps
  const ticks = [0, 0.5, 1].map((f) => f * max);
  const every = Math.max(1, Math.ceil(data.length / 6));

  function move(e: React.PointerEvent) {
    const r = ref.current?.getBoundingClientRect();
    if (!r || !data.length) return;
    const rel = (e.clientX - r.left) / r.width; // figure is dir=ltr, so x grows rightwards
    const i = Math.round(((rel * W - padL) / (W - padL - padR)) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  }

  const h = hover !== null ? data[hover] : null;
  return (
    <figure className="relative" dir="ltr">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full touch-none"
        role="img" aria-label={label} onPointerMove={move} onPointerLeave={() => setHover(null)}>
        {ticks.map((tv) => (
          <g key={tv}>
            <line x1={padL} x2={W - padR} y1={y(tv)} y2={y(tv)} stroke="var(--color-line)" />
            <text x={padL - 6} y={y(tv) + 4} textAnchor="end" fontSize="11" fill="var(--color-hint)">
              {compact(tv, lang)}</text>
          </g>
        ))}
        {data.map((d, i) => i % every === 0 && (
          <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--color-hint)">
            {d.label}</text>
        ))}
        {data.length > 0 && <>
          <path d={`${path}L${x(data.length - 1)},${y(0)}L${x(0)},${y(0)}Z`}
            fill="var(--color-accent)" fillOpacity="0.12" />
          <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="2"
            strokeLinejoin="round" strokeLinecap="round" />
        </>}
        {h && hover !== null && <>
          <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke="var(--color-hint)"
            strokeDasharray="3 3" />
          <circle cx={x(hover)} cy={y(h.value)} r="5" fill="var(--color-accent)"
            stroke="var(--color-card)" strokeWidth="2" />
        </>}
      </svg>
      {h && hover !== null && (
        <div className="pointer-events-none absolute top-0 rounded-lg border border-line bg-card px-3 py-2 text-[12px] shadow-lg"
          style={{ left: `clamp(0px, calc(${(x(hover) / W) * 100}% - 70px), calc(100% - 140px))` }}>
          <div className="text-hint">{h.label}</div>
          <div className="tabular font-semibold">{format(h.value)}</div>
          {h.sub && <div className="text-hint">{h.sub}</div>}
        </div>
      )}
    </figure>
  );
}

export function BarList({ data, format }: { data: Point[]; format: (v: number) => string }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <ul className="space-y-2.5">
      {data.map((d) => (
        <li key={d.label} className="group" title={`${d.label}: ${format(d.value)}`}>
          <div className="mb-1 flex justify-between gap-3 text-[13px]">
            <span className="truncate">{d.label}</span>
            <span className="tabular shrink-0 font-semibold">{format(d.value)}</span>
          </div>
          <div className="h-2 rounded-full bg-bg2">
            <div className="h-2 rounded-full bg-accent transition-all group-hover:brightness-110"
              style={{ width: `${(d.value / max) * 100}%` }} />
          </div>
          {d.sub && <p className="mt-0.5 text-[12px] text-hint">{d.sub}</p>}
        </li>
      ))}
    </ul>
  );
}
