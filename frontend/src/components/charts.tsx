"use client";

export interface BarDatum {
  id: string;
  label: string;
  value: number;
  tone?: "promote" | "reject" | "hold" | "neutral" | "accent";
}

export interface StackSegment {
  key: string;
  value: number;
  color: string;
}

export interface StackedBarDatum {
  id: string;
  label: string;
  segments: StackSegment[];
}

const TONE: Record<NonNullable<BarDatum["tone"]>, string> = {
  promote: "#16a34a",
  reject: "#dc2626",
  hold: "#94a3b8",
  neutral: "#64748b",
  accent: "#2563eb",
};

export function HorizontalBars({
  data,
  max,
  unit = "",
  height = 160,
}: {
  data: BarDatum[];
  max?: number;
  unit?: string;
  height?: number;
}) {
  if (data.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-slate-400">
        No values yet
      </div>
    );
  }
  const ceiling = max ?? Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="space-y-2.5" style={{ minHeight: height }}>
      {data.map((d) => {
        const pct = Math.max(2, (d.value / ceiling) * 100);
        return (
          <div key={d.id} className="grid grid-cols-[72px_1fr_48px] items-center gap-2">
            <span className="truncate font-mono text-[11px] font-medium text-slate-600">
              {d.label}
            </span>
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${pct}%`,
                  background: TONE[d.tone || "accent"],
                }}
              />
            </div>
            <span className="text-right font-mono text-[11px] tabular-nums text-slate-700">
              {Number.isInteger(d.value) ? d.value : d.value.toFixed(1)}
              {unit}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function StackedBars({
  data,
  height = 140,
  legend,
}: {
  data: StackedBarDatum[];
  height?: number;
  legend?: { key: string; color: string; label: string }[];
}) {
  if (data.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-slate-400">
        No series yet
      </div>
    );
  }
  const totals = data.map((d) =>
    d.segments.reduce((s, seg) => s + Math.max(0, seg.value), 0)
  );
  const ceiling = Math.max(...totals, 1);

  return (
    <div>
      {legend && legend.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-3">
          {legend.map((l) => (
            <span key={l.key} className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <span
                className="h-2 w-2 rounded-sm"
                style={{ background: l.color }}
              />
              {l.label}
            </span>
          ))}
        </div>
      )}
      <div
        className="flex items-end gap-1.5"
        style={{ height }}
      >
        {data.map((d) => {
          const total = d.segments.reduce((s, seg) => s + Math.max(0, seg.value), 0);
          const barH = Math.max(8, (total / ceiling) * height);
          return (
            <div key={d.id} className="group flex flex-1 flex-col items-center justify-end gap-1">
              <div
                className="flex w-full max-w-[36px] flex-col-reverse overflow-hidden rounded-t-md shadow-sm transition-transform duration-300 group-hover:-translate-y-0.5"
                style={{ height: barH }}
                title={`${d.label}: ${total.toFixed(1)}`}
              >
                {d.segments.map((seg) => {
                  const h =
                    total > 0 ? (Math.max(0, seg.value) / total) * 100 : 0;
                  if (h <= 0) return null;
                  return (
                    <div
                      key={seg.key}
                      style={{ height: `${h}%`, background: seg.color }}
                    />
                  );
                })}
              </div>
              <span className="max-w-full truncate text-[9px] font-medium text-slate-500">
                {d.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function VerdictPills({
  promote,
  reject,
  hold,
}: {
  promote: number;
  reject: number;
  hold: number;
}) {
  const total = promote + reject + hold || 1;
  return (
    <div className="space-y-3">
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
        <div
          className="bg-emerald-500 transition-all duration-700"
          style={{ width: `${(promote / total) * 100}%` }}
        />
        <div
          className="bg-amber-400 transition-all duration-700"
          style={{ width: `${(hold / total) * 100}%` }}
        />
        <div
          className="bg-red-500 transition-all duration-700"
          style={{ width: `${(reject / total) * 100}%` }}
        />
      </div>
      <div className="flex flex-wrap gap-4 text-[11px]">
        <span className="flex items-center gap-1.5 text-emerald-700">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Promote {promote}
        </span>
        <span className="flex items-center gap-1.5 text-amber-700">
          <span className="h-2 w-2 rounded-full bg-amber-400" />
          Hold {hold}
        </span>
        <span className="flex items-center gap-1.5 text-red-700">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          Reject {reject}
        </span>
      </div>
    </div>
  );
}

export function Gauge({
  value,
  label,
  detail,
  good = true,
}: {
  value: string;
  label: string;
  detail?: string;
  good?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div
        className={`mt-1 font-display text-3xl font-semibold tabular-nums ${
          good ? "text-slate-900" : "text-amber-600"
        }`}
      >
        {value}
      </div>
      {detail && <p className="mt-1 text-[11px] text-slate-500">{detail}</p>}
    </div>
  );
}
