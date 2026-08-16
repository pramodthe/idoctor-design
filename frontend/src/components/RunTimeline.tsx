"use client";

import type { AgentName, AgentStatusMap } from "@/lib/types";
import { AGENT_DISPLAY_NAMES } from "@/lib/types";

const STAGES: AgentName[] = [
  "evidence",
  "designer",
  "structure",
  "novelty",
  "complex",
  "physics",
  "evaluate",
  "critic",
  "experiment",
];

interface RunTimelineProps {
  agentStatus: AgentStatusMap;
  currentStep?: string | null;
  mode?: string | null;
}

export default function RunTimeline({
  agentStatus,
  currentStep,
  mode,
}: RunTimelineProps) {
  const activeIdx = STAGES.findIndex((s) => agentStatus[s] === "running");
  const completedCount = STAGES.filter((s) => agentStatus[s] === "completed").length;
  const progress =
    activeIdx >= 0
      ? ((activeIdx + 0.55) / STAGES.length) * 100
      : (completedCount / STAGES.length) * 100;

  return (
    <div className="soft-card rounded-2xl px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            Pipeline timeline
          </span>
          {mode && (
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-blue-700">
              {mode}
            </span>
          )}
        </div>
        <span className="truncate text-[11px] text-slate-500">
          {currentStep ||
            (completedCount === STAGES.length
              ? "Run complete — scrub stages below"
              : "Waiting to start…")}
        </span>
      </div>

      <div className="relative mb-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-blue-500 to-sky-400 transition-all duration-500"
          style={{ width: `${Math.min(100, Math.max(4, progress))}%` }}
        />
      </div>

      <div className="grid grid-cols-9 gap-1">
        {STAGES.map((stage) => {
          const st = agentStatus[stage];
          const short = AGENT_DISPLAY_NAMES[stage].split(" (")[0].split(" ")[0];
          return (
            <div
              key={stage}
              className={`rounded-xl px-1 py-2 text-center transition-all ${
                st === "running"
                  ? "bg-blue-600 text-white shadow-md shadow-blue-600/25"
                  : st === "completed"
                    ? "bg-emerald-50 text-emerald-800"
                    : "bg-slate-50 text-slate-400"
              }`}
            >
              <div className="mx-auto mb-1 h-1.5 w-1.5 rounded-full bg-current opacity-80" />
              <div className="truncate text-[9px] font-semibold uppercase tracking-wide">
                {short}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
