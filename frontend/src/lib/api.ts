import type {
  IDoctorDesignResults,
  RunMode,
  ScientificSpec,
  DesignsPayload,
  SmallMolPayload,
  EvalPayload,
  VerdictsPayload,
  ProvenancePayload,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

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
  onStepUpdate?: (step: string) => void
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
  try {
    const res = await fetch(`${API_BASE}/api/runs/latest`);
    if (!res.ok) return null;
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
    };
  } catch {
    return null;
  }
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
  };
}

export async function runWithFixtureFallback(
  mode: RunMode,
  onAgentUpdate: (agent: string, status: string) => void,
  onStepUpdate: (step: string) => void
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
        onStepUpdate
      );
    });
  } catch {
    const agents = [
      "evidence",
      "designer",
      "structure",
      "physics",
      "evaluate",
      "critic",
      "experiment",
    ] as const;
    const steps = [
      "Reading resistance literature…",
      "Designing sequences under spec constraints…",
      "Folding designs…",
      "Docking small-molecule control…",
      "Scoring vs known Ki…",
      "Critic reviewing survivors…",
      "Writing Monday lab card…",
    ];

    for (let i = 0; i < agents.length; i++) {
      onStepUpdate(steps[i]);
      onAgentUpdate(agents[i], "running");
      await new Promise((r) => setTimeout(r, 280));
      onAgentUpdate(agents[i], "completed");
    }

    return loadFixtureResults();
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
