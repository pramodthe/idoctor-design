"""Evidence agent — Paperclip / Europe PMC live or fixture spec.json."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from backend.config import FAST_DEV, FIXTURES_DIR, RUNS_DIR
from backend.contracts.validate import validate_spec
from backend.tools import paperclip


AGENT_NAME = "evidence"
AGENT_DISPLAY = "Literature & databases (Paperclip)"


def _newest_live_spec() -> Path | None:
    """Most recent spec.json produced by a live literature search, for dev reuse."""
    candidates = []
    for run in RUNS_DIR.glob("*/"):
        spec, prov = run / "spec.json", run / "provenance.json"
        if not (spec.is_file() and prov.is_file()):
            continue
        try:
            nodes = json.loads(prov.read_text()).get("nodes") or {}
        except (json.JSONDecodeError, OSError):
            continue
        if nodes.get("evidence") == "live":
            candidates.append(spec)
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def run_evidence(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    tool_calls: list[dict] = []
    steps: list[dict] = []
    scientific_spec: dict | None = None
    node_source = "fixture"

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Gathering literature evidence...")

    if mode == "replay":
        spec_path = run_dir / "spec.json"
        if not spec_path.exists():
            raise FileNotFoundError(f"Replay missing {spec_path}")
        scientific_spec = json.loads(spec_path.read_text())
        node_source = "cached"
        steps.append({"action": "Load cached spec", "detail": str(spec_path)})
    else:
        if mode == "live" and FAST_DEV:
            cached = _newest_live_spec()
            if cached:
                scientific_spec = json.loads(cached.read_text())
                node_source = "live"
                steps.append(
                    {
                        "action": "Reused cached literature spec (IDOCTOR_FAST)",
                        "detail": f"Dev mode — no new search. From {cached.parent.name}",
                    }
                )

        if scientific_spec is None and mode == "live":
            tool_calls.append(
                {
                    "tool": "paperclip.gather_kras_resistance_evidence",
                    "detail": "Paperclip or Europe PMC + ClinicalTrials.gov",
                }
            )
            try:
                spec, raw = paperclip.gather_kras_resistance_evidence()
                (run_dir / "paperclip_raw.json").write_text(json.dumps(raw, indent=2))
                if spec is not None:
                    scientific_spec = spec
                    # node_source live if provenance live (any real pmid preferred)
                    node_source = (
                        "live" if scientific_spec.get("provenance") == "live" else "fixture"
                    )
                    steps.append(
                        {
                            "action": "Live evidence harvest",
                            "detail": (
                                f"provenance={scientific_spec.get('provenance')}; "
                                f"mutations={len(scientific_spec.get('mutations') or [])}"
                            ),
                        }
                    )
                else:
                    steps.append(
                        {
                            "action": "Live evidence returned no spec",
                            "detail": "Falling back to fixture",
                        }
                    )
            except Exception as e:  # noqa: BLE001
                steps.append({"action": "Live evidence failed", "detail": str(e)})

        if scientific_spec is None:
            src = FIXTURES_DIR / "spec.example.json"
            dest = run_dir / "spec.json"
            shutil.copy2(src, dest)
            scientific_spec = json.loads(dest.read_text())
            scientific_spec["provenance"] = "fixture"
            dest.write_text(json.dumps(scientific_spec, indent=2))
            raw_path = run_dir / "paperclip_raw.json"
            if not raw_path.exists():
                raw_path.write_text(
                    json.dumps(
                        {
                            "source": "fixture",
                            "note": "Paperclip/literature not used; copied spec.example.json",
                            "europepmc": [],
                            "clinicaltrials": [],
                            "queries": [],
                        },
                        indent=2,
                    )
                )
            node_source = "fixture"
            steps.append({"action": "Load fixture spec", "detail": str(src)})

    validate_spec(scientific_spec)
    (run_dir / "spec.json").write_text(json.dumps(scientific_spec, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": None,
        "input_summary": f"mode={mode}",
        "output_summary": (
            f"spec with {len(scientific_spec.get('mutations', []))} mutations; "
            f"hypothesis set; provenance={scientific_spec.get('provenance')}"
        ),
        "steps": steps,
        "tool_calls": tool_calls,
    }

    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "scientific_spec": scientific_spec,
        "hypothesis": scientific_spec.get("hypothesis", ""),
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
