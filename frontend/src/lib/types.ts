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
  constraint_scores: Record<string, number>;
  plddt: number | null;
  iptm: number | null;
  pdb_path: string | null;
  novelty: { identity: number; method: string };
  provenance: string;
}

export interface DesignsPayload {
  schema_version?: string;
  score_direction?: string;
  designs: Design[];
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
  | "physics"
  | "evaluate"
  | "critic"
  | "experiment";

export type AgentStatus = "pending" | "running" | "completed";

export interface AgentStatusMap {
  evidence: AgentStatus;
  designer: AgentStatus;
  structure: AgentStatus;
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
}

export type RunMode = "fixture" | "replay" | "live";

export type AppState = "idle" | "running" | "completed";

export const AGENT_DISPLAY_NAMES: Record<AgentName, string> = {
  evidence: "Literature & databases (Paperclip)",
  designer: "Sequence design (Proto)",
  structure: "Fold & complex (Tamarind)",
  physics: "Docking control (AutoDock Vina)",
  evaluate: "Score vs experiment",
  critic: "Scientist critic (Claude)",
  experiment: "Monday lab card",
};

export const INITIAL_AGENT_STATUS: AgentStatusMap = {
  evidence: "pending",
  designer: "pending",
  structure: "pending",
  physics: "pending",
  evaluate: "pending",
  critic: "pending",
  experiment: "pending",
};
