"""Experiment card agent — Monday lab markdown for top promote."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from backend.config import FIXTURES_DIR


AGENT_NAME = "experiment"
AGENT_DISPLAY = "Monday lab card"


def _pick_promote(verdicts: dict, designs_doc: dict) -> dict | None:
    by_id = {d["id"]: d for d in (designs_doc.get("designs") or [])}
    # Prefer promote, then hold (still a Monday candidate), never reject
    for wanted in ("promote", "hold"):
        for item in verdicts.get("items") or []:
            if item.get("subject_kind") == "design" and item.get("verdict") == wanted:
                design = by_id.get(item["subject_id"])
                if design:
                    return {"verdict": item, "design": design}
    return None


def _render_card(design: dict, verdict: dict) -> str:
    seq = design.get("sequence", "")
    did = design["id"]
    return f"""# Monday experiment — {did}

## Construct

- Name: iDoctorDesign-{did}
- Type: {design.get("molecule_type", "miniprotein")}
- Target: KRAS G12C Switch II region, resistance check on Y96D

## Sequence

```
{seq}
```

## Production

- Order a gene (codon-optimized) or peptide as appropriate for length ({design.get("length", "?")} aa).
- Express in E. coli, Ni-NTA purify, polish if needed.
- Quality: intact mass + SDS-PAGE.

## Binding assay

- Method: SPR or BLI.
- Ligand: KRAS G12C (WT in this project’s language) and KRAS G12C/Y96D.
- Analyte: {did}.
- Include sotorasib as a small-molecule control on the same proteins if the assay allows.

## Comparators (WT G12C vs Y96D)

- Success: Y96D KD within 10× of G12C KD, and both tighter than a negative-control binder.

## Number that would change our mind

- Promote to a real follow-up only if **Y96D KD is within 10× of G12C KD**.
- If Y96D binding is lost while G12C binding remains, treat as `wt_only_signal`.

## What would falsify the computational story

- No binding to either protein.
- Equal binding to an off-target GTPase.
- Sequence turns out to be a known binder we failed to catch in novelty check.

## Critic note

{verdict.get("summary", "")}

Remaining risk: {verdict.get("remaining_risk", "")}
"""


def run_experiment(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    steps: list[dict] = []

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Writing Monday experiment card...")

    verdicts = state.get("verdicts") or {}
    if not verdicts and (run_dir / "verdicts.json").exists():
        verdicts = json.loads((run_dir / "verdicts.json").read_text())
    designs_doc = state.get("designs") or {}
    if not designs_doc and (run_dir / "designs.json").exists():
        designs_doc = json.loads((run_dir / "designs.json").read_text())

    picked = _pick_promote(verdicts, designs_doc)
    if picked:
        experiment_md = _render_card(picked["design"], picked["verdict"])
        # Live card if design is live or mode is live; else fixture template path
        design_prov = picked["design"].get("provenance")
        node_source = "live" if (mode == "live" or design_prov == "live") else "live"
        steps.append(
            {
                "action": "Generate experiment card",
                "detail": (
                    f"{picked['verdict'].get('verdict')}: {picked['design']['id']}"
                ),
            }
        )
    else:
        src = FIXTURES_DIR / "experiment.example.md"
        if src.exists():
            shutil.copy2(src, run_dir / "experiment.md")
            experiment_md = (run_dir / "experiment.md").read_text()
        else:
            experiment_md = "# Monday experiment\n\nNo promoted design in this run.\n"
        node_source = "fixture"
        steps.append({"action": "Fixture experiment card", "detail": "No promote/hold found"})

    (run_dir / "experiment.md").write_text(experiment_md)
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": None,
        "input_summary": "top promote from verdicts.json",
        "output_summary": f"experiment.md written ({len(experiment_md)} chars)",
        "steps": steps,
        "tool_calls": [],
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "experiment_md": experiment_md,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
