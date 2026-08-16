"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type {
  AppState,
  AgentStatusMap,
  IDoctorDesignResults,
  RunMode,
  AgentStatus,
} from "@/lib/types";
import { INITIAL_AGENT_STATUS } from "@/lib/types";
import {
  getProteinPDB,
  runWithFixtureFallback,
  downloadBlob,
  isDemoData,
  loadLatestRun,
} from "@/lib/api";
import Header from "@/components/Header";
import ProteinViewer from "@/components/ProteinViewer";
import AgentStatusPanel from "@/components/AgentStatusPanel";
import OnboardingModal from "@/components/OnboardingModal";
import MutationMap from "@/components/MutationMap";
import SmallMolTable from "@/components/SmallMolTable";
import DesignTable from "@/components/DesignTable";
import RejectDrawer from "@/components/RejectDrawer";
import ExperimentCard from "@/components/ExperimentCard";
import EvalPanel from "@/components/EvalPanel";

const DEFAULT_PDB = "6OIM";
const HYPOTHESIS_TEASER =
  "Switch II small-molecule drugs that work on KRAS G12C lose binding when pocket residues such as Y96 change; a designed miniprotein that uses a larger surface can keep contacts outside the sotorasib epitope and should be tested on Y96D, not only on wild-type G12C.";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [agentStatus, setAgentStatus] =
    useState<AgentStatusMap>(INITIAL_AGENT_STATUS);
  const [results, setResults] = useState<IDoctorDesignResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [pdbData, setPdbData] = useState<string | null>(null);
  const [usedLocalFixtures, setUsedLocalFixtures] = useState(false);
  const runGeneration = useRef(0);

  useEffect(() => {
    getProteinPDB(DEFAULT_PDB)
      .then(setPdbData)
      .catch(() => setPdbData(null));
  }, []);

  const handleRun = useCallback(async (mode: RunMode) => {
    const gen = ++runGeneration.current;
    setShowOnboarding(false);
    setAppState("running");
    setError(null);
    setResults(null);
    setAgentStatus(INITIAL_AGENT_STATUS);
    setCurrentStep(null);
    setUsedLocalFixtures(false);

    try {
      const res = await runWithFixtureFallback(
        mode,
        (agent, status) => {
          if (gen !== runGeneration.current) return;
          setAgentStatus((prev) => {
            if (!(agent in prev)) return prev;
            return { ...prev, [agent]: status as AgentStatus };
          });
        },
        (step) => {
          if (gen !== runGeneration.current) return;
          setCurrentStep(step);
        }
      );
      if (gen !== runGeneration.current) return;
      if (res.provenance?.mode === "fixture") {
        setUsedLocalFixtures(true);
      }
      setResults(res);
      setAppState("completed");
    } catch (err) {
      if (gen !== runGeneration.current) return;
      setError(err instanceof Error ? err.message : "Failed to run pipeline");
      setAppState("idle");
    }
  }, []);

  // On first load: show the newest saved run instead of always re-running.
  // Overrides: ?run=live | ?run=fixture | ?run=replay | ?run=none
  // Use a cancelled flag so React Strict Mode remounts don't leave the UI stuck on idle.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    const params = new URLSearchParams(window.location.search);
    const run = params.get("run");
    if (run === "none") return;

    if (run === "live" || run === "fixture" || run === "replay") {
      void handleRun(run);
      return () => {
        cancelled = true;
        runGeneration.current += 1;
      };
    }

    void (async () => {
      setAppState("running");
      setCurrentStep("Loading latest run…");
      const latest = await loadLatestRun();
      if (cancelled) return;
      if (latest) {
        setAgentStatus(
          Object.fromEntries(
            (Object.keys(INITIAL_AGENT_STATUS) as (keyof AgentStatusMap)[]).map(
              (a) => [a, "completed" as AgentStatus]
            )
          ) as unknown as AgentStatusMap
        );
        setResults(latest);
        setUsedLocalFixtures(latest.provenance?.mode === "fixture");
        setAppState("completed");
        setCurrentStep(null);
        return;
      }
      void handleRun("fixture");
    })();

    return () => {
      cancelled = true;
    };
  }, [handleRun]);

  const handleReset = useCallback(() => {
    setAppState("idle");
    setResults(null);
    setAgentStatus(INITIAL_AGENT_STATUS);
    setError(null);
    setCurrentStep(null);
    setUsedLocalFixtures(false);
  }, []);

  const showDemoBanner =
    results &&
    (isDemoData(results.provenance) || usedLocalFixtures);

  const pocketResidues =
    results?.scientific_spec?.pocket_residues ?? ["Cys12", "His95", "Tyr96", "Asp69"];

  function handleDownloads() {
    if (!results) return;
    downloadBlob(
      JSON.stringify(results.scientific_spec, null, 2),
      "spec.json",
      "application/json"
    );
    const fasta = (results.designs?.designs || [])
      .map((d) => `>${d.id}\n${d.sequence}`)
      .join("\n");
    downloadBlob(fasta, "designs.fasta", "text/plain");
    downloadBlob(
      JSON.stringify(results.verdicts, null, 2),
      "verdicts.json",
      "application/json"
    );
    downloadBlob(results.experiment_md || "", "experiment.md", "text/markdown");
  }

  return (
    <div className="flex min-h-screen flex-col">
      {showOnboarding && (
        <OnboardingModal onDismiss={() => setShowOnboarding(false)} />
      )}
      <Header appState={appState} />

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        {error && (
          <div className="mb-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {showDemoBanner && (
          <div className="demo-banner mb-6 border-2 border-amber-500 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-950">
            Demo data — provenance mode is{" "}
            <span className="font-mono">{results!.provenance.mode}</span>
            {Object.values(results!.provenance.nodes || {}).some(
              (n) => n === "fixture"
            ) && (
              <span>
                {" "}
                (one or more nodes are fixture). Do not treat scores as live
                results.
              </span>
            )}
          </div>
        )}

        {results?.run_id && appState === "completed" && (
          <p className="mb-4 text-xs text-slate-500">
            Showing run{" "}
            <span className="font-mono text-slate-700">{results.run_id}</span>
            {" · "}
            mode{" "}
            <span className="font-mono text-slate-700">
              {results.provenance?.mode}
            </span>
          </p>
        )}

        {/* IDLE */}
        {appState === "idle" && (
          <div className="animate-fade-in">
            <section className="relative overflow-hidden border border-slate-200/80 bg-white/70 px-6 py-14 sm:px-10 sm:py-16">
              <div
                className="pointer-events-none absolute inset-0 opacity-[0.07]"
                style={{
                  backgroundImage:
                    "url(\"data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%230f766e' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\")",
                }}
              />
              <div className="relative max-w-2xl">
                <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-teal-800">
                  re:AGENT · Track A
                </p>
                <h2 className="font-display text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
                  iDoctor Design
                </h2>
                <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                  An AI scientist that reads how KRAS G12C drugs fail, designs a
                  binder under those constraints, and only keeps what it cannot
                  disprove.
                </p>
                <p className="mt-5 max-w-xl border-l-2 border-teal-600/50 pl-4 text-sm leading-relaxed text-slate-500">
                  {HYPOTHESIS_TEASER}
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => handleRun("replay")}
                    className="bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-800"
                  >
                    Replay latest
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRun("fixture")}
                    className="border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 transition-colors hover:border-teal-600 hover:text-teal-900"
                  >
                    Run fixture
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRun("live")}
                    className="border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 transition-colors hover:border-teal-600 hover:text-teal-900"
                  >
                    Run live
                  </button>
                </div>
                <p className="mt-3 text-[11px] text-slate-400">
                  Stage default is <span className="font-mono">replay</span> of a
                  saved run (demo-data banner on). Fixture works offline from
                  bundled JSON. Live calls partners when keys exist — BindCraft
                  is used only if a finished campaign is on disk; otherwise the
                  engine column says heuristic, not RFdiffusion.
                </p>
              </div>
            </section>

            {pdbData && (
              <div className="mt-8 animate-fade-in animate-fade-in-delay-1">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Structure · PDB {DEFAULT_PDB} (optional)
                </p>
                <ProteinViewer
                  pdbData={pdbData}
                  bindingResidues={pocketResidues}
                  ligandId="ARS"
                />
              </div>
            )}
          </div>
        )}

        {/* RUNNING */}
        {appState === "running" && (
          <div className="animate-fade-in grid gap-6 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <div className="mb-4">
                <h2 className="font-display text-2xl font-semibold text-slate-900">
                  Running iDoctor Design
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {currentStep || "Starting agent graph…"}
                </p>
              </div>
              {pdbData ? (
                <ProteinViewer
                  pdbData={pdbData}
                  bindingResidues={pocketResidues}
                  ligandId="ARS"
                />
              ) : (
                <div className="flex h-64 items-center justify-center border border-dashed border-slate-300 bg-white/50 text-sm text-slate-400">
                  Protein viewer unavailable (API optional)
                </div>
              )}
            </div>
            <div className="lg:col-span-2">
              <AgentStatusPanel
                agentStatus={agentStatus}
                currentStep={currentStep}
                provenance={results?.provenance}
              />
            </div>
          </div>
        )}

        {/* COMPLETED — four regions */}
        {appState === "completed" && results && (
          <div className="space-y-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-3xl">
                <h2 className="font-display text-2xl font-semibold text-slate-900">
                  Trust results
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                  {results.hypothesis || results.scientific_spec?.hypothesis}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleDownloads}
                  className="border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-teal-600"
                >
                  Download artifacts
                </button>
                <button
                  type="button"
                  onClick={handleReset}
                  className="border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:text-slate-900"
                >
                  New run
                </button>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              {/* A — Literature / mutations */}
              <section className="animate-fade-in border border-slate-200 bg-white p-5">
                <RegionLabel letter="A" title="Literature spec / mutations" />
                <p className="mb-3 text-xs text-slate-500">
                  {results.scientific_spec?.target?.clinical_hook}
                </p>
                <p className="mb-3 text-[10px] text-slate-400">
                  WT = KRAS G12C without extra resistance mutation. Mutant =
                  G12C plus one listed change. Click a mutation for source
                  quotes.
                </p>
                <MutationMap
                  mutations={results.scientific_spec?.mutations || []}
                />
                {(results.scientific_spec?.failed_small_molecules?.length ??
                  0) > 0 && (
                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      Failed / limited small molecules
                    </h4>
                    <ul className="space-y-2">
                      {results.scientific_spec.failed_small_molecules.map(
                        (f) => (
                          <li key={f.id} className="text-xs text-slate-600">
                            <span className="font-medium text-slate-900">
                              {f.name}
                            </span>
                            <span className="text-slate-400"> — </span>
                            {f.why_not_enough}
                          </li>
                        )
                      )}
                    </ul>
                  </div>
                )}
              </section>

              {/* B — Small-molecule control */}
              <section className="animate-fade-in animate-fade-in-delay-1 border border-slate-200 bg-white p-5">
                <RegionLabel letter="B" title="Small-molecule control" />
                <p className="mb-3 text-xs text-slate-500">
                  Docking is a control that can be disproven — not the product.
                </p>
                <EvalPanel evalData={results.eval} />
                <div className="mt-4 border-t border-slate-100 pt-4">
                  <SmallMolTable
                    compounds={results.smallmol?.compounds || []}
                    verdicts={results.verdicts?.items || []}
                  />
                </div>
              </section>

              {/* C — Designs + reject pile */}
              <section className="animate-fade-in animate-fade-in-delay-2 border border-slate-200 bg-white p-5 lg:col-span-2">
                <RegionLabel letter="C" title="Designs + reject pile" />
                <DesignTable
                  designs={results.designs?.designs || []}
                  verdicts={results.verdicts?.items || []}
                  deltas={results.eval?.design_deltas}
                  designEngine={results.designs?.meta?.design_engine || results.designs?.meta?.engine}
                />
                <div className="mt-6">
                  <RejectDrawer
                    designs={results.designs?.designs || []}
                    verdicts={results.verdicts?.items || []}
                  />
                </div>
              </section>

              {/* D — Monday experiment */}
              <section className="animate-fade-in animate-fade-in-delay-3 border border-slate-200 bg-white p-5 lg:col-span-2">
                <RegionLabel letter="D" title="Monday experiment" />
                <ExperimentCard markdown={results.experiment_md || ""} />
              </section>
            </div>

            {pdbData && (
              <div className="border border-slate-200 bg-white p-4">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Structure context · {DEFAULT_PDB}
                </p>
                <ProteinViewer
                  pdbData={pdbData}
                  bindingResidues={pocketResidues}
                  ligandId="ARS"
                />
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200 py-4 text-center text-[11px] text-slate-400">
        iDoctor Design · re:AGENT 2026 · evidence before confidence
      </footer>
    </div>
  );
}

function RegionLabel({ letter, title }: { letter: string; title: string }) {
  return (
    <div className="mb-4 flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center bg-slate-900 text-[11px] font-bold text-teal-300">
        {letter}
      </span>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
    </div>
  );
}
