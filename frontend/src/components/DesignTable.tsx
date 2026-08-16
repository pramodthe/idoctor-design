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
  selectedId?: string | null;
  onSelectDesign?: (id: string) => void;
}

const VERDICT_BADGE: Record<string, string> = {
  promote: "bg-emerald-50 text-emerald-700 border-emerald-200",
  reject: "bg-red-50 text-red-700 border-red-200",
  hold: "bg-slate-100 text-slate-700 border-slate-200",
};

function engineLabel(d: Design, payloadEngine?: string): string {
  const raw = `${d.generator || ""} ${payloadEngine || ""} ${d.fold_method || ""} ${d.provenance || ""}`.toLowerCase();
  if (raw.includes("bindcraft")) return "BindCraft (Tamarind)";
  // Structure-based, but single-shot: no BindCraft acceptance filters were applied,
  // so this must never render as BindCraft.
  if (raw.includes("esmfold2-binder-design"))
    return "ESMFold2 binder design (Tamarind) — not filter-passed";
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
  selectedId = null,
  onSelectDesign,
}: DesignTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = designs.filter((d) => {
    const v = verdictFor(verdicts, d.id);
    if (rejectOnly) return v?.verdict === "reject";
    return true;
  });

  if (rows.length === 0) {
    return (
      <p className="py-4 text-xs text-slate-500">
        {rejectOnly ? "No rejected designs in this run." : "No designs."}
      </p>
    );
  }

  return (
    <div>
      {title && (
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {title}
        </h4>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-500">
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
                    className={`cursor-pointer border-b border-slate-200/60 transition-colors hover:bg-slate-50 ${
                      v?.verdict === "reject" ? "bg-red-50/80" : ""
                    } ${v?.verdict === "promote" ? "bg-emerald-50/80" : ""} ${selectedId === d.id ? "bg-indigo-50/90 ring-1 ring-inset ring-indigo-200" : ""}`}
                    onClick={() => {
                      setExpanded(open ? null : d.id);
                      onSelectDesign?.(d.id);
                    }}
                  >
                    <td className={`py-2.5 pr-3 font-mono font-medium text-slate-800 ${selectedId === d.id ? "border-l-2 border-indigo-500 pl-2" : ""}`}>
                      <span className="inline-flex items-center gap-1.5">
                        {d.id}
                        {selectedId === d.id && (
                          <span className="rounded bg-indigo-600 px-1 py-0.5 font-sans text-[8px] font-bold uppercase tracking-wider text-white">focus</span>
                        )}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-slate-400">
                      {truncateSeq(d.sequence)}
                    </td>
                    <td className="py-2.5 pr-3 text-slate-700">{d.length}</td>
                    <td className="py-2.5 pr-3 font-mono text-slate-700">
                      {d.plddt != null ? d.plddt.toFixed(1) : "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-[10px] text-slate-400">
                      {engineLabel(d, designEngine)}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[10px] text-slate-400">
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
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-slate-200/60 bg-slate-50">
                      <td colSpan={7} className="px-3 py-3">
                        <div className="space-y-2">
                          <div>
                            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                              FASTA
                            </div>
                            <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-blue-700">
                              {`>${d.id}\n${d.sequence}`}
                            </pre>
                          </div>
                          <p className="text-[11px] text-slate-400">
                            Engine: {engineLabel(d, designEngine)}
                            {d.fold_method ? ` · fold_method=${d.fold_method}` : ""}
                            {d.provenance ? ` · provenance=${d.provenance}` : ""}
                          </p>
                          {v && (
                            <div>
                              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
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
                                      className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
                                    >
                                      {r}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {v.remaining_risk && (
                                <p className="mt-2 text-[11px] text-amber-700">
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
      <p className="mt-2 text-[10px] text-slate-500">
        Click a row for full sequence and critic text. Rejected designs stay visible.
      </p>
    </div>
  );
}
