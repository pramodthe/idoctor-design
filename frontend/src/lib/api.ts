import type {
  IDoctorDesignResults,
  RunMode,
  ScientificSpec,
  DesignsPayload,
  SmallMolPayload,
  EvalPayload,
  VerdictsPayload,
  ProvenancePayload,
  LabLogEvent,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function getRunArtifactUrl(path: string, download = false): string {
  const params = new URLSearchParams({ path });
  if (download) params.set("download", "true");
  return `${API_BASE}/api/run-artifact?${params.toString()}`;
}

export async function getBinderPdb(path: string): Promise<string | null> {
  try {
    const res = await fetch(
      `${API_BASE}/api/binder-pdb?path=${encodeURIComponent(path)}`
    );
    if (!res.ok) return null;
    const data = await res.json();
    return data.pdb_data || null;
  } catch {
    return null;
  }
}

export async function getProteinPDB(pdbId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/protein/${pdbId}`);
  const data = await res.json();
  return data.pdb_data;
}

export async function startDesignRun(
  mode: RunMode
): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) {
    throw new Error(`Failed to start run: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getDesignResults(
  jobId: string
): Promise<
  | IDoctorDesignResults
  | {
      status: "running" | "failed" | "pending";
      agent_status?: Record<string, string>;
      current_step?: string;
      error?: string;
    }
> {
  const res = await fetch(`${API_BASE}/api/results/${jobId}`);
  if (!res.ok) throw new Error(`Failed to get results: ${res.statusText}`);
  return res.json();
}

export function pollDesignRun(
  jobId: string,
  onAgentUpdate: (agent: string, status: string) => void,
  onComplete: () => void,
  onError: (err: string) => void,
  onStepUpdate?: (step: string) => void,
  onLabLog?: (events: LabLogEvent[]) => void
): () => void {
  let cancelled = false;

  async function poll() {
    while (!cancelled) {
      try {
        const res = await fetch(`${API_BASE}/api/results/${jobId}`);
        if (!res.ok) {
          onError(`Server error: ${res.status}`);
          return;
        }
        const data = await res.json();

        if (data.status === "completed") {
          onComplete();
          return;
        }
        if (data.status === "failed") {
          onError(data.error || "Pipeline failed");
          return;
        }

        if (data.agent_status) {
          for (const [agent, status] of Object.entries(data.agent_status)) {
            onAgentUpdate(agent, status as string);
          }
        }

        if (data.current_step && onStepUpdate) {
          onStepUpdate(data.current_step);
        }
        if (Array.isArray(data.lab_log) && onLabLog) {
          onLabLog(data.lab_log as LabLogEvent[]);
        }
      } catch {
        if (!cancelled) {
          onError("Connection lost");
        }
        return;
      }

      await new Promise((r) => setTimeout(r, 500));
    }
  }

  poll();
  return () => {
    cancelled = true;
  };
}

export async function loadLatestRun(): Promise<IDoctorDesignResults | null> {
    const res = await fetch(`${API_BASE}/api/runs/latest`);
    if (res.status === 404) return null;
    if (!res.ok) {
      throw new Error(`Backend returned ${res.status} while loading the latest run`);
    }
    const data = await res.json();
    const spec = data.spec || data.scientific_spec;
    if (!spec || !data.designs || !data.provenance) return null;
    return {
      status: "completed",
      run_id: data.run_id,
      hypothesis: data.hypothesis || spec.hypothesis || "",
      scientific_spec: spec,
      designs: data.designs,
      smallmol: data.smallmol,
      eval: data.eval,
      verdicts: data.verdicts,
      experiment_md: data.experiment_md || "",
      provenance: data.provenance,
      agent_traces: data.agent_traces || [],
      lab_log: data.lab_log || [],
      loop_history: data.loop_history || undefined,
      loop_termination_reason: data.loop_termination_reason || null,
      complex_scores: data.complex_scores || undefined,
      checkpointed: Boolean(data.checkpointed),
    };
}

export async function loadFixtureResults(): Promise<IDoctorDesignResults> {
  const base = "/fixtures";
  const [spec, designs, smallmol, evalPayload, verdicts, provenance, experimentMd] =
    await Promise.all([
      fetch(`${base}/spec.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing spec fixture");
        return r.json() as Promise<ScientificSpec>;
      }),
      fetch(`${base}/designs.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing designs fixture");
        return r.json() as Promise<DesignsPayload>;
      }),
      fetch(`${base}/smallmol.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing smallmol fixture");
        return r.json() as Promise<SmallMolPayload>;
      }),
      fetch(`${base}/eval.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing eval fixture");
        return r.json() as Promise<EvalPayload>;
      }),
      fetch(`${base}/verdicts.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing verdicts fixture");
        return r.json() as Promise<VerdictsPayload>;
      }),
      fetch(`${base}/provenance.example.json`).then((r) => {
        if (!r.ok) throw new Error("Missing provenance fixture");
        return r.json() as Promise<ProvenancePayload>;
      }),
      fetch(`${base}/experiment.example.md`).then((r) => {
        if (!r.ok) throw new Error("Missing experiment fixture");
        return r.text();
      }),
    ]);

  return {
    status: "completed",
    hypothesis: spec.hypothesis || verdicts.hypothesis || "",
    scientific_spec: spec,
    designs,
    smallmol,
    eval: evalPayload,
    verdicts,
    experiment_md: experimentMd,
    provenance,
    agent_traces: [],
    lab_log: [],
  };
}

export async function runWithFixtureFallback(
  mode: RunMode,
  onAgentUpdate: (agent: string, status: string) => void,
  onStepUpdate: (step: string) => void,
  onLabLog?: (events: LabLogEvent[]) => void
): Promise<IDoctorDesignResults> {
  try {
    const { job_id } = await startDesignRun(mode);
    return await new Promise<IDoctorDesignResults>((resolve, reject) => {
      pollDesignRun(
        job_id,
        onAgentUpdate,
        async () => {
          try {
            const data = await getDesignResults(job_id);
            if (data.status === "completed") {
              resolve(data as IDoctorDesignResults);
            } else {
              reject(new Error("Unexpected status after complete"));
            }
          } catch (e) {
            reject(e);
          }
        },
        (err) => reject(new Error(err)),
        onStepUpdate,
        onLabLog
      );
    });
  } catch (error) {
    if (mode !== "fixture") {
      throw error;
    }
    const agents = [
      "evidence",
      "designer",
      "structure",
      "novelty",
      "complex",
      "physics",
      "evaluate",
      "critic",
      "experiment",
    ] as const;
    const steps = [
      "Reading resistance literature…",
      "Designing sequences under spec constraints…",
      "Loading structure metrics…",
      "Checking PDB novelty with MMseqs2…",
      "Evaluating G12C and resistance complexes…",
      "Docking small-molecule control…",
      "Scoring vs known Ki…",
      "Critic reviewing survivors…",
      "Writing Monday lab card…",
    ];
    const log: LabLogEvent[] = [];

    for (let i = 0; i < agents.length; i++) {
      onStepUpdate(steps[i]);
      onAgentUpdate(agents[i], "running");
      log.push({ agent: agents[i], kind: "step", text: steps[i] });
      onLabLog?.(log.slice());
      await new Promise((r) => setTimeout(r, 280));
      onAgentUpdate(agents[i], "completed");
    }

    const fixture = await loadFixtureResults();
    return { ...fixture, lab_log: log };
  }
}

export function downloadBlob(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function isDemoData(provenance: ProvenancePayload | undefined): boolean {
  if (!provenance) return true;
  if (provenance.mode === "fixture" || provenance.mode === "replay") return true;
  return Object.values(provenance.nodes || {}).some((n) => n === "fixture");
}
