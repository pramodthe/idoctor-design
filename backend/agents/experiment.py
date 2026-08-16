"""Experiment card agent — Monday lab markdown for top promote."""

from __future__ import annotations

import json
import time
from pathlib import Path

from backend.agents.llm import call_llm
from backend.config import FAST_DEV, FIXTURES_DIR


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
    status = str(verdict.get("verdict") or "hold").upper()
    return f"""# Monday experiment — {did} [{status}]

> Computational status: **{status}**. A HOLD candidate is an evidence-gathering
> experiment, not a promoted lead.

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


def _render_no_candidate(verdicts: dict) -> str:
    loop = verdicts.get("loop") or {}
    reasons = sorted(
        {
            reason
            for item in (verdicts.get("items") or [])
            if item.get("subject_kind") == "design"
            for reason in (item.get("reasons") or [])
        }
    )
    termination = loop.get("termination_reason") or loop.get("decision_reason") or "no_candidate"
    reason_text = ", ".join(reasons) if reasons else "no design candidates"
    missing_evidence = any(
        reason in {"evidence_tool_failure", "missing_novelty", "missing_complex_evaluation"}
        for reason in reasons
    )
    if missing_evidence:
        next_action = (
            "Run the missing novelty or complex-evaluation tool, then restart the bounded "
            "loop. Do not substitute another generated sequence for missing scientific evidence."
        )
    else:
        next_action = (
            "Redesign against the failed gates above, then restart the bounded loop with a new "
            "candidate. Keep the same falsification thresholds so the next result is comparable."
        )
    return f"""# Monday experiment — no candidate promoted

The autonomous verification loop stopped with **{termination}**.

No design is eligible for a binding experiment as a promoted lead. The blocking
evidence or design failures were: `{reason_text}`.

## Next action

{next_action}
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
    llm_trace = None
    if picked:
        experiment_md = _render_card(picked["design"], picked["verdict"])
        design_prov = picked["design"].get("provenance")
        node_source = "live" if (mode == "live" or design_prov == "live") else "fixture"
        steps.append(
            {
                "action": "Generate experiment card",
                "detail": (
                    f"{picked['verdict'].get('verdict')}: {picked['design']['id']}"
                ),
            }
        )
        if mode == "live" and not FAST_DEV:
            from backend.agents.lab_log import emit

            emit(progress_cb, AGENT_NAME, "thought", "Claude rewriting Monday card (keep IDs/sequence)")
            llm_trace = call_llm(
                "Rewrite this Monday wet-lab card for a scientist. Keep every sequence, "
                "design id, and numeric threshold unchanged. Do not invent assays or IDs.\n\n"
                + experiment_md,
                max_tokens=900,
            )
            if llm_trace.get("success") and (llm_trace.get("response") or "").strip():
                experiment_md = llm_trace["response"].strip()
                steps.append(
                    {
                        "action": "Claude card prose",
                        "detail": f"model={llm_trace.get('model')}",
                    }
                )
                emit(progress_cb, AGENT_NAME, "output", experiment_md[:400])
            else:
                steps.append(
                    {
                        "action": "Claude card skipped",
                        "detail": llm_trace.get("error")
                        or llm_trace.get("anthropic_error")
                        or "template kept",
                    }
                )
    else:
        if mode == "fixture":
            src = FIXTURES_DIR / "experiment.example.md"
            if src.exists():
                experiment_md = src.read_text()
            else:
                experiment_md = _render_no_candidate(verdicts)
            node_source = "fixture"
            steps.append(
                {"action": "Fixture experiment card", "detail": "No promote/hold found"}
            )
        else:
            experiment_md = _render_no_candidate(verdicts)
            node_source = "live" if mode == "live" else "cached"
            steps.append(
                {
                    "action": "Write no-promotion report",
                    "detail": (verdicts.get("loop") or {}).get("termination_reason")
                    or "no promote/hold found",
                }
            )

    (run_dir / "experiment.md").write_text(experiment_md)
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": (llm_trace or {}).get("model") if (llm_trace or {}).get("success") else None,
        "input_summary": "top promote from verdicts.json",
        "output_summary": f"experiment.md written ({len(experiment_md)} chars)",
        "steps": steps,
        "tool_calls": [],
        "llm_calls": [llm_trace] if llm_trace else [],
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "experiment_md": experiment_md,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
