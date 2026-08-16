"use client";

import type {
  AgentStatusMap,
  AgentName,
  ProvenancePayload,
} from "@/lib/types";
import { AGENT_DISPLAY_NAMES } from "@/lib/types";

interface AgentStatusPanelProps {
  agentStatus: AgentStatusMap;
  currentStep?: string | null;
  /** Per-node live/fixture/cached stamps — drives the demo-data banner. */
  provenance?: ProvenancePayload;
}

const AGENT_KEYS: AgentName[] = [
  "evidence",
  "designer",
  "structure",
  "physics",
  "evaluate",
  "critic",
  "experiment",
];

const DESCRIPTIONS: Record<AgentName, string> = {
  evidence: "Paperclip → mutation table and scientific spec",
  designer:
    "BindCraft on Tamarind if a finished campaign is on disk; else heuristic sequence_design — not RFdiffusion unless provenance says bindcraft",
  structure: "Tamarind → fold and complex confidence",
  physics: "AutoDock Vina → small-molecule control arm",
  evaluate: "Compare docking ranks to known Ki",
  critic: "Claude → promote, hold, or reject with reasons",
  experiment: "Monday wet-lab card for the survivor",
};

export default function AgentStatusPanel({
  agentStatus,
  currentStep,
  provenance,
}: AgentStatusPanelProps) {
  const completedCount = Object.values(agentStatus).filter(
    (s) => s === "completed"
  ).length;
  const progress = (completedCount / AGENT_KEYS.length) * 100;
  const nodeVals = Object.values(provenance?.nodes || {});
  const hasFixtureNode = nodeVals.some((n) => n === "fixture");
  const isDemo =
    !provenance ||
    provenance.mode === "fixture" ||
    provenance.mode === "replay" ||
    hasFixtureNode;

  return (
    <div className="border border-slate-200 bg-white p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Agent pipeline
        </h3>
        <span className="text-xs text-slate-400">
          {completedCount}/{AGENT_KEYS.length}
        </span>
      </div>

      <div className="mb-5 h-1 overflow-hidden bg-slate-100">
        <div
          className="relative h-full bg-teal-600 transition-all duration-700"
          style={{ width: `${progress}%` }}
        >
          <div className="shimmer-bar absolute inset-0" />
        </div>
      </div>

      {isDemo && (
        <div className="demo-banner mb-4 border-2 border-amber-500 bg-amber-50 px-3 py-2 text-[11px] font-semibold text-amber-950">
          Demo data / fixture provenance
          {provenance ? (
            <>
              {" "}
              — mode{" "}
              <span className="font-mono">{provenance.mode}</span>
              {hasFixtureNode && " (one or more nodes are fixture)"}. Do not
              treat heuristic folds or sequence_design as RFdiffusion/BindCraft.
            </>
          ) : (
            <> — provenance not loaded yet.</>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        {AGENT_KEYS.map((key) => {
          const status = agentStatus[key];
          const isRunning = status === "running";
          const isCompleted = status === "completed";

          return (
            <div
              key={key}
              className={`relative overflow-hidden border px-3 py-2.5 transition-all duration-300 ${
                isRunning
                  ? "border-teal-300 bg-teal-50/80"
                  : isCompleted
                    ? "border-emerald-200 bg-emerald-50/40"
                    : "border-slate-100 bg-slate-50/40"
              }`}
            >
              {isRunning && (
                <div className="absolute inset-0 overflow-hidden">
                  <div className="scan-line absolute inset-x-0 h-8 bg-gradient-to-b from-transparent via-teal-100/50 to-transparent" />
                </div>
              )}

              <div className="relative flex items-center gap-3">
                <div
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded ${
                    isRunning
                      ? "bg-teal-200/80"
                      : isCompleted
                        ? "bg-emerald-100"
                        : "bg-slate-100"
                  }`}
                >
                  {isCompleted ? (
                    <svg
                      className="h-3 w-3 text-emerald-700"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={3}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        isRunning ? "animate-pulse bg-teal-600" : "bg-slate-300"
                      }`}
                    />
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`text-sm font-medium ${
                        isRunning
                          ? "text-teal-900"
                          : isCompleted
                            ? "text-emerald-900"
                            : "text-slate-400"
                      }`}
                    >
                      {AGENT_DISPLAY_NAMES[key]}
                    </span>
                    {isRunning && (
                      <div className="flex items-center gap-1">
                        <div className="h-1 w-1 animate-pulse rounded-full bg-teal-500" />
                        <div
                          className="h-1 w-1 animate-pulse rounded-full bg-teal-500"
                          style={{ animationDelay: "0.2s" }}
                        />
                        <div
                          className="h-1 w-1 animate-pulse rounded-full bg-teal-500"
                          style={{ animationDelay: "0.4s" }}
                        />
                      </div>
                    )}
                  </div>
                  {isRunning && (
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {currentStep || DESCRIPTIONS[key]}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
