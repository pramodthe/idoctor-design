"use client";

import type { Design, VerdictItem } from "@/lib/types";

interface RejectDrawerProps {
  designs: Design[];
  verdicts: VerdictItem[];
}

export default function RejectDrawer({ designs, verdicts }: RejectDrawerProps) {
  const rejects = verdicts.filter(
    (v) => v.subject_kind === "design" && v.verdict === "reject"
  );

  if (rejects.length === 0) {
    return (
      <div className="border-t border-red-200 pt-4">
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-red-700/80">
          Reject pile
        </h4>
        <p className="text-xs text-slate-500">No designs rejected in this run.</p>
      </div>
    );
  }

  return (
    <div className="border-t border-red-200 pt-4">
      <h4 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-red-700">
        Reject pile — {rejects.length} killed by critic
      </h4>
      <ul className="space-y-3">
        {rejects.map((v) => {
          const design = designs.find((d) => d.id === v.subject_id);
          return (
            <li
              key={v.subject_id}
              className="rounded-r-lg border-l-2 border-red-400 bg-red-50/80 py-2 pl-3 pr-2"
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-sm font-semibold text-slate-900">
                  {v.subject_id}
                </span>
                {design && (
                  <span className="text-[10px] text-slate-500">
                    len {design.length} · pLDDT{" "}
                    {design.plddt != null ? design.plddt.toFixed(0) : "—"}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-700">
                {v.summary}
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {v.reasons.map((r) => (
                  <span
                    key={r}
                    className="rounded border border-red-200 bg-red-500/10 px-1.5 py-0.5 font-mono text-[10px] text-red-700"
                  >
                    {r}
                  </span>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
