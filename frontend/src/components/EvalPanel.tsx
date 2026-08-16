"use client";

import type { EvalPayload } from "@/lib/types";

interface EvalPanelProps {
  evalData: EvalPayload;
}

export default function EvalPanel({ evalData }: EvalPanelProps) {
  const rho = evalData.smallmol_spearman_rho;
  const n = evalData.smallmol_n;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Spearman ρ (Vina vs Ki)
          </div>
          <div className="mt-0.5 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {rho != null ? rho.toFixed(2) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            n
          </div>
          <div className="mt-0.5 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {n}
          </div>
        </div>
      </div>

      {evalData.smallmol_note && (
        <p className="text-xs leading-relaxed text-slate-400">
          {evalData.smallmol_note}
        </p>
      )}

      {evalData.disagreements?.length > 0 && (
        <div>
          <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-amber-700">
            Disagreements
          </h4>
          <ul className="space-y-2">
            {evalData.disagreements.map((d) => (
              <li
                key={d.id}
                className="border-l-2 border-amber-500/60 pl-3 text-xs text-slate-700"
              >
                <span className="font-mono font-semibold">{d.id}</span>
                <span className="mx-1.5 text-slate-600">·</span>
                <span className="text-slate-500">
                  Vina rank {d.vina_rank} vs Ki rank {d.ki_rank}
                </span>
                <p className="mt-0.5 text-slate-400">{d.note}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
