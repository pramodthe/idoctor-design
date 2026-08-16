"use client";

import { useEffect, useMemo, useState } from "react";
import ProteinViewer from "@/components/ProteinViewer";
import { getBinderPdb, getRunArtifactUrl } from "@/lib/api";
import type {
  ComplexVariantMetrics,
  Design,
  SuccessBars,
  TamarindArtifact,
} from "@/lib/types";

interface ComplexResultsPanelProps {
  design?: Design;
  successBars?: SuccessBars;
  bindingResidues: string[];
  fallbackPdbData: string | null;
}

const PLOT_LABELS: Record<string, string> = {
  pae: "PAE heatmap",
  plddt: "pLDDT profile",
  coverage: "MSA coverage",
  ext_metrics: "Interface metrics",
};

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function metricValue(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : Number(value).toFixed(digits);
}

function imageLabel(artifact: TamarindArtifact): string {
  const lower = artifact.name.toLowerCase();
  const key = Object.keys(PLOT_LABELS).find((token) => lower.includes(token));
  return key ? PLOT_LABELS[key] : artifact.name.replace(/\.[^.]+$/, "");
}

function confidenceTone(value: number | null, threshold: number): string {
  if (value == null) return "text-slate-400";
  if (value >= threshold) return "text-emerald-700";
  if (value >= threshold * 0.8) return "text-amber-700";
  return "text-rose-700";
}

function MetricCard({
  label,
  value,
  detail,
  tone = "text-slate-900",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-xs">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
        {label}
      </p>
      <p className={`mt-1 font-mono text-xl font-bold tabular-nums ${tone}`}>{value}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">{detail}</p>
    </div>
  );
}

export default function ComplexResultsPanel({
  design,
  successBars,
  bindingResidues,
  fallbackPdbData,
}: ComplexResultsPanelProps) {
  const variants = useMemo(() => {
    const entries = Object.entries(design?.complex_metrics || {});
    return entries.sort(([a], [b]) => {
      if (a === "G12C") return -1;
      if (b === "G12C") return 1;
      return a.localeCompare(b);
    });
  }, [design]);

  const [selectedVariant, setSelectedVariant] = useState(variants[0]?.[0] || "");
  const [complexPdb, setComplexPdb] = useState<string | null>(null);
  const [activePlotPath, setActivePlotPath] = useState<string | null>(null);

  useEffect(() => {
    if (!variants.some(([variant]) => variant === selectedVariant)) {
      setSelectedVariant(variants[0]?.[0] || "");
    }
  }, [variants, selectedVariant]);

  const selected: ComplexVariantMetrics | undefined = variants.find(
    ([variant]) => variant === selectedVariant
  )?.[1];
  const imageArtifacts = useMemo(
    () => {
      const order = ["_pae.png", "_plddt.png", "_coverage.png", "_ext_metrics.png"];
      return (selected?.artifacts || [])
        .filter((artifact) => artifact.kind === "image")
        .sort((a, b) => {
          const ai = order.findIndex((suffix) => a.name.toLowerCase().endsWith(suffix));
          const bi = order.findIndex((suffix) => b.name.toLowerCase().endsWith(suffix));
          return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi);
        });
    },
    [selected]
  );

  useEffect(() => {
    setActivePlotPath(imageArtifacts[0]?.path || null);
  }, [selectedVariant, imageArtifacts]);

  useEffect(() => {
    let cancelled = false;
    const path = selected?.pdb_path;
    if (!path) {
      setComplexPdb(null);
      return;
    }
    getBinderPdb(path).then((pdb) => {
      if (!cancelled) setComplexPdb(pdb);
    });
    return () => {
      cancelled = true;
    };
  }, [selected?.pdb_path]);

  if (!design) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm text-slate-500">No design output is loaded.</p>
      </section>
    );
  }

  if (variants.length === 0) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 shadow-sm">
        <p className="text-sm font-semibold text-amber-900">No trusted complex panel</p>
        <p className="mt-1 text-xs leading-relaxed text-amber-800">
          This design has no WT-versus-mutant Tamarind artifacts. Proxy scores are not
          rendered as structural evidence.
        </p>
      </section>
    );
  }

  const raw = selected?.raw || {};
  const sequence = String(raw.Sequence || "");
  const chainLengths = sequence
    ? sequence.split(":").map((chain) => chain.length)
    : [];
  const meanPae = num(raw["Mean PAE"]);
  const maxPae = num(raw["Max PAE"]);
  const actifptm = num(raw.actifpTM);
  const minIptm = successBars?.min_iptm ?? 0.75;
  const minPlddt = successBars?.min_plddt ?? 70;
  const scoreFiles = (selected?.artifacts || []).filter((artifact) =>
    ["table", "data", "alignment", "log"].includes(artifact.kind)
  );

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-indigo-700">
              Tamarind output
            </span>
            <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
              Complete panel
            </span>
          </div>
          <h2 className="mt-2 text-lg font-bold tracking-tight text-slate-950">
            WT and resistance complex evidence
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-500">
            AlphaFold-Multimer structures, interface confidence, PAE, pLDDT, model
            settings, alignments, and raw score files for {design.id}.
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Method
          </p>
          <p className="mt-1 font-mono text-xs font-semibold text-slate-700">
            alphafold2_multimer_v3 · IPSAE
          </p>
        </div>
      </div>

      <div className="border-b border-slate-200 bg-slate-50/70 px-5 py-3">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {variants.map(([variant, metrics]) => {
            const active = variant === selectedVariant;
            const passes = metrics.iptm != null && metrics.iptm >= minIptm;
            return (
              <button
                key={variant}
                type="button"
                onClick={() => setSelectedVariant(variant)}
                className={`min-w-[170px] rounded-2xl border px-3 py-2.5 text-left transition-all ${
                  active
                    ? "border-indigo-300 bg-white shadow-sm ring-2 ring-indigo-100"
                    : "border-slate-200 bg-white/70 hover:border-slate-300 hover:bg-white"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900">{variant}</span>
                  <span
                    className={`h-2 w-2 rounded-full ${passes ? "bg-emerald-500" : "bg-rose-500"}`}
                  />
                </div>
                <div className="mt-2 flex gap-4 text-[10px] text-slate-500">
                  <span>
                    ipTM <strong className="font-mono text-slate-800">{metricValue(metrics.iptm)}</strong>
                  </span>
                  <span>
                    pLDDT <strong className="font-mono text-slate-800">{metricValue(metrics.plddt, 1)}</strong>
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-5 p-5 xl:grid-cols-12">
        <div className="xl:col-span-7">
          <div className="h-[420px] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900">
            <ProteinViewer
              pdbData={complexPdb || fallbackPdbData}
              complexMode={Boolean(complexPdb)}
              bindingResidues={bindingResidues}
            />
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-500">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-blue-400" /> Chain A · KRAS
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-400" /> Chain B · binder
              </span>
              {chainLengths.length > 0 && (
                <span className="font-mono">{chainLengths.join(" aa · ")} aa</span>
              )}
            </div>
            {selected?.pdb_path && (
              <a
                href={getRunArtifactUrl(selected.pdb_path, true)}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-700 hover:bg-slate-50"
              >
                Download PDB
              </a>
            )}
          </div>
        </div>

        <div className="space-y-4 xl:col-span-5">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-2">
            <MetricCard
              label="Interface ipTM"
              value={metricValue(selected?.iptm)}
              detail={`promotion bar ≥ ${minIptm.toFixed(2)}`}
              tone={confidenceTone(selected?.iptm ?? null, minIptm)}
            />
            <MetricCard
              label="Mean pLDDT"
              value={metricValue(selected?.plddt, 1)}
              detail={`structure bar ≥ ${minPlddt}`}
              tone={confidenceTone(selected?.plddt ?? null, minPlddt)}
            />
            <MetricCard
              label="pTM"
              value={metricValue(selected?.ptm)}
              detail="global fold confidence"
            />
            <MetricCard
              label="actifpTM"
              value={metricValue(actifptm)}
              detail="contact-restricted interface"
            />
            <MetricCard
              label="ipSAE"
              value={metricValue(selected?.ipsae, 4)}
              detail="PAE-derived interface score"
            />
            <MetricCard
              label="Mean PAE"
              value={metricValue(meanPae, 1)}
              detail={`max ${metricValue(maxPae, 1)} Å`}
              tone={meanPae != null && meanPae <= 10 ? "text-emerald-700" : "text-amber-700"}
            />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-900">Variant comparison</h3>
              <span className="text-[10px] text-slate-400">higher ipTM is better</span>
            </div>
            <div className="mt-3 space-y-3">
              {variants.map(([variant, metrics]) => (
                <div key={variant}>
                  <div className="mb-1 flex items-center justify-between text-[10px]">
                    <span className="font-mono font-semibold text-slate-700">{variant}</span>
                    <span className="font-mono font-bold text-slate-900">
                      {metricValue(metrics.iptm)}
                    </span>
                  </div>
                  <div className="relative h-2 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className={`h-full rounded-full ${
                        (metrics.iptm ?? 0) >= minIptm ? "bg-emerald-500" : "bg-rose-500"
                      }`}
                      style={{ width: `${Math.max(2, (metrics.iptm || 0) * 100)}%` }}
                    />
                    <span
                      className="absolute inset-y-0 w-px bg-slate-900/50"
                      style={{ left: `${minIptm * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h3 className="text-xs font-bold text-slate-900">Job provenance</h3>
            <dl className="mt-3 grid grid-cols-[92px_1fr] gap-x-3 gap-y-2 text-[10px]">
              <dt className="text-slate-400">Job</dt>
              <dd className="break-all font-mono text-slate-700">{selected?.job_name || "—"}</dd>
              <dt className="text-slate-400">Predictor</dt>
              <dd className="font-mono text-slate-700">{selected?.job_type || "alphafold"}</dd>
              <dt className="text-slate-400">Model / rank</dt>
              <dd className="font-mono text-slate-700">
                {String(raw.Model || "1")} / {String(raw.Rank || "001")}
              </dd>
              <dt className="text-slate-400">Files retained</dt>
              <dd className="font-mono text-slate-700">{selected?.artifacts?.length || 0}</dd>
            </dl>
          </div>
        </div>
      </div>

      {imageArtifacts.length > 0 && (
        <div className="border-t border-slate-200 bg-slate-50/70 p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Model diagnostics</h3>
              <p className="text-[10px] text-slate-500">Plots preserved from the Tamarind result archive</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {imageArtifacts.map((artifact) => (
                <button
                  key={artifact.path}
                  type="button"
                  onClick={() => setActivePlotPath(artifact.path)}
                  className={`rounded-lg px-2.5 py-1 text-[10px] font-semibold ${
                    activePlotPath === artifact.path
                      ? "bg-slate-900 text-white"
                      : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {imageLabel(artifact)}
                </button>
              ))}
            </div>
          </div>
          {activePlotPath && (
            <div className="flex min-h-[320px] items-center justify-center overflow-hidden rounded-2xl border border-slate-200 bg-white p-3">
              {/* Generated run plots are served by the local API and keep their native aspect ratio. */}
              <img
                src={getRunArtifactUrl(activePlotPath)}
                alt="Tamarind model diagnostic"
                className="max-h-[520px] max-w-full object-contain"
              />
            </div>
          )}
        </div>
      )}

      <details className="border-t border-slate-200 px-5 py-4">
        <summary className="cursor-pointer text-xs font-bold text-slate-800">
          Raw metrics and result files ({scoreFiles.length})
        </summary>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-[10px]">
              <tbody>
                {Object.entries(raw).map(([key, value]) => (
                  <tr key={key} className="border-b border-slate-100 last:border-0">
                    <th className="whitespace-nowrap bg-slate-50 px-3 py-2 font-semibold text-slate-500">
                      {key}
                    </th>
                    <td className="max-w-[420px] break-all px-3 py-2 font-mono text-slate-700">
                      {String(value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid content-start gap-2 sm:grid-cols-2">
            {scoreFiles.map((artifact) => (
              <a
                key={artifact.path}
                href={getRunArtifactUrl(artifact.path, true)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-[10px] hover:border-indigo-300 hover:bg-indigo-50"
              >
                <span className="block font-bold uppercase tracking-wider text-slate-400">
                  {artifact.kind}
                </span>
                <span className="mt-1 block break-all font-mono text-slate-700">
                  {artifact.name}
                </span>
              </a>
            ))}
          </div>
        </div>
      </details>
    </section>
  );
}
