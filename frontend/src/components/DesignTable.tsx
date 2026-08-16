"use client";

import { Fragment, useState } from "react";
import type { Design, VerdictItem, DesignDelta } from "@/lib/types";

interface DesignTableProps {
  designs: Design[];
  verdicts: VerdictItem[];
  deltas?: DesignDelta[];
  /** If true, only show rejected rows (reject pile) */
  rejectOnly?: boolean;
  title?: string;
  designEngine?: string;
}

const VERDICT_BADGE: Record<string, string> = {
  promote: "bg-emerald-50 text-emerald-800 border-emerald-300",
  reject: "bg-red-50 text-red-800 border-red-300",
  hold: "bg-slate-100 text-slate-700 border-slate-300",
};

function engineLabel(d: Design, payloadEngine?: string): string {
  const raw = `${d.generator || ""} ${payloadEngine || ""} ${d.fold_method || ""} ${d.provenance || ""}`.toLowerCase();
  if (raw.includes("bindcraft")) return "BindCraft (Tamarind)";
  if (raw.includes("sequence_design") || raw.includes("heuristic"))
    return "heuristic generator — not RFdiffusion";
  if (d.provenance === "fixture" || payloadEngine === "fixture") return "fixture";
  return d.generator || payloadEngine || d.provenance || "unknown";
}

function truncateSeq(seq: string, n = 28): string {
  if (seq.length <= n) return seq;
  return `${seq.slice(0, n)}…`;
}

function verdictFor(verdicts: VerdictItem[], id: string) {
  return verdicts.find((v) => v.subject_kind === "design" && v.subject_id === id);
}

function deltaFor(deltas: DesignDelta[] | undefined, id: string) {
  return deltas?.find((d) => d.id === id);
}

export default function DesignTable({
  designs,
  verdicts,
  deltas,
  rejectOnly = false,
  title,
  designEngine,
}: DesignTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = designs.filter((d) => {
    const v = verdictFor(verdicts, d.id);
    if (rejectOnly) return v?.verdict === "reject";
    return true;
  });

  if (rows.length === 0) {
    return (
      <p className="py-4 text-xs text-slate-400">
        {rejectOnly ? "No rejected designs in this run." : "No designs."}
      </p>
    );
  }

  return (
    <div>
      {title && (
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {title}
        </h4>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-400">
              <th className="pb-2 pr-3 font-semibold">ID</th>
              <th className="pb-2 pr-3 font-semibold">Sequence</th>
              <th className="pb-2 pr-3 font-semibold">Len</th>
              <th className="pb-2 pr-3 font-semibold">pLDDT</th>
              <th className="pb-2 pr-3 font-semibold">Engine</th>
              <th className="pb-2 pr-3 font-semibold">WT / mutant</th>
              <th className="pb-2 font-semibold">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => {
              const v = verdictFor(verdicts, d.id);
              const delta = deltaFor(deltas, d.id);
              const open = expanded === d.id;
              const mutantEntries = delta
                ? Object.entries(delta.mutant_scores || {})
                : [];
              const mutantStr =
                mutantEntries.length > 0
                  ? mutantEntries
                      .map(([k, val]) => `${k}:${val ?? "—"}`)
                      .join(" ")
                  : "—";

              return (
                <Fragment key={d.id}>
                  <tr
                    className={`cursor-pointer border-b border-slate-100 transition-colors hover:bg-slate-50/80 ${
                      v?.verdict === "reject" ? "bg-red-50/30" : ""
                    } ${v?.verdict === "promote" ? "bg-emerald-50/40" : ""}`}
                    onClick={() => setExpanded(open ? null : d.id)}
                  >
                    <td className="py-2.5 pr-3 font-mono font-medium text-slate-900">
                      {d.id}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-slate-600">
                      {truncateSeq(d.sequence)}
                    </td>
                    <td className="py-2.5 pr-3 text-slate-700">{d.length}</td>
                    <td className="py-2.5 pr-3 font-mono text-slate-700">
                      {d.plddt != null ? d.plddt.toFixed(1) : "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-[10px] text-slate-600">
                      {engineLabel(d, designEngine)}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[10px] text-slate-600">
                      {delta?.wt_score != null ? delta.wt_score : "—"} / {mutantStr}
                    </td>
                    <td className="py-2.5">
                      {v ? (
                        <span
                          className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${VERDICT_BADGE[v.verdict]}`}
                        >
                          {v.verdict}
                        </span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-slate-100 bg-slate-50/60">
                      <td colSpan={7} className="px-3 py-3">
                        <div className="space-y-2">
                          <div>
                            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                              FASTA
                            </div>
                            <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-slate-700">
                              {`>${d.id}\n${d.sequence}`}
                            </pre>
                          </div>
                          <p className="text-[11px] text-slate-600">
                            Engine: {engineLabel(d, designEngine)}
                            {d.fold_method ? ` · fold_method=${d.fold_method}` : ""}
                            {d.provenance ? ` · provenance=${d.provenance}` : ""}
                          </p>
                          {v && (
                            <div>
                              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                Critic
                              </div>
                              <p className="text-xs leading-relaxed text-slate-700">
                                {v.summary}
                              </p>
                              {v.reasons?.length > 0 && (
                                <div className="mt-1.5 flex flex-wrap gap-1">
                                  {v.reasons.map((r) => (
                                    <span
                                      key={r}
                                      className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-600"
                                    >
                                      {r}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {v.remaining_risk && (
                                <p className="mt-2 text-[11px] text-amber-800">
                                  Remaining risk: {v.remaining_risk}
                                </p>
                              )}
                            </div>
                          )}
                          {delta?.note && (
                            <p className="mt-1 text-[11px] text-slate-500">{delta.note}</p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] text-slate-400">
        Click a row for full sequence and critic text. Rejected designs stay visible.
      </p>
    </div>
  );
}
