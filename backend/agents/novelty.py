"""Novelty verification agent — RCSB PDB sequence search via MMseqs2."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from backend.config import FAST_DEV
from backend.tools.novelty import NoveltyUnavailable, search_pdb_sequence


AGENT_NAME = "novelty"
AGENT_DISPLAY = "PDB novelty check"


def _trusted_existing(design: dict) -> bool:
    method = str((design.get("novelty") or {}).get("method") or "").lower()
    return any(token in method for token in ("rcsb", "mmseqs", "blast", "foldseek"))


def _replace_failures(state: dict, prefix: str, current: list[str]) -> list[str]:
    prior = [
        str(item)
        for item in (state.get("verification_failures") or [])
        if not str(item).startswith(prefix)
    ]
    return [*prior, *current]


def run_novelty(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    designs_doc = copy.deepcopy(state.get("designs") or {})
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    traces = list(state.get("agent_traces") or [])
    steps: list[dict] = []
    tool_calls: list[dict] = []
    failures: list[str] = []
    checked = 0

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Checking candidate sequences against the PDB...")

    if mode == "replay":
        node_source = "cached"
        steps.append({"action": "Reuse novelty results", "detail": "designs.json"})
    elif mode == "fixture":
        node_source = "fixture"
        steps.append({"action": "Keep fixture novelty", "detail": "No network call in fixture mode"})
    elif FAST_DEV:
        node_source = "skipped"
        failures.append("novelty:skipped_fast_mode")
        steps.append(
            {
                "action": "RCSB novelty skipped",
                "detail": "IDOCTOR_FAST=1; unverified identities remain non-promotable",
            }
        )
    else:
        node_source = "live"
        max_identity = float(
            ((state.get("scientific_spec") or {}).get("success_bars") or {}).get(
                "max_pdb_identity", 0.7
            )
        )
        for design in designs_doc.get("designs") or []:
            if _trusted_existing(design):
                continue
            did = str(design.get("id") or "design")
            try:
                result = search_pdb_sequence(design.get("sequence") or "")
                design["novelty"] = result
                checked += 1
                tool_calls.append(
                    {
                        "tool": "rcsb.mmseqs2",
                        "detail": (
                            f"{did}: max identity={result['identity']:.3f}; "
                            f"bar={max_identity:.3f}; hits={len(result['hits'])}"
                        ),
                    }
                )
            except NoveltyUnavailable as exc:
                design["novelty"] = {
                    "identity": None,
                    "method": "rcsb_mmseqs2_failed",
                    "error": str(exc),
                }
                failures.append(f"novelty:{did}:{exc}")
        if failures:
            node_source = "skipped"
        steps.append(
            {
                "action": "RCSB MMseqs2 search",
                "detail": f"verified={checked}; failures={len(failures)}",
            }
        )

    (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
    provenance_nodes[AGENT_NAME] = node_source
    elapsed = time.perf_counter() - start
    traces.append(
        {
            "agent": AGENT_NAME,
            "agent_name": AGENT_DISPLAY,
            "duration_seconds": round(elapsed, 2),
            "model": None,
            "input_summary": f"mode={mode}; {len(designs_doc.get('designs') or [])} sequences",
            "output_summary": f"PDB novelty verified={checked}; failures={len(failures)}",
            "steps": steps,
            "tool_calls": tool_calls,
            "llm_calls": [],
        }
    )
    return {
        "designs": designs_doc,
        "verification_failures": _replace_failures(state, "novelty:", failures),
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
