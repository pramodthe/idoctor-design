"use client";

import type { LoopHistoryPayload, LoopIteration } from "@/lib/types";

interface LoopHistoryPanelProps {
  history?: LoopHistoryPayload;
}

function routeLabel(round: LoopIteration): string {
  if (round.route === "redesign") return "critic → redesign";
  if (round.decision_reason === "promoted") return "promoted → handoff";
  return "critic → handoff";
}

function routeClass(round: LoopIteration): string {
  if (round.route === "redesign") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  if (round.decision_reason === "promoted") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

export default function LoopHistoryPanel({ history }: LoopHistoryPanelProps) {
  const rounds = history?.iterations || [];
  if (!rounds.length) return null;

  const latest = rounds[rounds.length - 1];
  const maxScore = Math.max(1, ...rounds.map((round) => round.progress_score));
  const maxIterations = history?.max_iterations || rounds.length;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-1">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-950">Verification loop</h2>
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">
              {rounds.length}/{maxIterations} rounds
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Every retry starts from the critic&apos;s structured failures and is re-verified by the full evidence panel.
          </p>
        </div>
        <div className="text-right">
          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">Latest route</p>
          <span className={`mt-1 inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${routeClass(latest)}`}>
            {routeLabel(latest)}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-2 lg:grid-cols-3">
        {rounds.map((round) => {
          const feedback = round.redesign_feedback;
          const scoreWidth = Math.max(4, Math.min(100, (round.progress_score / maxScore) * 100));
          return (
            <article key={round.iteration} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.13em] text-slate-400">Round {round.iteration}</p>
                  <p className="mt-1 font-mono text-[11px] text-slate-700">
                    {round.design_ids.length} candidate{round.design_ids.length === 1 ? "" : "s"}
                  </p>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${routeClass(round)}`}>
                  {round.route === "redesign" ? "retry" : "stop"}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between text-[10px]">
                <span className="font-semibold text-slate-500">progress score</span>
                <span className="font-mono font-bold text-slate-800">{round.progress_score.toFixed(2)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
                <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${scoreWidth}%` }} />
              </div>

              <div className="mt-3 flex flex-wrap gap-1">
                <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-800">{round.counts.promote} promote</span>
                <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800">{round.counts.hold} hold</span>
                <span className="rounded-md bg-rose-100 px-1.5 py-0.5 text-[9px] font-semibold text-rose-800">{round.counts.reject} reject</span>
              </div>

              {round.reason_codes.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {round.reason_codes.map((reason) => (
                    <span key={reason} className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[9px] text-slate-600">{reason}</span>
                  ))}
                </div>
              )}

              <p className="mt-3 text-[10px] leading-relaxed text-slate-500">
                {round.improved ? "Improved over the previous best." : `${round.no_improvement_rounds} no-improvement round${round.no_improvement_rounds === 1 ? "" : "s"}.`} {round.decision_reason.replaceAll("_", " ")}.
              </p>
              {feedback?.instructions && round.route === "redesign" && (
                <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-2.5 py-2 text-[10px] leading-relaxed text-amber-900">
                  <span className="font-bold">Designer brief:</span> {feedback.instructions}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
