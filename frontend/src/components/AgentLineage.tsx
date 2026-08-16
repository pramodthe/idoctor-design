"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";
import type {
  AgentName,
  AgentStatus,
  AgentStatusMap,
  AgentTrace,
  Design,
  LabLogEvent,
  LoopHistoryPayload,
  ProvenancePayload,
  SmallMolCompound,
  VerdictItem,
  VerdictValue,
} from "@/lib/types";
import { AGENT_DISPLAY_NAMES } from "@/lib/types";

export interface AgentLineageProps {
  agentStatus: AgentStatusMap;
  currentStep?: string | null;
  provenance?: ProvenancePayload;
  traces?: AgentTrace[];
  labLog?: LabLogEvent[];
  verdicts?: VerdictItem[];
  designs?: Design[];
  compounds?: SmallMolCompound[];
  loopHistory?: LoopHistoryPayload;
  className?: string;
}

const CHAIN: AgentName[] = [
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

const SUB: Record<AgentName, string> = {
  evidence: "Paperclip MCP · clinical records",
  designer: "de novo binder sequences",
  structure: "AlphaFold2 / ESMFold complex",
  novelty: "RCSB MMseqs2 · PDB identity",
  complex: "G12C vs resistance multimer",
  physics: "Vina control on 6OIM",
  evaluate: "Spearman ρ vs Ki oracle",
  critic: "adversarial reject engine",
  experiment: "Monday wet-lab protocol",
};

const TOOLS: Record<AgentName, string[]> = {
  evidence: ["Paperclip PMC API", "EuropePMC search"],
  designer: ["BindCraft (RFdiffusion)", "ProteinMPNN"],
  structure: ["AlphaFold-Multimer", "ESMFold"],
  novelty: ["RCSB PDB Alignment", "MMseqs2 Identity"],
  complex: ["WT vs Y96D ipTM", "Switch II Interface"],
  physics: ["AutoDock Vina", "RDKit ETKDGv3"],
  evaluate: ["Spearman ρ Oracle", "WT/Mutant ΔΔG"],
  critic: ["Claude Scientist Critic", "Biophysical Filter"],
  experiment: ["experiment.md Card", "Synthesis Specs"],
};


const AGENT_X = 300;
const AGENT_Y = 180;
const VERDICT_W = 190;

function llmCount(traces: AgentTrace[] | undefined, key: AgentName): number {
  return (traces || [])
    .filter((t) => t.agent === key)
    .flatMap((t) => t.llm_calls || [])
    .filter((c) => {
      if (!c || typeof c !== "object") return false;
      const t = c as { success?: boolean; model?: string };
      if (t.success === true) return true;
      const m = (t.model || "").toLowerCase();
      return m.includes("claude") || m.startsWith("anthropic");
    }).length;
}

function firstOutput(traces: AgentTrace[] | undefined, key: AgentName): string | null {
  const t = [...(traces || [])]
    .reverse()
    .find((tr) => tr.agent === key && tr.output_summary);
  return t?.output_summary || null;
}

function recentLog(labLog: LabLogEvent[] | undefined, key: AgentName): string | null {
  if (!labLog) return null;
  for (let i = labLog.length - 1; i >= 0; i--) {
    if (labLog[i].agent === key && labLog[i].text) {
      const t = labLog[i].text;
      return t.length > 120 ? t.slice(0, 117) + "…" : t;
    }
  }
  return null;
}

type MetricRow = { label: string; value: string; up?: boolean; rate?: string };

type AgentNodeData = {
  kind: "agent";
  agent: AgentName;
  label: string;
  sub: string;
  status: AgentStatus;
  llm: number;
  prov: string | undefined;
  output: string | null;
  log: string | null;
  activeStep: string | null;
  tools: string[];
  promoteCount: number;
  rejectCount: number;
  duration?: number;
  rows: MetricRow[];
  targetPosition: Position;
  sourcePosition: Position;
};

type VerdictNodeData = {
  kind: "verdict";
  subjectKind: "design" | "smallmol";
  subjectId: string;
  verdict: VerdictValue;
  summary: string;
  reasons: string[];
  meta: string;
};

type AnyNodeData = AgentNodeData | VerdictNodeData;

/* FlowTune Inspired Modern Card Node */
function AgentNode({ data }: NodeProps<AgentNodeData>) {
  const [open, setOpen] = useState(false);
  const running = data.status === "running";
  const completed = data.status === "completed";
  const rows = open ? data.rows : data.rows.slice(0, 1);

  return (
    <div
      className={`group relative w-[220px] rounded-[20px] bg-white/95 p-3 shadow-lg shadow-slate-900/5 ring-1 backdrop-blur-xl transition-all duration-300 ${
        running
          ? "ring-blue-500 shadow-blue-500/20"
          : completed
            ? "ring-slate-200 hover:ring-blue-300"
            : "ring-slate-200/60 opacity-85"
      }`}
    >
      <Handle type="target" position={data.targetPosition} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-blue-500 shadow-sm" />
      <Handle type="source" position={data.sourcePosition} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-blue-500 shadow-sm" />
      <Handle type="target" id="in-loop" position={Position.Top} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-amber-500 shadow-sm" />
      <Handle type="source" id="out-loop" position={Position.Top} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-amber-500 shadow-sm" />

      {/* Header Pill & Title */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-slate-100/80">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setOpen((v) => !v);
            }}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm shadow-blue-600/30 transition-transform active:scale-95"
            aria-label={open ? "Collapse" : "Expand"}
          >
            <span className="text-xs font-bold leading-none">{open ? "−" : "+"}</span>
          </button>

          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] font-bold tracking-tight text-slate-900">
                {data.label}
              </span>
              {data.prov && (
                <span className={`rounded-full px-1.5 py-0.2 text-[9px] font-bold ${
                  data.prov === "live"
                    ? "bg-emerald-50 text-emerald-700"
                    : data.prov === "cached"
                      ? "bg-indigo-50 text-indigo-700"
                      : data.prov === "fixture"
                        ? "bg-amber-50 text-amber-700"
                        : "bg-slate-100 text-slate-600"
                }`}>
                  {data.prov}
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-400 font-medium">{data.sub}</p>
          </div>
        </div>

        {/* Right Status Dot or LLM Badge */}
        {running ? (
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-600" />
          </span>
        ) : completed ? (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-bold text-emerald-700">
            done
          </span>
        ) : (
          <span className="h-2 w-2 rounded-full bg-slate-300" />
        )}
      </div>

      {/* Inset Sub-Cards */}
      <div className="space-y-1.5 pt-2">
        {rows.map((row, idx) => (
          <div
            key={idx}
            className="flowtune-subcard flex items-center justify-between px-2.5 py-1.5"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-md bg-blue-50 text-[10px] font-bold text-blue-600">
                ●
              </span>
              <span className="truncate text-[11px] font-medium text-slate-700">
                {row.label}
              </span>
            </div>

            <div className="flex items-center gap-1 shrink-0 pl-1">
              <span className="font-mono text-[10px] font-bold text-slate-800">
                {row.value}
              </span>
            </div>
          </div>
        ))}

        {running && data.activeStep && (
          <div className="rounded-xl bg-blue-50/80 px-2.5 py-1 text-[10px] font-medium text-blue-700">
            {data.activeStep}
          </div>
        )}
      </div>
    </div>
  );
}


/* FlowTune Verdict Sub-Node */
function VerdictNode({ data }: NodeProps<VerdictNodeData>) {
  const promote = data.verdict === "promote";
  const reject = data.verdict === "reject";

  return (
    <div
      className={`group relative w-[200px] rounded-[22px] bg-white/90 p-3 shadow-lg ring-1 backdrop-blur-xl transition-all ${
        promote
          ? "ring-emerald-200 shadow-emerald-500/10"
          : reject
            ? "ring-pink-200 shadow-pink-500/10"
            : "ring-amber-200 shadow-amber-500/10"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-slate-300" />

      <div className="flex items-center justify-between gap-1.5 pb-1">
        <span className="truncate font-mono text-[12px] font-bold text-slate-800">
          {data.subjectId}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
            promote
              ? "bg-[#10B981] text-white shadow-xs"
              : reject
                ? "bg-[#FF3B69] text-white shadow-xs"
                : "bg-[#F59E0B] text-white shadow-xs"
          }`}
        >
          {reject ? "Alert" : promote ? "OK" : "Warn"}
        </span>
      </div>

      <div className="flowtune-subcard mt-1.5 flex items-center justify-between px-2 py-1.5">
        <span className="truncate text-[10px] font-medium text-slate-500">
          {data.subjectKind === "design" ? "miniprotein" : "control"}
        </span>
        <span className="font-mono text-[10px] font-bold text-slate-700">
          {data.meta}
        </span>
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode, verdict: VerdictNode };

const AGENT_LAYOUT: Record<
  AgentName,
  { x: number; y: number; target: Position; source: Position }
> = {
  evidence: { x: 0, y: 0, target: Position.Left, source: Position.Right },
  designer: { x: 260, y: 0, target: Position.Left, source: Position.Right },
  structure: { x: 520, y: 0, target: Position.Left, source: Position.Bottom },
  novelty: { x: 520, y: 150, target: Position.Top, source: Position.Left },
  complex: { x: 260, y: 150, target: Position.Right, source: Position.Left },
  physics: { x: 0, y: 150, target: Position.Right, source: Position.Bottom },
  evaluate: { x: 0, y: 300, target: Position.Top, source: Position.Right },
  critic: { x: 260, y: 300, target: Position.Left, source: Position.Right },
  experiment: { x: 520, y: 300, target: Position.Left, source: Position.Right },
};

function agentRows(
  key: AgentName,
  tools: string[],
  traces: AgentTrace[] | undefined,
  designs: Design[],
  promoteCount: number,
  rejectCount: number
): MetricRow[] {
  const t = (traces || []).find((x) => x.agent === key);
  const dur =
    t?.duration_seconds != null
      ? `${Number(t.duration_seconds).toFixed(1)}s`
      : t ? "ready" : "queued";
  
  const rows: MetricRow[] = [
    { label: tools[0] || key, value: dur, rate: t?.duration_seconds != null ? "pass" : "pending", up: true },
  ];

  if (key === "designer" && designs.length > 0) {
    rows.push({ label: "Generated Candidates", value: `${designs.length} binders`, rate: "BindCraft", up: true });
  }
  if (key === "structure") {
    const plddt = designs.find((d) => d.plddt != null)?.plddt;
    if (plddt != null) {
      rows.push({ label: "Fold Confidence", value: `pLDDT ${plddt.toFixed(0)}`, rate: plddt >= 75 ? "High" : "Low", up: plddt >= 75 });
    }
  }
  if (key === "critic") {
    rows.push({
      label: "Falsification Triage",
      value: `${promoteCount} Passed · ${rejectCount} Rejected`,
      rate: t?.model || "rules + Claude",
      up: rejectCount === 0,
    });
  }
  if (tools[1]) {
    rows.push({ label: tools[1], value: t ? "verified" : "queued", rate: "verified", up: Boolean(t) });
  }
  return rows;
}


function edgeMetric(from: AgentName, traces: AgentTrace[] | undefined, flowing: boolean, done: boolean) {
  const t = (traces || []).find((x) => x.agent === from);
  if (flowing) return "live";
  if (t?.duration_seconds != null) return `${Number(t.duration_seconds).toFixed(1)}s`;
  if (done) return "ok";
  return "";
}

function designMeta(d: Design | undefined): string {
  if (!d) return "design";
  const bits = [`len ${d.length}`];
  if (d.plddt != null) bits.push(`pLDDT ${d.plddt.toFixed(0)}`);
  return bits.join(" · ");
}

function compoundMeta(c: SmallMolCompound | undefined): string {
  if (!c) return "compound";
  if (c.known_ki_nm != null) return `Ki ${c.known_ki_nm} nM`;
  if (c.vina_wt != null) return `Vina ${c.vina_wt.toFixed(1)}`;
  return c.name || "compound";
}

export default function AgentLineage({
  agentStatus,
  currentStep,
  provenance,
  traces,
  labLog,
  verdicts = [],
  designs = [],
  compounds = [],
  loopHistory,
  className = "",
}: AgentLineageProps) {
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stableNodeTypes] = useState(() => nodeTypes);
  const [stableEdgeTypes] = useState(() => ({}));

  const designById = useMemo(
    () => Object.fromEntries(designs.map((d) => [d.id, d])),
    [designs]
  );
  const compoundById = useMemo(
    () => Object.fromEntries(compounds.map((c) => [c.id, c])),
    [compounds]
  );

  const designVerdicts = useMemo(
    () => verdicts.filter((v) => v.subject_kind === "design"),
    [verdicts]
  );
  const molVerdicts = useMemo(
    () => verdicts.filter((v) => v.subject_kind === "smallmol"),
    [verdicts]
  );

  const { nodes, edges } = useMemo(() => {
    const promotes = designVerdicts.filter((v) => v.verdict === "promote");
    const rejects = designVerdicts.filter((v) => v.verdict === "reject");
    const holds = designVerdicts.filter((v) => v.verdict === "hold");
    const molRejects = molVerdicts.filter((v) => v.verdict === "reject" || v.verdict === "hold");
    const molPromotes = molVerdicts.filter((v) => v.verdict === "promote");

    const retryActive =
      agentStatus.critic === "completed" && agentStatus.designer === "running";
    const criticDone = agentStatus.critic === "completed" || designVerdicts.length > 0;

    const nodes: Node<AnyNodeData>[] = CHAIN.map((key) => ({
      id: key,
      type: "agent",
      position: { x: AGENT_LAYOUT[key].x, y: AGENT_LAYOUT[key].y },
      data: {
        kind: "agent",
        agent: key,
        label: AGENT_DISPLAY_NAMES[key].split(" (")[0],
        sub: SUB[key],
        status: agentStatus[key],
        llm: llmCount(traces, key),
        prov: provenance?.nodes?.[key],
        output: firstOutput(traces, key),
        log: recentLog(labLog, key),
        activeStep: agentStatus[key] === "running" ? (currentStep ?? null) : null,
        tools: TOOLS[key],
        promoteCount: key === "critic" ? promotes.length + molPromotes.length : 0,
        rejectCount: key === "critic" ? rejects.length + molRejects.length : 0,
        duration: (traces || []).find((t) => t.agent === key)?.duration_seconds,
        rows: agentRows(
          key,
          TOOLS[key],
          traces,
          designs,
          key === "critic" ? promotes.length + molPromotes.length : 0,
          key === "critic" ? rejects.length + molRejects.length : 0
        ),
        targetPosition: AGENT_LAYOUT[key].target,
        sourcePosition: AGENT_LAYOUT[key].source,
      },
      draggable: false,
      connectable: false,
    }));

    const edges: Edge[] = [];
    const edgeLabels = [
      "spec.json",
      "designs.json",
      "structures/",
      "novelty",
      "complex_scores.json",
      "smallmol.json",
      "eval.json",
      "verdicts.json",
    ];

    for (let i = 0; i < CHAIN.length - 1; i++) {
      const from = agentStatus[CHAIN[i]];
      const to = agentStatus[CHAIN[i + 1]];
      const flowing = from === "completed" && to === "running";
      const done = from === "completed";
      const color = flowing ? "#3B82F6" : done ? "#10B981" : "#cbd5e1";
      const label = edgeLabels[i];


      edges.push({
        id: `${CHAIN[i]}->${CHAIN[i + 1]}`,
        source: CHAIN[i],
        target: CHAIN[i + 1],
        animated: flowing,
        type: "smoothstep",
        label,
        labelStyle: { fontSize: 10, fill: "#475569", fontWeight: 700 },
        labelBgStyle: { fill: "#ffffff", stroke: "#e2e8f0", strokeWidth: 1 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 9999,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color,
        },
        style: {
          stroke: color,
          strokeWidth: flowing ? 2.5 : 1.8,
        },
      });
    }

    const completedRounds = loopHistory?.iterations?.length || 0;
    const loopWasUsed = retryActive || completedRounds > 1;
    if (loopWasUsed) {
      edges.push({
        id: "critic->designer",
        source: "critic",
        sourceHandle: "out-loop",
        target: "designer",
        targetHandle: "in-loop",
        animated: retryActive,
        type: "smoothstep",
        label:
          completedRounds > 1
            ? `${completedRounds} rounds`
            : "redesign",
        labelStyle: { fontSize: 10, fill: "#b45309", fontWeight: 700 },
        labelBgStyle: { fill: "#fffbeb", stroke: "#fde68a", strokeWidth: 1 },
        labelBgBorderRadius: 9999,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#d97706" },
        style: { stroke: "#d97706", strokeWidth: 2, strokeDasharray: "6 4" },
      });
    }

    // Candidate and control verdicts are presented in the decision panels below
    // the graph. Keeping them off the canvas makes the nine-stage loop readable.
    const showOutcomeNodes = false;
    if (criticDone && showOutcomeNodes) {
      const criticX = CHAIN.indexOf("critic") * AGENT_X;

      // Promoted designs: fan UP from critic, then into experiment
      promotes.forEach((v, i) => {
        const id = `verdict-promote-${v.subject_id}`;
        const d = designById[v.subject_id];
        nodes.push({
          id,
          type: "verdict",
          position: {
            x: criticX + 40 + i * (VERDICT_W + 16),
            y: AGENT_Y - 140,
          },
          data: {
            kind: "verdict",
            subjectKind: "design",
            subjectId: v.subject_id,
            verdict: v.verdict,
            summary: v.summary,
            reasons: v.reasons || [],
            meta: designMeta(d),
          },
          draggable: false,
          connectable: false,
        });
        edges.push({
          id: `critic->${id}`,
          source: "critic",
          sourceHandle: "out-up",
          target: id,
          type: "smoothstep",
          animated: agentStatus.experiment === "running",
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#10B981" },
          style: { stroke: "#10B981", strokeWidth: 2 },
          label: i === 0 ? "promote ↗" : undefined,
          labelStyle: { fontSize: 9, fill: "#10B981", fontWeight: 700 },
          labelBgStyle: { fill: "#ecfdf5", stroke: "#a7f3d0", strokeWidth: 1 },
          labelBgBorderRadius: 9999,
        });
        edges.push({
          id: `${id}->experiment`,
          source: id,
          target: "experiment",
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#10B981" },
          style: { stroke: "#10B981", strokeWidth: 1.8, opacity: 0.85 },
        });
      });

      // Rejected designs: fan DOWN from critic (dead ends)
      rejects.forEach((v, i) => {
        const id = `verdict-reject-${v.subject_id}`;
        const d = designById[v.subject_id];
        nodes.push({
          id,
          type: "verdict",
          position: {
            x: criticX - 20 + i * (VERDICT_W + 12),
            y: AGENT_Y + 140,
          },
          data: {
            kind: "verdict",
            subjectKind: "design",
            subjectId: v.subject_id,
            verdict: v.verdict,
            summary: v.summary,
            reasons: v.reasons || [],
            meta: designMeta(d),
          },
          draggable: false,
          connectable: false,
        });
        edges.push({
          id: `critic->${id}`,
          source: "critic",
          sourceHandle: "out-down",
          target: id,
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#FF3B69" },
          style: { stroke: "#FF3B69", strokeWidth: 1.8, strokeDasharray: "5 4" },
          label: i === 0 ? "reject ↘" : undefined,
          labelStyle: { fontSize: 9, fill: "#FF3B69", fontWeight: 700 },
          labelBgStyle: { fill: "#fef2f2", stroke: "#fecdd3", strokeWidth: 1 },
          labelBgBorderRadius: 9999,
        });
      });

      // Hold designs under rejects if any
      holds.forEach((v, i) => {
        const id = `verdict-hold-${v.subject_id}`;
        const d = designById[v.subject_id];
        nodes.push({
          id,
          type: "verdict",
          position: {
            x: criticX - 20 + (rejects.length + i) * (VERDICT_W + 12),
            y: AGENT_Y + 140,
          },
          data: {
            kind: "verdict",
            subjectKind: "design",
            subjectId: v.subject_id,
            verdict: v.verdict,
            summary: v.summary,
            reasons: v.reasons || [],
            meta: designMeta(d),
          },
          draggable: false,
          connectable: false,
        });
        edges.push({
          id: `critic->${id}`,
          source: "critic",
          sourceHandle: "out-down",
          target: id,
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#F59E0B" },
          style: { stroke: "#F59E0B", strokeWidth: 1.5, strokeDasharray: "4 4" },
        });
      });

      // Small-mol control verdicts: further down / offset right of rejects
      const molAll = [...molPromotes, ...molRejects];
      molAll.forEach((v, i) => {
        const id = `verdict-mol-${v.subject_id}`;
        const c = compoundById[v.subject_id];
        const promote = v.verdict === "promote";
        nodes.push({
          id,
          type: "verdict",
          position: {
            x: criticX + 40 + i * (VERDICT_W + 12),
            y: AGENT_Y + 260,
          },
          data: {
            kind: "verdict",
            subjectKind: "smallmol",
            subjectId: v.subject_id,
            verdict: v.verdict,
            summary: v.summary,
            reasons: v.reasons || [],
            meta: compoundMeta(c),
          },
          draggable: false,
          connectable: false,
        });
        edges.push({
          id: `critic->${id}`,
          source: "critic",
          sourceHandle: "out-down",
          target: id,
          type: "smoothstep",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: promote ? "#10B981" : "#FF3B69",
          },
          style: {
            stroke: promote ? "#10B981" : "#FF3B69",
            strokeWidth: 1.5,
            strokeDasharray: promote ? undefined : "5 4",
            opacity: 0.85,
          },
          label: i === 0 ? "control ↘" : undefined,
          labelStyle: { fontSize: 9, fill: "#64748b", fontWeight: 600 },
          labelBgStyle: { fill: "#f8fafc", stroke: "#e2e8f0", strokeWidth: 1 },
          labelBgBorderRadius: 9999,
        });
      });
    }

    return { nodes, edges };
  }, [
    agentStatus,
    currentStep,
    provenance,
    traces,
    labLog,
    designVerdicts,
    molVerdicts,
    designById,
    compoundById,
    loopHistory,
    designs,
  ]);

  useEffect(() => {
    if (!flowRef.current) return;
    const runningKey = CHAIN.find((k) => agentStatus[k] === "running");
    if (runningKey) {
      const node = flowRef.current.getNode(runningKey);
      if (node) {
        flowRef.current.setCenter(node.position.x + 130, node.position.y + 60, {
          zoom: 0.85,
          duration: 500,
        });
        return;
      }
    }
    if (agentStatus.critic === "completed" && designVerdicts.length > 0) {
      flowRef.current.fitView({ padding: 0.2, duration: 500, maxZoom: 0.95 });
    }
  }, [agentStatus, designVerdicts.length]);

  const onNodeClick = useCallback((_: unknown, node: Node<AnyNodeData>) => {
    setSelectedId((s) => (s === node.id ? null : node.id));
  }, []);

  const selectedNode = selectedId ? nodes.find((n) => n.id === selectedId) : null;
  const selectedData = selectedNode?.data;

  return (
    <div className={`agent-lineage relative h-full overflow-hidden rounded-[24px] ${className}`}>
      {/* Floating Canvas Controls (Top Left) */}
      <div className="absolute left-3 top-3 z-30 flex items-center gap-1.5 pointer-events-auto">
        <button
          type="button"
          onClick={() => flowRef.current?.fitView({ padding: 0.22, duration: 400 })}
          className="flex h-7 items-center gap-1.5 rounded-xl border border-slate-200 bg-white/95 px-2.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-white hover:text-slate-900 transition-colors"
        >
          <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
          <span>Fit Graph</span>
        </button>
      </div>


      {/* Floating Target Badge (Center Top Anchor) */}
      <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2 pointer-events-none">
        <div className="flowtune-pill bg-white/95 px-3 py-1 text-xs font-bold text-slate-800 shadow-md shadow-slate-900/5">
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-600" />
          </span>
          <span>Target: KRAS G12C Switch II</span>
          <span className="rounded-md bg-slate-100 px-1.5 py-0.2 font-mono text-[10px] text-slate-600">6OIM</span>
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={stableNodeTypes}
        edgeTypes={stableEdgeTypes}
        onNodeClick={onNodeClick}
        onInit={(inst) => {
          flowRef.current = inst;
          if (designVerdicts.length > 0) {
            inst.fitView({ padding: 0.2, maxZoom: 0.95 });
          }
        }}
        fitView
        fitViewOptions={{ padding: 0.22, maxZoom: designVerdicts.length > 0 ? 0.95 : 1 }}
        minZoom={0.35}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        zoomOnScroll={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} color="transparent" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>

      {selectedData && selectedData.kind === "agent" && (
        <div className="absolute right-3 top-3 z-40 w-[280px] rounded-[18px] bg-white p-4 shadow-[0_12px_40px_rgba(15,23,42,0.12)] ring-1 ring-black/5">
          <div className="mb-2 flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-900">{selectedData.label}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-400">{selectedData.sub}</div>
            </div>
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Close"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {selectedData.llm > 0 && (
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[9px] font-bold text-blue-700">
                Claude × {selectedData.llm}
              </span>
            )}
            {selectedData.prov && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-semibold uppercase text-slate-600">
                {selectedData.prov}
              </span>
            )}
            {selectedData.promoteCount > 0 && (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-bold text-emerald-700">
                {selectedData.promoteCount} promote
              </span>
            )}
            {selectedData.rejectCount > 0 && (
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-[9px] font-bold text-red-700">
                {selectedData.rejectCount} reject
              </span>
            )}
          </div>
          <div className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-slate-400">Tools</div>
          <ul className="mb-2 space-y-0.5">
            {selectedData.tools.map((t) => (
              <li key={t} className="font-mono text-[10px] text-blue-700">{t}</li>
            ))}
          </ul>
          {(selectedData.output || selectedData.log) && (
            <>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-wider text-slate-400">Latest</div>
              <p className="text-[10px] leading-snug text-slate-600">
                {selectedData.output || selectedData.log}
              </p>
            </>
          )}
        </div>
      )}

      {selectedData && selectedData.kind === "verdict" && (
        <div className="absolute right-3 top-3 z-40 w-[300px] rounded-[18px] bg-white p-4 shadow-[0_12px_40px_rgba(15,23,42,0.12)] ring-1 ring-black/5">
          <div className="mb-2 flex items-start justify-between gap-2">
            <div>
              <div className="font-mono text-sm font-semibold text-slate-900">{selectedData.subjectId}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-400">
                {selectedData.subjectKind} · {selectedData.meta}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Close"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <span
            className={`mb-3 inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
              selectedData.verdict === "promote"
                ? "bg-emerald-50 text-emerald-700"
                : selectedData.verdict === "reject"
                  ? "bg-red-50 text-red-700"
                  : "bg-slate-100 text-slate-600"
            }`}
          >
            {selectedData.verdict}
          </span>
          <p className="text-[11px] leading-snug text-slate-600">{selectedData.summary}</p>
          {selectedData.reasons.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {selectedData.reasons.map((r) => (
                <span
                  key={r}
                  className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[9px] text-slate-500"
                >
                  {r}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
