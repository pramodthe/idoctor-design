"""Evaluator agent — oracle metrics → eval.json."""

from __future__ import annotations

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


# What each resistance mutation changes in the pocket, and which binder features
# are expected to compensate. Keys: (base penalty kcal, aromatic-reliance coeff,
# positive-charge compensation coeff, negative-charge coeff).
#
# Y96D / H95D introduce a carboxylate where an aromatic/imidazole sat: a binder
# carrying basic residues can form a compensating salt bridge, while one that
# leaned on pi-stacking loses its anchor. R68S deletes a basic side chain, so an
# acidic binder loses the partner it was pairing with. Y96C removes the aromatic
# without adding charge, so only the stacking term applies.
_MUTATION_CHEMISTRY: dict[str, tuple[float, float, float, float]] = {
    "Y96D": (2.0, 3.0, -4.0, 1.5),
    "H95D": (1.8, 2.0, -3.5, 1.5),
    "Y96C": (2.2, 3.5, 0.0, 0.0),
    "R68S": (1.6, 0.0, 0.0, 4.0),
}
_DEFAULT_CHEMISTRY = (1.5, 1.0, -1.0, 1.0)


def _composition(sequence: str) -> tuple[float, float, float]:
    """Fractions of basic, acidic and aromatic residues in a binder sequence."""
    seq = "".join(c for c in (sequence or "").upper() if c.isalpha())
    n = max(len(seq), 1)
    basic = sum(1 for c in seq if c in "KR") / n
    acidic = sum(1 for c in seq if c in "DE") / n
    aromatic = sum(1 for c in seq if c in "FWY") / n
    return basic, acidic, aromatic


def _live_heuristic_design_scores(designs: dict | list, spec: dict | None) -> dict[str, dict]:
    """Sequence-derived WT-vs-mutant interface proxy for live designs.

    This is a proxy, not physics: no complex is folded and nothing is docked. But
    every number here is a function of the design's own sequence composition and
    its measured structure confidence, so changing a sequence changes its scores
    and no design is favoured by its position in the list. Designs whose fold came
    back from a real structure predictor are marked higher confidence than those
    still carrying heuristic_v1 estimates.

    More negative = better, matching the docking convention used elsewhere.
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
    mut_ids = [m for m in mut_ids if m in _MUTATION_CHEMISTRY] or list(_DEFAULT_MUTANTS)

    out: dict[str, dict] = {}
    for d in design_list:
        did = d.get("id")
        if not did:
            continue
        if d.get("provenance") == "fixture":
            continue

        sequence = d.get("sequence") or ""
        if not sequence:
            continue
        basic, acidic, aromatic = _composition(sequence)

        plddt = d.get("plddt")
        iptm = d.get("iptm")
        fold_method = str(d.get("fold_method") or "")
        measured = bool(fold_method) and not fold_method.startswith("heuristic")

        # WT affinity proxy scales with how confident the fold is. A binder nobody
        # can fold confidently does not get to claim a strong interface.
        confidence = (float(plddt) / 100.0) if plddt is not None else 0.7
        if iptm is not None:
            confidence = (confidence + float(iptm)) / 2.0
        wt = -5.5 - 4.0 * max(0.0, min(1.0, confidence))

        mutants: dict[str, float] = {}
        for mid in mut_ids:
            base, arom_coeff, pos_coeff, neg_coeff = _MUTATION_CHEMISTRY.get(
                mid, _DEFAULT_CHEMISTRY
            )
            # Positive delta = worse binding against the mutant than against WT.
            delta = (
                base
                + arom_coeff * aromatic
                + pos_coeff * basic
                + neg_coeff * acidic
            )
            delta = max(0.1, min(5.0, delta))
            mutants[mid] = round(wt + delta, 2)

        note = (
            "Sequence-derived interface proxy (not docking/MD/complex folding). "
            "Delta per mutation is computed from this binder's own basic/acidic/"
            "aromatic composition against the chemistry each mutation changes; "
            f"WT term scales with fold confidence ({'measured: ' + fold_method if measured else 'heuristic fold estimate'}). "
            "Treat as a screening prior, not evidence of binding."
        )
        out[did] = {
            "wt_score": round(wt, 2),
            "mutant_scores": mutants,
            "method": "sequence_proxy_v2",
            "confidence": "measured_fold" if measured else "estimated_fold",
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
