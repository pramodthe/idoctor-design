"""Physics control arm — small-molecule Vina scores (fixture/cached, enrich from KRAS library)."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from backend.compounds import KRAS_COMPOUNDS
from backend.config import FIXTURES_DIR
from backend.contracts.validate import validate_smallmol


AGENT_NAME = "physics"
AGENT_DISPLAY = "Docking control (AutoDock Vina)"


def _enrich_from_kras_library(smallmol: dict) -> dict:
    """Fill known_ki_nm from KRAS_COMPOUNDS when missing."""
    by_id = {c["id"]: c for c in KRAS_COMPOUNDS}
    for c in smallmol.get("compounds") or []:
        known = by_id.get(c["id"])
        if not known:
            continue
        if c.get("known_ki_nm") is None and known.get("known_ki_nm") is not None:
            c["known_ki_nm"] = known["known_ki_nm"]
        if not c.get("smiles") and known.get("smiles"):
            c["smiles"] = known["smiles"]
        if not c.get("name") and known.get("name"):
            c["name"] = known["name"]
    return smallmol


def _build_live_smallmol(fixture: dict) -> dict:
    """Include all KRAS_COMPOUNDS with known_ki; reuse vina from fixture where ids match."""
    fixture_by_id = {c["id"]: c for c in (fixture.get("compounds") or [])}
    compounds = []
    for known in KRAS_COMPOUNDS:
        fx = fixture_by_id.get(known["id"], {})
        compounds.append(
            {
                "id": known["id"],
                "name": known.get("name") or fx.get("name") or known["id"],
                "smiles": known.get("smiles") or fx.get("smiles") or "",
                "known_ki_nm": known.get("known_ki_nm"),
                "vina_wt": fx.get("vina_wt"),
                "vina_mutants": fx.get("vina_mutants") or {},
                "pains_flags": fx.get("pains_flags") or [],
                "lipinski_violations": fx.get("lipinski_violations"),
            }
        )
    return {
        "schema_version": fixture.get("schema_version", "1.0"),
        "receptor_pdb_wt": fixture.get("receptor_pdb_wt", "6OIM"),
        "compounds": compounds,
        "note": (
            "Live mode: known_ki_nm from KRAS_COMPOUNDS; vina scores reused from fixture "
            "where compound ids match (cached docking, not a fresh Vina run)."
        ),
    }


def run_physics(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    tool_calls: list[dict] = []
    steps: list[dict] = []
    node_source = "fixture"
    docked_dir = run_dir / "docked"
    docked_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Building small-molecule control scores...")

    smallmol: dict | None = None

    if mode == "replay":
        path = run_dir / "smallmol.json"
        smallmol = json.loads(path.read_text())
        node_source = "cached"
        steps.append({"action": "Load cached smallmol", "detail": str(path)})
    elif mode == "live":
        cached = run_dir / "smallmol.json"
        src = FIXTURES_DIR / "smallmol.example.json"
        fixture = json.loads(src.read_text())
        if cached.exists():
            # Enrich cached with full library
            smallmol = _build_live_smallmol(json.loads(cached.read_text()))
            # Prefer vina from cached file when present
            cached_doc = json.loads(cached.read_text())
            by_c = {c["id"]: c for c in (cached_doc.get("compounds") or [])}
            for c in smallmol["compounds"]:
                prev = by_c.get(c["id"])
                if prev:
                    if prev.get("vina_wt") is not None:
                        c["vina_wt"] = prev["vina_wt"]
                    if prev.get("vina_mutants"):
                        c["vina_mutants"] = prev["vina_mutants"]
            node_source = "cached"
            steps.append({"action": "Enrich cached Vina + KRAS library", "detail": str(cached)})
        else:
            smallmol = _build_live_smallmol(fixture)
            # Honest label: vina values are cached from fixture, ki from compounds.py
            node_source = "cached"
            steps.append(
                {
                    "action": "Build smallmol from KRAS_COMPOUNDS + fixture vina",
                    "detail": str(src),
                }
            )
        tool_calls.append(
            {
                "tool": "vina.cached",
                "detail": "No fresh AutoDock Vina run; vina from fixture where ids match",
            }
        )
    else:
        src = FIXTURES_DIR / "smallmol.example.json"
        shutil.copy2(src, run_dir / "smallmol.json")
        smallmol = json.loads((run_dir / "smallmol.json").read_text())
        node_source = "fixture"
        steps.append({"action": "Load fixture KRAS scores", "detail": str(src)})
        tool_calls.append(
            {
                "tool": "vina.skip",
                "detail": "Fixture path: AutoDock Vina not required",
            }
        )

    smallmol = _enrich_from_kras_library(smallmol)
    validate_smallmol(smallmol)
    (run_dir / "smallmol.json").write_text(json.dumps(smallmol, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    n = len(smallmol.get("compounds") or [])
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": None,
        "input_summary": f"mode={mode}; KRAS control library",
        "output_summary": f"{n} compounds in smallmol.json (node={node_source})",
        "steps": steps,
        "tool_calls": tool_calls,
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "smallmol": smallmol,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
