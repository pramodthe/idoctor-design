"use client";

import { getRunArtifactUrl, getRunFileUrl } from "@/lib/api";
import type { AgentTrace, IDoctorDesignResults } from "@/lib/types";

interface RunDetailsPanelProps {
  results: IDoctorDesignResults;
}

function JsonDetails({ label, value }: { label: string; value: unknown }) {
  if (value == null) return null;
  return (
    <details className="rounded-xl border border-slate-200 bg-slate-50/70">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-white">
        {label}
      </summary>
      <pre className="max-h-[360px] overflow-auto border-t border-slate-200 bg-slate-950 p-3 font-mono text-[10px] leading-relaxed text-slate-200">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

function TraceRow({ trace }: { trace: AgentTrace }) {
  const llmCount = trace.llm_calls?.length || 0;
  const toolCount = trace.tool_calls?.length || 0;
  return (
    <tr className="border-b border-slate-200/70 last:border-0">
      <td className="py-2 pr-3 font-semibold text-slate-800">{trace.agent_name || trace.agent}</td>
      <td className="py-2 pr-3 font-mono text-slate-500">{trace.duration_seconds.toFixed(1)}s</td>
      <td className="py-2 pr-3 text-slate-500">{llmCount} LLM · {toolCount} tools</td>
      <td className="max-w-[420px] py-2 text-slate-600">{trace.output_summary || "—"}</td>
    </tr>
  );
}

export default function RunDetailsPanel({ results }: RunDetailsPanelProps) {
  const files = results.files || [];
  const directories = results.directories || [];
  const directoryFiles = results.directory_files || {};
  const traces = results.agent_traces || [];
  const provenanceNodes = Object.entries(results.provenance?.nodes || {});
  const runId = results.run_id || "idoctor";
  const payloads = [
    ["spec.json", results.scientific_spec],
    ["designs.json", results.designs],
    ["loop_history.json", results.loop_history],
    ["verdicts.json", results.verdicts],
    ["complex_scores.json", results.complex_scores],
    ["smallmol.json", results.smallmol],
    ["eval.json", results.eval],
    ["provenance.json", results.provenance],
  ] as const;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-1">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-slate-950">Saved run details</h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-600">
              {runId}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Complete manifest, agent outputs, provenance, and raw payloads from the latest saved run.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[10px]">
          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 font-semibold text-slate-600">{files.length} files</span>
          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 font-semibold text-slate-600">{directories.length} folders</span>
          <span className="rounded-lg border border-indigo-200 bg-indigo-50 px-2 py-1 font-semibold text-indigo-700">{traces.length} agent traces</span>
        </div>
      </div>

      <div className="mt-3 grid gap-2 lg:grid-cols-3">
        <div className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-3 lg:col-span-3">
          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-indigo-500">Scientific hypothesis</p>
          <p className="mt-1 text-xs leading-relaxed text-indigo-950">{results.hypothesis || "No hypothesis recorded."}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">Run metadata</p>
          <dl className="mt-2 space-y-1.5 text-[10px]">
            <div className="flex justify-between gap-2"><dt className="text-slate-400">Mode</dt><dd className="font-semibold uppercase text-slate-700">{results.provenance?.mode || "—"}</dd></div>
            <div className="flex justify-between gap-2"><dt className="text-slate-400">Checkpoint</dt><dd className="font-semibold text-slate-700">{results.checkpointed ? "resumable" : "—"}</dd></div>
            <div className="flex justify-between gap-2"><dt className="text-slate-400">Created</dt><dd className="font-mono text-slate-700">{results.provenance?.created_at || "—"}</dd></div>
          </dl>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">Evidence nodes</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {provenanceNodes.map(([node, source]) => (
              <span key={node} className={`rounded-md border px-1.5 py-1 text-[9px] font-semibold ${source === "live" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : source === "cached" ? "border-indigo-200 bg-indigo-50 text-indigo-700" : source === "fixture" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-white text-slate-500"}`}>
                {node}: {source}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-slate-400">Saved folders</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {directories.map((directory) => (
              <span key={directory} className="rounded-md border border-slate-200 bg-white px-1.5 py-1 font-mono text-[9px] text-slate-600">{directory}/</span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-2 lg:grid-cols-2">
        <details className="rounded-2xl border border-slate-200 bg-white" open>
          <summary className="cursor-pointer px-3 py-2.5 text-xs font-bold text-slate-800 hover:bg-slate-50">Saved outputs and downloads</summary>
          <div className="border-t border-slate-200 p-3">
            <div className="grid gap-1.5 sm:grid-cols-2">
              {files.map((file) => (
                <a key={file} href={getRunFileUrl(runId, file, true)} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-[10px] font-mono text-slate-700 hover:border-indigo-300 hover:bg-indigo-50">
                  <span className="truncate">{file}</span><span className="text-indigo-600">↗</span>
                </a>
              ))}
            </div>
            {Object.entries(directoryFiles).length > 0 && (
              <div className="mt-3 space-y-2">
                {Object.entries(directoryFiles).map(([directory, nestedFiles]) => (
                  <details key={directory} className="rounded-xl border border-slate-200 bg-slate-50/70">
                    <summary className="cursor-pointer px-2.5 py-2 text-[10px] font-semibold text-slate-700 hover:bg-white">
                      {directory}/ · {nestedFiles.length} nested artifacts
                    </summary>
                    <div className="grid max-h-[240px] gap-1 overflow-auto border-t border-slate-200 p-2 sm:grid-cols-2">
                      {nestedFiles.map((nestedFile) => (
                        <a key={nestedFile} href={getRunArtifactUrl(`data/runs/${runId}/${directory}/${nestedFile}`, true)} target="_blank" rel="noreferrer" className="truncate rounded-md border border-slate-200 bg-white px-2 py-1.5 font-mono text-[9px] text-slate-600 hover:border-indigo-300 hover:bg-indigo-50">
                          {nestedFile}
                        </a>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
          </div>
        </details>

        <details className="rounded-2xl border border-slate-200 bg-white" open>
          <summary className="cursor-pointer px-3 py-2.5 text-xs font-bold text-slate-800 hover:bg-slate-50">Agent outputs and model/tool calls</summary>
          <div className="max-h-[280px] overflow-auto border-t border-slate-200 p-3">
            <table className="w-full text-left text-[10px]">
              <thead><tr className="border-b border-slate-200 text-[9px] uppercase tracking-wider text-slate-400"><th className="pb-2 pr-3">Agent</th><th className="pb-2 pr-3">Time</th><th className="pb-2 pr-3">Calls</th><th className="pb-2">Output</th></tr></thead>
              <tbody>{traces.map((trace, index) => <TraceRow key={`${trace.agent}-${index}`} trace={trace} />)}</tbody>
            </table>
          </div>
        </details>
      </div>

      <details className="mt-3 rounded-2xl border border-slate-200 bg-white">
        <summary className="cursor-pointer px-3 py-2.5 text-xs font-bold text-slate-800 hover:bg-slate-50">Raw saved payloads</summary>
        <div className="grid gap-2 border-t border-slate-200 p-3 lg:grid-cols-2">
          {payloads.map(([label, value]) => <JsonDetails key={label} label={label} value={value} />)}
          {results.experiment_md && <details className="rounded-xl border border-slate-200 bg-slate-50/70"><summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">experiment.md</summary><pre className="max-h-[360px] overflow-auto whitespace-pre-wrap border-t border-slate-200 bg-slate-950 p-3 text-[10px] leading-relaxed text-slate-200">{results.experiment_md}</pre></details>}
        </div>
      </details>
    </section>
  );
}
