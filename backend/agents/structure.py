"""Structure agent — Tamarind fold metrics or heuristic / fixture pLDDT/ipTM."""

from __future__ import annotations

import json
import time
from pathlib import Path

from backend.tools import tamarind


AGENT_NAME = "structure"
AGENT_DISPLAY = "Fold & complex (Tamarind)"


def run_structure(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    tool_calls: list[dict] = []
    steps: list[dict] = []
    node_source = "fixture"

    structures_dir = run_dir / "structures"
    structures_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Folding designs / loading structure metrics...")

    designs_doc = state.get("designs") or {}
    if not designs_doc and (run_dir / "designs.json").exists():
        designs_doc = json.loads((run_dir / "designs.json").read_text())

    designs_live = any(
        d.get("provenance") == "live" for d in (designs_doc.get("designs") or [])
    )

    if mode == "replay":
        node_source = "cached"
        steps.append({"action": "Reuse cached structure metrics", "detail": str(structures_dir)})
    else:
        live_ok = False
        if mode == "live":
            try:
                seqs = [
                    {"id": d["id"], "sequence": d["sequence"]}
                    for d in (designs_doc.get("designs") or [])
                ]
                tool_calls.append(
                    {"tool": "tamarind.submit_fold", "detail": f"{len(seqs)} sequences"}
                )
                result = tamarind.submit_fold(
                    seqs,
                    structures_dir=str(structures_dir),
                    max_jobs=2,
                    timeout=600,
                )
                if result:
                    live_ok = True
                    node_source = "live"
                    job_type = result.get("job_type") or "tamarind"
                    by_id = {m["id"]: m for m in result.get("metrics", []) if "id" in m}
                    for d in designs_doc.get("designs") or []:
                        m = by_id.get(d["id"])
                        if not m:
                            continue
                        if m.get("plddt") is not None:
                            d["plddt"] = m["plddt"]
                        if m.get("iptm") is not None:
                            d["iptm"] = m["iptm"]
                        if m.get("pdb_path"):
                            d["pdb_path"] = m["pdb_path"]
                        d["fold_method"] = f"tamarind:{m.get('job_type') or job_type}"
                        if m.get("job_name"):
                            d["tamarind_job"] = m["job_name"]
                    (structures_dir / "README.txt").write_text(
                        f"Structure metrics from Tamarind live tool `{job_type}`. "
                        "Do not conflate with docking affinity.\n"
                    )
                    steps.append(
                        {
                            "action": "Tamarind fold",
                            "detail": f"tool={job_type}; metrics={len(by_id)}",
                        }
                    )
            except tamarind.TamarindUnavailable as e:
                steps.append({"action": "Tamarind unavailable", "detail": str(e)})

            if not live_ok:
                # Heuristic fallback when designs are live
                if designs_live:
                    tool_calls.append(
                        {
                            "tool": "tamarind.apply_heuristic_metrics",
                            "detail": "heuristic_v1 — not AlphaFold/Tamarind",
                        }
                    )
                    designs_doc = tamarind.apply_heuristic_metrics(designs_doc)
                    node_source = "live"
                    (structures_dir / "README.txt").write_text(
                        "Tamarind unavailable. Fold metrics are heuristic_v1 from "
                        "sequence_design.estimate_fold_metrics — NOT Tamarind/AlphaFold/"
                        "ColabFold. Do not claim Proto Modal or Tamarind structure prediction.\n"
                    )
                    steps.append(
                        {
                            "action": "Heuristic fold metrics",
                            "detail": "Applied heuristic_v1; node=live (designs were live)",
                        }
                    )
                else:
                    node_source = "fixture"
                    (structures_dir / "README.txt").write_text(
                        "Structure PDBs not generated. Metrics come from designs.json "
                        "(fixture). Tamarind was unavailable or skipped.\n"
                    )
                    steps.append(
                        {
                            "action": "Fixture structure metrics",
                            "detail": "Kept pLDDT/ipTM from fixture designs",
                        }
                    )
        else:
            node_source = "fixture"
            (structures_dir / "README.txt").write_text(
                "Structure PDBs not generated. Metrics come from designs.json "
                "(fixture or prior run). Tamarind was unavailable or skipped.\n"
            )
            steps.append(
                {
                    "action": "Fixture structure metrics",
                    "detail": "Kept pLDDT/ipTM from designs; structures/ placeholder written",
                }
            )

    (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": None,
        "input_summary": f"mode={mode}; {len(designs_doc.get('designs') or [])} designs",
        "output_summary": f"structures dir ready; node={node_source}",
        "steps": steps,
        "tool_calls": tool_calls,
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "designs": designs_doc,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
