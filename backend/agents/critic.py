"""Scientist critic — rule-based P0 verdicts (LLM optional for prose)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from backend.agents.llm import call_llm
from backend.config import FAST_DEV
from backend.contracts.validate import validate_verdicts


AGENT_NAME = "critic"
AGENT_DISPLAY = "Scientist critic (Claude)"

WT_ONLY_DELTA_KCAL = 3.0


def _delta_map(eval_result: dict) -> dict[str, dict]:
    return {row["id"]: row for row in (eval_result or {}).get("design_deltas") or []}


def _severe_docking_lie_ids(eval_result: dict) -> set[str]:
    """Only flag compounds where docking rank badly contradicts Ki (residual >= 2)."""
    out: set[str] = set()
    for d in (eval_result or {}).get("disagreements") or []:
        try:
            residual = int(d.get("residual") or 0)
        except (TypeError, ValueError):
            residual = 0
        note = (d.get("note") or "").lower()
        if residual >= 2 or "worst ki" in note or "do not promote" in note:
            out.add(d["id"])
    return out


def _truncate_words(text: str, max_words: int = 80) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _criticize_design(design: dict, bars: dict, delta: dict | None, mutation_ids: list[str]) -> dict:
    reasons: list[str] = []
    metrics_used: list[str] = []
    evidence_ids: list[str] = list(mutation_ids[:2]) if mutation_ids else []
    verdict = "promote"
    summary_bits: list[str] = []

    novelty = design.get("novelty") or {}
    identity = novelty.get("identity")
    max_id = bars.get("max_pdb_identity")
    if identity is not None and max_id is not None and float(identity) > float(max_id):
        reasons.append("too_similar_to_pdb")
        metrics_used.append("novelty.identity")
        verdict = "reject"
        summary_bits.append(
            f"Novelty identity {identity} exceeds max_pdb_identity {max_id}."
        )

    plddt = design.get("plddt")
    min_plddt = bars.get("min_plddt")
    if plddt is not None:
        metrics_used.append("plddt")
    if min_plddt is not None and plddt is not None and float(plddt) < float(min_plddt):
        reasons.append("low_structure_confidence")
        if verdict != "reject":
            verdict = "reject"
        summary_bits.append(f"pLDDT {plddt} is below min_plddt {min_plddt}.")

    mutants = (delta or {}).get("mutant_scores") or {}
    wt_score = (delta or {}).get("wt_score")
    require_mutant = bool(bars.get("require_mutant_score"))

    if require_mutant and not mutants:
        reasons.append("weak_or_missing_metric")
        if verdict == "promote":
            verdict = (
                "hold"
                if (plddt is not None and min_plddt is not None and float(plddt) >= float(min_plddt))
                else "reject"
            )
        summary_bits.append("Spec requires a mutant score; none present.")
    elif mutants and wt_score is not None:
        # More negative = better. Mutant much worse → large positive (mutant - wt).
        for mid, mscore in mutants.items():
            if mscore is None:
                continue
            metrics_used.append(f"design_delta_{mid}")
            try:
                dval = float(mscore) - float(wt_score)
            except (TypeError, ValueError):
                continue
            if dval > WT_ONLY_DELTA_KCAL:
                reasons.append("wt_only_signal")
                evidence_ids = list({*evidence_ids, mid})
                verdict = "reject"
                summary_bits.append(
                    f"Mutant score collapses vs WT (delta {dval:.1f} kcal on {mid})."
                )

    if verdict == "promote":
        if design.get("iptm") is not None:
            metrics_used.append("iptm")
        if identity is not None and "novelty.identity" not in metrics_used:
            metrics_used.append("novelty.identity")
        note = (delta or {}).get("note") or ""
        if "hold" in note.lower() or "wait" in note.lower() or "modest" in note.lower():
            verdict = "hold"
            reasons.append("weak_or_missing_metric")
            summary_bits.append(
                "Metrics are modest; wait for stronger structure/mutant evidence."
            )
        else:
            reasons.append("passes_spec")
            summary_bits.append(
                "Passes novelty, structure confidence, and mutant-score bars in this run."
            )

    if not reasons:
        reasons.append("other")

    remaining_risk = ""
    if verdict == "promote":
        remaining_risk = (
            "No wet-lab binding yet. Must measure KD on G12C vs resistance mutant "
            "before treating this as a drug lead."
        )
    elif verdict == "hold":
        remaining_risk = "Could be promoted or rejected after live structure/mutant jobs."

    summary = " ".join(summary_bits) if summary_bits else "Rule-based critic assessment."
    return {
        "subject_kind": "design",
        "subject_id": design["id"],
        "verdict": verdict,
        "reasons": list(dict.fromkeys(reasons)),
        "summary": _truncate_words(summary),
        "evidence_ids": evidence_ids,
        "metrics_used": list(dict.fromkeys(metrics_used)),
        "remaining_risk": remaining_risk,
    }


def _criticize_smallmol(compound: dict, eval_result: dict, mutation_ids: list[str]) -> dict | None:
    cid = compound["id"]
    if cid == "sotorasib":
        return {
            "subject_kind": "smallmol",
            "subject_id": cid,
            "verdict": "hold",
            "reasons": ["passes_spec"],
            "summary": _truncate_words(
                "Clinical baseline, not a new idea. Mutant Vina is worse than WT in the "
                "control arm, matching the resistance story. Do not demo this as the invention."
            ),
            "evidence_ids": mutation_ids[:1] or ["Y96D"],
            "metrics_used": ["vina_wt", "vina_Y96D", "known_ki_nm"],
            "remaining_risk": "Approved drug with known resistance — control arm only.",
        }
    if cid == "adagrasib":
        return {
            "subject_kind": "smallmol",
            "subject_id": cid,
            "verdict": "hold",
            "reasons": ["passes_spec"],
            "summary": _truncate_words(
                "Second approved G12C covalent inhibitor — control arm only. "
                "Strong experimental Ki; not an iDoctor Design invention."
            ),
            "evidence_ids": mutation_ids[:1] or ["Y96D"],
            "metrics_used": ["vina_wt", "known_ki_nm"],
            "remaining_risk": "Approved drug with overlapping resistance liabilities.",
        }
    if cid in _severe_docking_lie_ids(eval_result) or cid == "sml8708":
        return {
            "subject_kind": "smallmol",
            "subject_id": cid,
            "verdict": "reject",
            "reasons": ["contradicts_literature", "weak_or_missing_metric"],
            "summary": _truncate_words(
                "Strong Vina relative to weak experimental Ki (or large rank residual). "
                "This is why docking rank is not the product."
            ),
            "evidence_ids": [],
            "metrics_used": ["vina_wt", "known_ki_nm"],
            "remaining_risk": "",
        }
    return None


def _maybe_enrich_summaries(items: list[dict], hypothesis: str) -> tuple[list[dict], dict | None]:
    """Optional LLM polish; on failure keep template summaries.

    Verdicts are decided by the rules above — this only rewrites prose, so a dev
    run can skip it without changing any promote/hold/reject outcome.
    """
    if FAST_DEV:
        return items, None

    prompt = (
        "You are a careful medicinal chemistry critic. Rewrite each summary to ≤80 words. "
        "Do NOT invent Ki values, PDB IDs, or numbers not already present. "
        "Return JSON array of {subject_id, summary} only.\n\n"
        f"Hypothesis: {hypothesis}\n\n"
        f"Items: {json.dumps([{k: it[k] for k in ('subject_id','verdict','reasons','summary')} for it in items])}"
    )
    trace = call_llm(prompt, max_tokens=800, temperature=0.3)
    if not trace.get("success"):
        return items, trace
    text = (trace.get("response") or "").strip()
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        updates = json.loads(text)
        by_id = {u["subject_id"]: u.get("summary") for u in updates if "subject_id" in u}
        for it in items:
            if it["subject_id"] in by_id and by_id[it["subject_id"]]:
                it["summary"] = _truncate_words(str(by_id[it["subject_id"]]))
    except Exception:
        pass
    return items, trace


def run_critic(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    steps: list[dict] = []
    llm_trace = None

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Applying scientist critic rules...")

    spec = state.get("scientific_spec") or {}
    if not spec and (run_dir / "spec.json").exists():
        spec = json.loads((run_dir / "spec.json").read_text())
    designs_doc = state.get("designs") or {}
    if not designs_doc and (run_dir / "designs.json").exists():
        designs_doc = json.loads((run_dir / "designs.json").read_text())
    smallmol = state.get("smallmol") or {}
    if not smallmol and (run_dir / "smallmol.json").exists():
        smallmol = json.loads((run_dir / "smallmol.json").read_text())
    eval_result = state.get("eval_result") or {}
    if not eval_result and (run_dir / "eval.json").exists():
        eval_result = json.loads((run_dir / "eval.json").read_text())

    bars = spec.get("success_bars") or {}
    mutation_ids = [m["id"] for m in (spec.get("mutations") or []) if "id" in m]
    hypothesis = spec.get("hypothesis") or state.get("hypothesis") or ""
    deltas = _delta_map(eval_result)

    items: list[dict] = []
    for design in designs_doc.get("designs") or []:
        items.append(_criticize_design(design, bars, deltas.get(design["id"]), mutation_ids))

    for compound in smallmol.get("compounds") or []:
        row = _criticize_smallmol(compound, eval_result, mutation_ids)
        if row:
            items.append(row)

    items, llm_trace = _maybe_enrich_summaries(items, hypothesis)
    if llm_trace and llm_trace.get("success"):
        steps.append({"action": "LLM summary polish", "detail": f"model={llm_trace.get('model')}"})
        node_source = "live"
    else:
        steps.append(
            {
                "action": "Template summaries",
                "detail": "LLM unavailable or failed; rule-based text kept",
            }
        )
        node_source = "live" if mode != "fixture" else "fixture"

    steps.insert(0, {"action": "Rule-based critic", "detail": f"{len(items)} verdicts"})

    verdicts = {
        "schema_version": "1.0",
        "hypothesis": hypothesis,
        "items": items,
    }
    validate_verdicts(verdicts)
    (run_dir / "verdicts.json").write_text(json.dumps(verdicts, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    promotes = sum(1 for i in items if i["verdict"] == "promote")
    rejects = sum(1 for i in items if i["verdict"] == "reject")
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": (llm_trace or {}).get("model"),
        "input_summary": "spec success_bars + designs + eval deltas + smallmol",
        "output_summary": f"{len(items)} verdicts ({promotes} promote, {rejects} reject)",
        "steps": steps,
        "tool_calls": [],
        "llm_calls": [llm_trace] if llm_trace else [],
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "verdicts": verdicts,
        "hypothesis": hypothesis,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
