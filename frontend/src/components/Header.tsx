"use client";

import { useState } from "react";
import type {
  AgentStatusMap,
  AppState,
  LabLogEvent,
  ProvenanceMode,
  ScientificSpec,
} from "@/lib/types";

interface HeaderProps {
  appState: AppState;
  mode?: ProvenanceMode | string | null;
  partners?: string[];
  agentStatus?: AgentStatusMap;
  currentStep?: string | null;
  labLog?: LabLogEvent[];
  onRunLive?: () => void;
  onRunFixture?: () => void;
  onLoadLatest?: () => void;
  onDownload?: () => void;
  onReset?: () => void;
  canDownload?: boolean;
  spec?: ScientificSpec | null;
  runId?: string | null;
  viewMode?: "graph" | "split";
  onViewMode?: (mode: "graph" | "split") => void;
}

export default function Header({
  appState,
  mode,
  agentStatus,
  currentStep,
  labLog = [],
  onRunLive,
  onRunFixture,
  onLoadLatest,
  onDownload,
  onReset,
  canDownload,
  spec,
  runId,
}: HeaderProps) {
  const [loadOpen, setLoadOpen] = useState(false);
  const running = appState === "running";
  const completed = appState === "completed";

  const completedCount = agentStatus
    ? Object.values(agentStatus).filter((s) => s === "completed").length
    : 0;
  const target = spec?.target;
  const mutationIds = (spec?.mutations || []).slice(0, 3).map((m) => m.id);

  return (
    <header className="shrink-0 border-b border-slate-200/80 bg-white/90 px-6 py-3 shadow-xs backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Brand & Target Identification */}
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/20">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-slate-900">
                iDoctor Design
              </h1>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-700 ring-1 ring-blue-100">
                AI Scientist
              </span>
              {mode && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                  mode === "live"
                    ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                    : "bg-slate-100 text-slate-600"
                }`}>
                  {mode}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 font-medium">
              {runId ? `Run ${runId}` : "Resistance-aware protein design with inspectable evidence"}
            </p>
          </div>
        </div>

        {/* Center: Target & Pocket Metadata Pills */}
        <div className="hidden lg:flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-1.5 ring-1 ring-slate-200/70">
            <span className="text-xs font-semibold text-slate-500">Target Receptor:</span>
            <span className="font-mono text-xs font-bold text-slate-900">
              {target?.name || "KRAS G12C"} (PDB: {target?.pdb_id || "6OIM"})
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-xl bg-rose-50/80 px-3 py-1.5 ring-1 ring-rose-200/60">
            <span className="text-xs font-semibold text-rose-700">Resistance:</span>
            <span className="font-mono text-xs font-bold text-rose-900">
              {mutationIds.length ? mutationIds.join(" / ") : "Y96D / H95D"}
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-xl bg-emerald-50/80 px-3 py-1.5 ring-1 ring-emerald-200/60">
            <span className="text-xs font-semibold text-emerald-700">Strategy:</span>
            <span className="text-xs font-bold text-emerald-900">De Novo Miniprotein Binder</span>
          </div>
        </div>

        {/* Right: Pipeline Controls */}
        <div className="flex items-center gap-2">
          {/* Replay / Saved run dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setLoadOpen((v) => !v)}
              className="flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition-colors"
            >
              <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Load Data</span>
              <svg className="h-3 w-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {loadOpen && (
              <div className="absolute right-0 z-50 mt-1.5 w-52 overflow-hidden rounded-2xl bg-white p-1.5 shadow-xl ring-1 ring-black/10 backdrop-blur-xl animate-fade-in">
                <button
                  type="button"
                  onClick={() => { setLoadOpen(false); onLoadLatest?.(); }}
                  className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700"
                >
                  <span className="h-2 w-2 rounded-full bg-blue-500" />
                  Load Latest Saved Run
                </button>
                <button
                  type="button"
                  onClick={() => { setLoadOpen(false); onRunLive?.(); }}
                  className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:bg-emerald-50 hover:text-emerald-700"
                >
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Run Live API Pipeline
                </button>
                <button
                  type="button"
                  onClick={() => { setLoadOpen(false); onRunFixture?.(); }}
                  className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold text-slate-700 hover:bg-amber-50 hover:text-amber-700"
                >
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  Open Demo Fixture
                </button>
              </div>
            )}
          </div>

          {/* Reset button */}
          <button
            type="button"
            onClick={onReset}
            title="Reset to initial state"
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition-colors"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {/* Export button */}
          {canDownload && (
            <button
              type="button"
              onClick={onDownload}
              className="flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition-colors"
            >
              <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              <span>Export</span>
            </button>
          )}

          {/* Main Primary Run Button */}
          <button
            type="button"
            onClick={onRunLive}
            disabled={running}
            className="flex h-9 items-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-bold text-white shadow-md shadow-blue-600/20 hover:bg-blue-700 active:scale-95 disabled:opacity-50 transition-all cursor-pointer"
          >
            {running ? (
              <>
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <span>Designing ({completedCount}/9)...</span>
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                <span>{completed ? "Run New Live Campaign" : "Run Live Scientist"}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
