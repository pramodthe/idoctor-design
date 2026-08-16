"use client";

import type {
  AgentTrace,
  Design,
  EvalPayload,
  VerdictItem,
} from "@/lib/types";
import {
  Gauge,
  HorizontalBars,
  StackedBars,
  VerdictPills,
  type BarDatum,
  type StackedBarDatum,
} from "@/components/charts";

interface RunMetricsProps {
  designs: Design[];
  verdicts: VerdictItem[];
  evalData?: EvalPayload | null;
  traces?: AgentTrace[];
}

export default function RunMetrics({
  designs,
  verdicts,
  evalData,
  traces = [],
}: RunMetricsProps) {
  const designVerdicts = verdicts.filter((v) => v.subject_kind === "design");
  const promote = designVerdicts.filter((v) => v.verdict === "promote").length;
  const reject = designVerdicts.filter((v) => v.verdict === "reject").length;
  const hold = designVerdicts.filter((v) => v.verdict === "hold").length;

  const plddtBars: BarDatum[] = designs
    .filter((d) => d.plddt != null)
    .slice(0, 8)
    .map((d) => {
      const v = designVerdicts.find((x) => x.subject_id === d.id);
      return {
        id: d.id,
        label: d.id,
        value: d.plddt as number,
        tone:
          v?.verdict === "promote"
            ? "promote"
            : v?.verdict === "reject"
              ? "reject"
              : "accent",
      };
    });

  const durationBars: BarDatum[] = traces.map((t) => ({
    id: t.agent,
    label: t.agent_name?.split(" (")[0] || t.agent,
    value: Number(t.duration_seconds?.toFixed?.(1) ?? t.duration_seconds ?? 0),
    tone: "accent",
  }));

  const deltaStacks: StackedBarDatum[] = (evalData?.design_deltas || [])
    .slice(0, 8)
    .map((d) => {
      const mutants = Object.values(d.mutant_scores || {}).filter(
        (x): x is number => typeof x === "number"
      );
      const mutantAvg =
        mutants.length > 0
          ? mutants.reduce((a, b) => a + b, 0) / mutants.length
          : 0;
      return {
        id: d.id,
        label: d.id.replace(/^des_/, ""),
        segments: [
          {
            key: "wt",
            value: Math.abs(d.wt_score ?? 0),
            color: "#2563eb",
          },
          {
            key: "mut",
            value: Math.abs(mutantAvg),
            color: "#f472b6",
          },
        ],
      };
    });

  const rho = evalData?.smallmol_spearman_rho;
  const rhoGood = rho == null || rho >= 0.3;

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <div className="soft-card rounded-2xl p-4 lg:col-span-4">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              Design confidence
            </h3>
            <p className="text-[11px] text-slate-500">pLDDT by design</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-center">
            <div className="text-[9px] font-semibold uppercase text-emerald-700">
              Promoted
            </div>
            <div className="font-display text-xl font-semibold text-emerald-800">
              {promote}
            </div>
          </div>
        </div>
        <HorizontalBars data={plddtBars} max={100} />
      </div>

      <div className="soft-card rounded-2xl p-4 lg:col-span-4">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              WT vs mutant signal
            </h3>
            <p className="text-[11px] text-slate-500">
              Absolute score magnitude (control)
            </p>
          </div>
          <div className="flex gap-2 text-[10px]">
            <span className="flex items-center gap-1 text-slate-500">
              <span className="h-2 w-2 rounded-sm bg-blue-600" /> WT
            </span>
            <span className="flex items-center gap-1 text-slate-500">
              <span className="h-2 w-2 rounded-sm bg-pink-400" /> Mutant
            </span>
          </div>
        </div>
        <StackedBars data={deltaStacks} height={150} />
        {deltaStacks.length === 0 && (
          <p className="mt-2 text-center text-[11px] text-slate-400">
            No design deltas on this run
          </p>
        )}
      </div>

      <div className="flex flex-col gap-4 lg:col-span-4">
        <div className="grid grid-cols-2 gap-3">
          <Gauge
            label="Spearman ρ"
            value={rho != null ? rho.toFixed(2) : "—"}
            detail={
              evalData?.smallmol_n
                ? `n=${evalData.smallmol_n} Vina vs Ki`
                : "Docking control"
            }
            good={rhoGood}
          />
          <div className="soft-card rounded-2xl px-4 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Critic mix
            </div>
            <div className="mt-3">
              <VerdictPills promote={promote} reject={reject} hold={hold} />
            </div>
          </div>
        </div>
        <div className="soft-card flex-1 rounded-2xl p-4">
          <h3 className="mb-1 text-sm font-semibold text-slate-900">
            Agent runtime
          </h3>
          <p className="mb-3 text-[11px] text-slate-500">Seconds per node</p>
          <HorizontalBars data={durationBars.slice(0, 7)} unit="s" height={120} />
        </div>
      </div>
    </div>
  );
}
