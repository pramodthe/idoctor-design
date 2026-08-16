"use client";

import type { SmallMolCompound, VerdictItem } from "@/lib/types";

interface SmallMolTableProps {
  compounds: SmallMolCompound[];
  verdicts: VerdictItem[];
  primaryMutant?: string;
}

function verdictFor(
  verdicts: VerdictItem[],
  id: string
): VerdictItem | undefined {
  return verdicts.find((v) => v.subject_kind === "smallmol" && v.subject_id === id);
}

const VERDICT_BADGE: Record<string, string> = {
  promote: "bg-emerald-50 text-emerald-700 border-emerald-200",
  reject: "bg-red-50 text-red-700 border-red-200",
  hold: "bg-slate-100 text-slate-600 border-slate-200",
};

export default function SmallMolTable({
  compounds,
  verdicts,
  primaryMutant = "Y96D",
}: SmallMolTableProps) {
  // Sort by known Ki when present (lower better), not by best Vina
  const sorted = [...compounds].sort((a, b) => {
    const ka = a.known_ki_nm ?? Number.POSITIVE_INFINITY;
    const kb = b.known_ki_nm ?? Number.POSITIVE_INFINITY;
    return ka - kb;
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-400">
            <th className="pb-2 pr-3 font-semibold">Compound</th>
            <th className="pb-2 pr-3 font-semibold">Vina WT</th>
            <th className="pb-2 pr-3 font-semibold">Ki (nM)</th>
            <th className="pb-2 pr-3 font-semibold">Vina {primaryMutant}</th>
            <th className="pb-2 font-semibold">Eval</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => {
            const v = verdictFor(verdicts, c.id);
            const mutantScore =
              c.vina_mutants?.[primaryMutant] ??
              Object.values(c.vina_mutants || {})[0] ??
              null;
            return (
              <tr
                key={c.id}
                className="border-b border-slate-100 last:border-0"
              >
                <td className="py-2.5 pr-3">
                  <div className="font-medium text-slate-900">{c.name}</div>
                  <div className="font-mono text-[10px] text-slate-400">{c.id}</div>
                </td>
                <td className="py-2.5 pr-3 font-mono text-slate-700">
                  {c.vina_wt != null ? c.vina_wt.toFixed(1) : "—"}
                </td>
                <td className="py-2.5 pr-3 font-mono text-slate-700">
                  {c.known_ki_nm != null ? c.known_ki_nm : "—"}
                </td>
                <td className="py-2.5 pr-3 font-mono text-slate-700">
                  {mutantScore != null ? Number(mutantScore).toFixed(1) : "—"}
                </td>
                <td className="py-2.5">
                  {v ? (
                    <span
                      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${VERDICT_BADGE[v.verdict]}`}
                      title={v.summary}
                    >
                      {v.verdict}
                    </span>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-slate-400">
        Sorted by experimental Ki (nM), not Vina. WT = KRAS G12C without extra resistance mutation.
      </p>
    </div>
  );
}
