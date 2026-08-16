"""Evaluator agent — oracle metrics → eval.json."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from backend.config import FIXTURES_DIR
from backend.contracts.validate import validate_eval
from backend.evaluation.oracle import evaluate_smallmol_and_designs


AGENT_NAME = "evaluate"
AGENT_DISPLAY = "Score vs experiment"

# Default resistance mutations for heuristic WT-vs-mutant interface scores
_DEFAULT_MUTANTS = ("Y96D", "H95D", "R68S")


def _fixture_design_scores() -> dict[str, dict]:
    """Optional design WT/mutant scores from fixture eval (demo interface numbers)."""
    path = FIXTURES_DIR / "eval.example.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out: dict[str, dict] = {}
    for row in data.get("design_deltas") or []:
        out[row["id"]] = {
            "wt_score": row.get("wt_score"),
            "mutant_scores": row.get("mutant_scores") or {},
            "note": row.get("note", ""),
        }
    return out


def _live_heuristic_design_scores(designs: dict | list, spec: dict | None) -> dict[str, dict]:
    """Deterministic pseudo-interface scores for live designs (not physics).

    More negative = better. Mutant retention is biased by pLDDT/novelty so the
    critic can exercise promote/hold/reject without inventing wet-lab numbers.
    """
    if isinstance(designs, dict):
        design_list = designs.get("designs") or []
    else:
        design_list = designs or []

    mut_ids = [
        m.get("id")
        for m in (spec or {}).get("mutations") or []
        if isinstance(m, dict) and m.get("id")
    ]
    mut_ids = [m for m in mut_ids if m in _DEFAULT_MUTANTS] or list(_DEFAULT_MUTANTS)

    out: dict[str, dict] = {}
    for i, d in enumerate(design_list):
        did = d.get("id")
        if not did:
            continue
        if d.get("provenance") == "fixture":
            continue
        plddt = float(d.get("plddt") or 70.0)
        identity = float((d.get("novelty") or {}).get("identity") or 0.2)
        seed = int(hashlib.sha256(f"{did}-iface".encode()).hexdigest()[:8], 16)
        # WT score in roughly [-10, -6]
        wt = -6.0 - (plddt - 60.0) / 20.0 - (seed % 100) / 200.0
        mutants: dict[str, float] = {}
        for j, mid in enumerate(mut_ids):
            # Top designs retain mutant binding; weaker / high-identity designs collapse
            retain = (i < 2 and identity < 0.4 and plddt >= 75)
            if retain:
                delta = 0.3 + ((seed >> (j * 3)) % 50) / 100.0  # small loss
            elif i < 4:
                delta = 1.5 + ((seed >> (j * 3)) % 80) / 100.0
            else:
                delta = 3.2 + ((seed >> (j * 3)) % 120) / 100.0  # wt_only collapse
            mutants[mid] = round(wt + delta, 2)
        note = (
            "Heuristic interface scores (not docking/MD). "
            "Used so the critic can compare WT vs mutant until Tamarind/complex jobs exist."
        )
        if i >= 4:
            note += " Intentionally WT-biased for reject-path testing."
        out[did] = {
            "wt_score": round(wt, 2),
            "mutant_scores": mutants,
            "note": note,
        }
    return out


def run_evaluator(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    steps: list[dict] = []

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Computing Spearman and disagreements...")

    if mode == "replay" and (run_dir / "eval.json").exists() and state.get("skip_reeval"):
        eval_result = json.loads((run_dir / "eval.json").read_text())
        node_source = "cached"
        steps.append({"action": "Load cached eval", "detail": "eval.json"})
    else:
        smallmol = state.get("smallmol")
        if not smallmol and (run_dir / "smallmol.json").exists():
            smallmol = json.loads((run_dir / "smallmol.json").read_text())
        designs = state.get("designs")
        if not designs and (run_dir / "designs.json").exists():
            designs = json.loads((run_dir / "designs.json").read_text())
        spec = state.get("scientific_spec")
        if not spec and (run_dir / "spec.json").exists():
            spec = json.loads((run_dir / "spec.json").read_text())

        design_scores = state.get("design_scores")
        if design_scores is None:
            if mode == "fixture":
                design_scores = _fixture_design_scores()
            elif mode == "live":
                design_scores = _live_heuristic_design_scores(designs or {}, spec)
                steps.append(
                    {
                        "action": "Live heuristic design scores",
                        "detail": f"{len(design_scores)} designs scored (not physics)",
                    }
                )
            else:
                # replay without skip: prefer existing deltas on designs, else fixture map
                design_scores = _fixture_design_scores()

        eval_result = evaluate_smallmol_and_designs(smallmol, designs, design_scores)
        node_source = "live"
        steps.append(
            {
                "action": "Oracle evaluate",
                "detail": (
                    f"n={eval_result.get('smallmol_n')}, "
                    f"rho={eval_result.get('smallmol_spearman_rho')}, "
                    f"disagreements={len(eval_result.get('disagreements') or [])}"
                ),
            }
        )

    validate_eval(eval_result)
    (run_dir / "eval.json").write_text(json.dumps(eval_result, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": None,
        "input_summary": "smallmol.json + designs + optional interface scores",
        "output_summary": eval_result.get("smallmol_note", "eval.json written"),
        "steps": steps,
        "tool_calls": [{"tool": "oracle.evaluate", "detail": "Spearman + residuals + design_deltas"}],
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "eval_result": eval_result,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
