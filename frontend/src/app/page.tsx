"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentStatus,
  AgentStatusMap,
  AppState,
  IDoctorDesignResults,
  LabLogEvent,
  RunMode,
} from "@/lib/types";
import { INITIAL_AGENT_STATUS } from "@/lib/types";
import {
  downloadBlob,
  getProteinPDB,
  loadFixtureResults,
  loadLatestRun,
  runWithFixtureFallback,
} from "@/lib/api";
import AgentLineage from "@/components/AgentLineage";
import AppShell from "@/components/AppShell";
import ComplexResultsPanel from "@/components/ComplexResultsPanel";
import ExperimentCard from "@/components/ExperimentCard";
import Header from "@/components/Header";
import LabLog from "@/components/LabLog";
import { tracesToLabLog } from "@/lib/labLog";

const DEFAULT_PDB = "6OIM";

function completedAgentMap(): AgentStatusMap {
  return Object.fromEntries(
    (Object.keys(INITIAL_AGENT_STATUS) as (keyof AgentStatusMap)[]).map((agent) => [
      agent,
      "completed" as AgentStatus,
    ])
  ) as unknown as AgentStatusMap;
}

export default function Home() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [agentStatus, setAgentStatus] = useState<AgentStatusMap>(INITIAL_AGENT_STATUS);
  const [results, setResults] = useState<IDoctorDesignResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dataNotice, setDataNotice] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [targetPdb, setTargetPdb] = useState<string | null>(null);
  const [labLog, setLabLog] = useState<LabLogEvent[]>([]);
  const [activeMode, setActiveMode] = useState<RunMode | null>(null);
  const [copiedSeq, setCopiedSeq] = useState(false);
  const runGeneration = useRef(0);

  const applyResults = useCallback((loaded: IDoctorDesignResults) => {
    setResults(loaded);
    setAgentStatus(completedAgentMap());
    setActiveMode(loaded.provenance?.mode || "fixture");
    setLabLog(
      loaded.lab_log?.length ? loaded.lab_log : tracesToLabLog(loaded.agent_traces)
    );
    setAppState("completed");
    setCurrentStep(null);
  }, []);

  useEffect(() => {
    getProteinPDB(DEFAULT_PDB).then(setTargetPdb).catch(() => setTargetPdb(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initData() {
      try {
        const latest = await loadLatestRun();
        if (cancelled) return;
        if (latest) {
          applyResults(latest);
          setDataNotice(null);
          return;
        }
        const fixture = await loadFixtureResults();
        if (cancelled) return;
        applyResults(fixture);
        setDataNotice("No saved run was found. Showing the demo fixture explicitly.");
      } catch {
        const fixture = await loadFixtureResults();
        if (cancelled) return;
        applyResults(fixture);
        setDataNotice(
          "Backend is offline, so this is demo fixture data—not a live scientific result. Start FastAPI on port 8080 and load the latest run."
        );
      }
    }
    void initData();
    return () => {
      cancelled = true;
    };
  }, [applyResults]);

  const handleRun = useCallback(
    async (mode: RunMode) => {
      const generation = ++runGeneration.current;
      setAppState("running");
      setError(null);
      setDataNotice(null);
      setResults(null);
      setAgentStatus(INITIAL_AGENT_STATUS);
      setCurrentStep(null);
      setLabLog([]);
      setActiveMode(mode);

      try {
        const run = await runWithFixtureFallback(
          mode,
          (agent, status) => {
            if (generation !== runGeneration.current) return;
            setAgentStatus((previous) => {
              if (!(agent in previous)) return previous;
              return { ...previous, [agent]: status as AgentStatus };
            });
          },
          (step) => {
            if (generation === runGeneration.current) setCurrentStep(step);
          },
          (events) => {
            if (generation === runGeneration.current) setLabLog(events);
          }
        );
        if (generation !== runGeneration.current) return;
        applyResults(run);
      } catch (runError) {
        if (generation !== runGeneration.current) return;
        setError(
          runError instanceof Error ? runError.message : "The pipeline could not be started."
        );
        setAppState("idle");
      }
    },
    [applyResults]
  );

  const handleLoadLatest = useCallback(async () => {
    setError(null);
    setDataNotice(null);
    setCurrentStep("Loading latest saved run…");
    setAppState("running");
    try {
      const latest = await loadLatestRun();
      if (!latest) throw new Error("No complete saved run is available.");
      applyResults(latest);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Could not reach the iDoctor backend."
      );
      setAppState(results ? "completed" : "idle");
      setCurrentStep(null);
    }
  }, [applyResults, results]);

  const handleReset = useCallback(() => {
    runGeneration.current += 1;
    setAppState("idle");
    setResults(null);
    setAgentStatus(INITIAL_AGENT_STATUS);
    setError(null);
    setDataNotice(null);
    setCurrentStep(null);
    setLabLog([]);
    setActiveMode(null);
  }, []);

  function handleDownloads() {
    if (!results) return;
    const stem = results.run_id || "idoctor";
    downloadBlob(JSON.stringify(results.scientific_spec, null, 2), `${stem}-spec.json`, "application/json");
    const fasta = (results.designs?.designs || [])
      .map((design) => `>${design.id}\n${design.sequence}`)
      .join("\n");
    downloadBlob(fasta, `${stem}-designs.fasta`, "text/plain");
    downloadBlob(JSON.stringify(results.verdicts, null, 2), `${stem}-verdicts.json`, "application/json");
    downloadBlob(JSON.stringify(results.complex_scores || {}, null, 2), `${stem}-complex-scores.json`, "application/json");
  }

  const designs = results?.designs?.designs || [];
  const allVerdicts = results?.verdicts?.items || [];
  const designVerdicts = allVerdicts.filter((item) => item.subject_kind === "design");
  const promotedIds = new Set(
    designVerdicts.filter((item) => item.verdict === "promote").map((item) => item.subject_id)
  );
  const promotedDesigns = designs.filter((design) => promotedIds.has(design.id));
  const rejectedDesigns = designs.filter((design) =>
    designVerdicts.some((item) => item.subject_id === design.id && item.verdict === "reject")
  );
  const heldDesigns = designs.filter((design) =>
    designVerdicts.some((item) => item.subject_id === design.id && item.verdict === "hold")
  );
  const focusDesign = promotedDesigns[0] || designs[0];
  const focusVerdict = designVerdicts.find((item) => item.subject_id === focusDesign?.id);
  const bestIptm = Math.max(
    ...designs
      .map((design) => design.iptm)
      .filter((value): value is number => typeof value === "number"),
    0
  );
  const liveNodes = Object.values(results?.provenance?.nodes || {}).filter(
    (node) => node === "live" || node === "cached"
  ).length;
  const termination =
    results?.loop_termination_reason || results?.verdicts?.loop?.termination_reason;
  const runRejected = focusVerdict?.verdict === "reject";
  const runPromoted = promotedDesigns.length > 0;
  const pocketResidues =
    results?.scientific_spec?.pocket_residues || ["Cys12", "His95", "Tyr96", "Asp69"];
  const headline = runPromoted
    ? `${promotedDesigns.length} candidate${promotedDesigns.length === 1 ? "" : "s"} cleared every gate`
    : runRejected
      ? "Candidate falsified by the resistance panel"
      : appState === "running"
        ? "The AI scientist is collecting evidence"
        : "No candidate has cleared the promotion gates";

  return (
    <AppShell
      topBar={
        <Header
          appState={appState}
          mode={results?.provenance?.mode || activeMode}
          spec={results?.scientific_spec}
          runId={results?.run_id}
          agentStatus={agentStatus}
          currentStep={currentStep}
          labLog={labLog}
          onRunLive={() => void handleRun("live")}
          onRunFixture={() => void handleRun("fixture")}
          onLoadLatest={() => void handleLoadLatest()}
          onDownload={handleDownloads}
          onReset={handleReset}
          canDownload={Boolean(results)}
        />
      }
    >
      <div className="mx-auto max-w-[1680px] space-y-4">
        {dataNotice && (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-900 shadow-sm">
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" />
            <div><strong className="font-bold">Data source warning.</strong> {dataNotice}</div>
          </div>
        )}
        {error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-800 shadow-sm">
            {error}
          </div>
        )}

        <section className={`overflow-hidden rounded-3xl border p-5 shadow-sm ${
          runPromoted
            ? "border-emerald-200 bg-gradient-to-br from-emerald-50 to-white"
            : runRejected
              ? "border-rose-200 bg-gradient-to-br from-rose-50 via-white to-amber-50/40"
              : "border-slate-200 bg-white"
        }`}>
          <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr] xl:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${
                  runPromoted ? "bg-emerald-600 text-white" : runRejected ? "bg-rose-600 text-white" : "bg-slate-900 text-white"
                }`}>
                  {runPromoted ? "promoted" : runRejected ? "rejected" : appState}
                </span>
                {results?.provenance?.mode && (
                  <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-600">
                    {results.provenance.mode} evidence
                  </span>
                )}
                {results?.checkpointed && (
                  <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[10px] font-bold text-indigo-700">
                    resumable checkpoint
                  </span>
                )}
              </div>
              <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-950 xl:text-3xl">{headline}</h1>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
                {focusVerdict?.summary || currentStep || results?.hypothesis || "Load a run to inspect every model, tool call, structure, and critic decision."}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {(focusVerdict?.reasons || []).map((reason) => (
                  <span key={reason} className="rounded-lg border border-rose-200 bg-white px-2 py-1 font-mono text-[10px] font-semibold text-rose-700">{reason}</span>
                ))}
                {termination && (
                  <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono text-[10px] text-slate-600">stop: {termination}</span>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-2">
              <SummaryMetric label="Promoted" value={String(promotedDesigns.length)} detail={`${rejectedDesigns.length} reject · ${heldDesigns.length} hold`} />
              <SummaryMetric label="Best ipTM" value={bestIptm ? bestIptm.toFixed(2) : "—"} detail={`bar ≥ ${(results?.scientific_spec?.success_bars?.min_iptm ?? 0.75).toFixed(2)}`} />
              <SummaryMetric label="Evidence nodes" value={`${liveNodes}/9`} detail="live or validated cache" />
              <SummaryMetric label="Oracle ρ" value={results?.eval?.smallmol_spearman_rho?.toFixed(2) || "—"} detail={`n=${results?.eval?.smallmol_n || 0} controls`} />
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-1">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-950">Autonomous scientist workflow</h2>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">9 agents</span>
              </div>
              <p className="mt-0.5 text-[11px] text-slate-500">Click any node for tools, provenance, model calls, and output summaries.</p>
            </div>
            <span className="font-mono text-[10px] text-slate-400">{results?.run_id || currentStep || "no run loaded"}</span>
          </div>
          <div className="h-[430px] overflow-hidden rounded-2xl border border-slate-100 bg-slate-50/70">
            <AgentLineage
              agentStatus={agentStatus}
              currentStep={currentStep}
              provenance={results?.provenance}
              traces={results?.agent_traces}
              labLog={labLog}
              verdicts={allVerdicts}
              designs={designs}
              compounds={results?.smallmol?.compounds}
              loopHistory={results?.loop_history}
              className="h-full"
            />
          </div>
        </section>

        <ComplexResultsPanel
          design={focusDesign}
          successBars={results?.scientific_spec?.success_bars}
          bindingResidues={pocketResidues}
          fallbackPdbData={targetPdb}
        />

        <div className="grid gap-4 xl:grid-cols-12">
          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-950">Candidate decision</h2>
                <p className="mt-0.5 text-[11px] text-slate-500">The exact sequence and evidence used by the critic</p>
              </div>
              {focusVerdict && (
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${
                  focusVerdict.verdict === "promote"
                    ? "bg-emerald-100 text-emerald-800"
                    : focusVerdict.verdict === "reject"
                      ? "bg-rose-100 text-rose-800"
                      : "bg-amber-100 text-amber-800"
                }`}>{focusVerdict.verdict}</span>
              )}
            </div>
            {focusDesign ? (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-sm font-bold text-slate-900">{focusDesign.id}</span>
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard.writeText(focusDesign.sequence);
                      setCopiedSeq(true);
                      setTimeout(() => setCopiedSeq(false), 1600);
                    }}
                    className="rounded-lg border border-slate-200 px-2.5 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50"
                  >
                    {copiedSeq ? "Copied ✓" : "Copy FASTA"}
                  </button>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  <TinyMetric label="Length" value={`${focusDesign.length} aa`} />
                  <TinyMetric label="pLDDT" value={focusDesign.plddt?.toFixed(1) || "—"} />
                  <TinyMetric label="ipTM" value={focusDesign.iptm?.toFixed(2) || "—"} />
                  <TinyMetric label="PDB identity" value={focusDesign.novelty?.identity != null ? `≤${focusDesign.novelty.identity}` : "—"} />
                </div>
                <div className="rounded-xl bg-slate-950 p-3 font-mono text-[10px] leading-relaxed text-slate-200">
                  <span className="break-all">{focusDesign.sequence}</span>
                </div>
                {focusVerdict && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs leading-relaxed text-slate-700">{focusVerdict.summary}</p>
                    {focusVerdict.remaining_risk && (
                      <p className="mt-2 text-[10px] leading-relaxed text-slate-500"><strong>Remaining risk:</strong> {focusVerdict.remaining_risk}</p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-4 text-xs text-slate-500">No candidate loaded.</p>
            )}
          </section>

          <section className="xl:col-span-4">
            <LabLog events={labLog} live={appState === "running"} />
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-slate-950">Experiment handoff</h2>
                <p className="mt-0.5 text-[11px] text-slate-500">Wet-lab boundary, never an automatic order</p>
              </div>
              <span className={`rounded-full px-2 py-1 text-[9px] font-bold uppercase ${
                runPromoted ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
              }`}>{runPromoted ? "review" : "stop"}</span>
            </div>
            <div className="mt-4 max-h-[340px] overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3">
              <ExperimentCard markdown={results?.experiment_md || "# No experiment generated"} />
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function SummaryMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-white/80 bg-white/80 px-3 py-3 shadow-xs backdrop-blur">
      <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">{label}</p>
      <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-950">{value}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">{detail}</p>
    </div>
  );
}

function TinyMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-2 text-center">
      <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 font-mono text-xs font-bold text-slate-800">{value}</p>
    </div>
  );
}
