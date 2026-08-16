export interface LabLogEvent {
  agent: string;
  kind: "step" | "tool" | "thought" | "output" | "route" | string;
  text: string;
  tool?: string;
}

export interface AgentTraceStep {
  action: string;
  detail: string;
}

export interface AgentTrace {
  agent: string;
  agent_name: string;
  duration_seconds: number;
  model: string | null;
  input_summary: string;
  output_summary: string;
  steps: AgentTraceStep[];
  llm_calls?: unknown[];
  tool_calls?: unknown[];
}

export type ProvenanceMode = "live" | "replay" | "fixture";
export type NodeProvenance = "live" | "cached" | "fixture" | "skipped";
export type MutationEffect = "loss" | "reduced" | "unclear";
export type SourceKind = "paper" | "trial" | "pdb" | "chembl";
export type VerdictValue = "promote" | "reject" | "hold";
export type SubjectKind = "design" | "smallmol";

export interface SourceRef {
  kind: SourceKind;
  id: string;
  title: string;
  quote: string;
}

export interface SpecMutation {
  id: string;
  effect_on_sotorasib: MutationEffect;
  notes: string;
  sources: SourceRef[];
}

export interface FailedSmallMolecule {
  id: string;
  name: string;
  why_not_enough: string;
  sources: SourceRef[];
}

export interface SpecStructure {
  pdb_id: string | null;
  label: string;
  kind: string;
  mutation_id?: string;
  notes?: string;
}

export interface SuccessBars {
  max_pdb_identity: number;
  min_plddt: number | null;
  min_iptm?: number | null;
  require_mutant_score: boolean;
}

export interface ScientificSpec {
  schema_version: string;
  provenance: string;
  hypothesis: string;
  target: {
    name: string;
    gene: string;
    pdb_id: string;
    uniprot_id: string | null;
    clinical_hook: string;
  };
  pocket_residues: string[];
  success_bars: SuccessBars;
  mutations: SpecMutation[];
  failed_small_molecules: FailedSmallMolecule[];
  structures: SpecStructure[];
}

export interface Design {
  id: string;
  sequence: string;
  length: number;
  molecule_type: string;
  constraint_scores: Record<string, number | boolean | null>;
  plddt: number | null;
  iptm: number | null;
  pdb_path: string | null;
  novelty: { identity: number | null; method: string };
  provenance: string;
  fold_method?: string | null;
  generator?: string | null;
  iteration?: number;
  lineage?: {
    iteration: number;
    parent_ids: string[];
    failure_codes: string[];
  };
  complex_metrics?: Record<string, ComplexVariantMetrics>;
}

export interface TamarindArtifact {
  name: string;
  kind: "image" | "structure" | "table" | "alignment" | "data" | "log" | "file" | string;
  path: string;
}

export interface ComplexVariantMetrics {
  variant: string;
  job_name: string;
  job_type: string;
  iptm: number | null;
  plddt: number | null;
  ptm: number | null;
  ipsae: number | null;
  ranking_score?: number | null;
  pdb_path?: string | null;
  artifacts?: TamarindArtifact[];
  raw?: Record<string, string | number | null>;
}

export interface ComplexDesignScore {
  wt_score: number | null;
  mutant_scores: Record<string, number | null>;
  method: string;
  confidence: string;
  score_kind: string;
  score_direction: string;
  note?: string;
}

export interface DesignsPayload {
  schema_version?: string;
  score_direction?: string;
  designs: Design[];
  meta?: { design_engine?: string; job_name?: string; engine?: string };
}

export interface SmallMolCompound {
  id: string;
  name: string;
  smiles: string;
  known_ki_nm: number | null;
  vina_wt: number | null;
  vina_mutants: Record<string, number | null>;
  pains_flags: string[];
  lipinski_violations: number;
}

export interface SmallMolPayload {
  schema_version?: string;
  receptor_pdb_wt?: string;
  compounds: SmallMolCompound[];
}

export interface EvalDisagreement {
  id: string;
  vina_rank: number;
  ki_rank: number;
  residual: number;
  note: string;
}

export interface DesignDelta {
  id: string;
  wt_score: number | null;
  mutant_scores: Record<string, number | null>;
  note: string;
  evaluation_method?: string;
  evaluation_confidence?: string;
  score_kind?: string;
  score_direction?: "higher_is_better" | "lower_is_better" | string;
}

export interface EvalPayload {
  schema_version?: string;
  smallmol_spearman_rho: number | null;
  smallmol_n: number;
  smallmol_note?: string;
  disagreements: EvalDisagreement[];
  design_deltas: DesignDelta[];
}

export interface VerdictItem {
  subject_kind: SubjectKind;
  subject_id: string;
  verdict: VerdictValue;
  reasons: string[];
  summary: string;
  evidence_ids: string[];
  metrics_used: string[];
  remaining_risk: string;
}

export interface VerdictsPayload {
  schema_version?: string;
  hypothesis?: string;
  items: VerdictItem[];
  loop?: LoopStatus;
}

export interface LoopStatus {
  iteration: number;
  max_iterations: number;
  progress_score: number;
  best_progress_score: number;
  no_improvement_rounds: number;
  route: "redesign" | "experiment";
  decision_reason: string;
  termination_reason?: string | null;
  verification_failures?: string[];
}

export interface LoopIteration {
  iteration: number;
  design_engine: string;
  design_ids: string[];
  progress_score: number;
  improved: boolean;
  no_improvement_rounds: number;
  counts: { promote: number; hold: number; reject: number };
  reason_codes: string[];
  route: "redesign" | "experiment";
  decision_reason: string;
  redesign_feedback?: {
    priority_codes?: string[];
    reason_counts?: Record<string, number>;
    parent_ids?: string[];
    instructions?: string;
  } | null;
  verification_failures?: string[];
}

export interface LoopHistoryPayload {
  schema_version: string;
  max_iterations: number;
  termination_reason?: string | null;
  iterations: LoopIteration[];
}

export interface ProvenancePayload {
  run_id: string;
  mode: ProvenanceMode;
  nodes: Record<string, NodeProvenance>;
  created_at: string;
}

export type AgentName =
  | "evidence"
  | "designer"
  | "structure"
  | "novelty"
  | "complex"
  | "physics"
  | "evaluate"
  | "critic"
  | "experiment";

export type AgentStatus = "pending" | "running" | "completed";

export interface AgentStatusMap {
  evidence: AgentStatus;
  designer: AgentStatus;
  structure: AgentStatus;
  novelty: AgentStatus;
  complex: AgentStatus;
  physics: AgentStatus;
  evaluate: AgentStatus;
  critic: AgentStatus;
  experiment: AgentStatus;
}

export interface IDoctorDesignResults {
  status: "completed";
  run_id?: string;
  hypothesis: string;
  scientific_spec: ScientificSpec;
  designs: DesignsPayload;
  smallmol: SmallMolPayload;
  eval: EvalPayload;
  verdicts: VerdictsPayload;
  experiment_md: string;
  provenance: ProvenancePayload;
  agent_traces?: AgentTrace[];
  lab_log?: LabLogEvent[];
  loop_history?: LoopHistoryPayload;
  loop_termination_reason?: string | null;
  complex_scores?: Record<string, ComplexDesignScore>;
  checkpointed?: boolean;
}

export type RunMode = "fixture" | "replay" | "live";

export type AppState = "idle" | "running" | "completed";

export const AGENT_DISPLAY_NAMES: Record<AgentName, string> = {
  evidence: "Literature (Paperclip MCP)",
  designer: "Binder design",
  structure: "Fold metrics",
  novelty: "PDB novelty check",
  complex: "WT/mutant complexes",
  physics: "Docking control",
  evaluate: "Score vs Ki",
  critic: "Scientist critic",
  experiment: "Monday lab card",
};

export const INITIAL_AGENT_STATUS: AgentStatusMap = {
  evidence: "pending",
  designer: "pending",
  structure: "pending",
  novelty: "pending",
  complex: "pending",
  physics: "pending",
  evaluate: "pending",
  critic: "pending",
  experiment: "pending",
};
