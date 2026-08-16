"use client";

import type { Design, DesignDelta, VerdictItem } from "@/lib/types";
import DesignTable from "@/components/DesignTable";

interface CandidateReviewPanelProps {
  designs: Design[];
  verdicts: VerdictItem[];
  deltas?: DesignDelta[];
  designEngine?: string;
  selectedId?: string | null;
  onSelectDesign?: (id: string) => void;
}

function CountCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-xs">
      <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{label}</p>
      <p className={`mt-0.5 font-mono text-xl font-bold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}

export default function CandidateReviewPanel({
  designs,
  verdicts,
  deltas,
  designEngine,
  selectedId,
  onSelectDesign,
}: CandidateReviewPanelProps) {
  const designVerdicts = verdicts.filter((item) => item.subject_kind === "design");
  const promoted = designVerdicts.filter((item) => item.verdict === "promote").length;
  const held = designVerdicts.filter((item) => item.verdict === "hold").length;
  const rejected = designVerdicts.filter((item) => item.verdict === "reject").length;
  const selected = designs.find((design) => design.id === selectedId);

  if (designs.length === 0) return null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-1">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-slate-950">Candidate review</h2>
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">
              {designs.length} sequences
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Select any row to inspect its sequence, critic reasons, metrics, and 3D context below.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-indigo-500" /> selected</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500" /> rejected</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CountCard label="Selected" value={selected ? 1 : 0} tone="text-indigo-700" />
        <CountCard label="Promoted" value={promoted} tone="text-emerald-700" />
        <CountCard label="Held" value={held} tone="text-amber-700" />
        <CountCard label="Rejected" value={rejected} tone="text-rose-700" />
      </div>

      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/60 p-3">
        <DesignTable
          designs={designs}
          verdicts={verdicts}
          deltas={deltas}
          designEngine={designEngine}
          selectedId={selectedId}
          onSelectDesign={onSelectDesign}
        />
      </div>
    </section>
  );
}
