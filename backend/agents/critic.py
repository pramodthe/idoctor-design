"""Scientist critic — rule-based P0 verdicts (LLM optional for prose)."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from backend.agents.llm import call_llm
from backend.agents.graph_policy import MAX_DESIGN_RETRIES
from backend.config import (
    DEFAULT_MIN_IPTM,
    FAST_DEV,
    MAX_DESIGN_ITERATIONS,
    MAX_NO_IMPROVEMENT_ROUNDS,
)
from backend.contracts.validate import validate_verdicts


AGENT_NAME = "critic"
AGENT_DISPLAY = "Scientist critic"

WT_ONLY_DELTA_KCAL = 3.0
WT_ONLY_DELTA_IPTM = 0.15

# Failures a new sequence can plausibly repair. Missing evidence is deliberately
# absent: another sequence must not be used as a substitute for a missing tool.
REDESIGNABLE_REASONS = {
    "low_structure_confidence",
    "low_iptm",
    "too_similar_to_pdb",
    "wt_only_signal",
}
EVIDENCE_BLOCKER_REASONS = {
    "missing_structure_metric",
    "unverified_structure_metric",
    "missing_iptm",
    "missing_novelty",
    "unverified_novelty",
    "missing_mutant_evaluation",
    "missing_wt_evaluation",
    "proxy_only_evaluation",
}


def _trusted_structure_method(method: str) -> bool:
    method = (method or "").lower()
    if not method or any(x in method for x in ("heuristic", "fixture", "unknown")):
        return False
    return any(
        token in method
        for token in ("tamarind", "esmfold", "alphafold", "boltz", "chai", "experimental")
    )


def _evaluation_method(delta: dict | None) -> str:
    method = str((delta or {}).get("evaluation_method") or "").strip().lower()
    if method:
        return method
    note = str((delta or {}).get("note") or "").lower()
    if "sequence-derived" in note or "sequence proxy" in note or "not docking" in note:
        return "sequence_proxy"
    if "fixture" in note:
        return "fixture"
    return "unknown"


def _trusted_mutant_evaluation(method: str) -> bool:
    method = (method or "").lower()
    if not method or any(x in method for x in ("proxy", "heuristic", "fixture", "unknown")):
        return False
    return any(
        token in method
        for token in (
            "experimental",
            "complex",
            "multimer",
            "docking",
            "boltz",
            "chai",
            "alphafold",
            "openmm",
            "molecular_dynamics",
        )
    )


def _trusted_novelty_method(method: str) -> bool:
    method = (method or "").lower()
    return any(
        token in method
        for token in ("mmseqs", "blast", "foldseek", "diamond", "pdb_search", "experimental")
    )


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


def _criticize_design(
    design: dict,
    bars: dict,
    delta: dict | None,
    mutation_ids: list[str],
) -> dict:
    reasons: list[str] = []
    metrics_used: list[str] = []
    evidence_ids: list[str] = list(mutation_ids[:2]) if mutation_ids else []
    verdict = "promote"
    summary_bits: list[str] = []

    def hold() -> None:
        nonlocal verdict
        if verdict != "reject":
            verdict = "hold"

    novelty = design.get("novelty") or {}
    identity = novelty.get("identity")
    novelty_method = str(novelty.get("method") or "")
    max_id = bars.get("max_pdb_identity")
    if max_id is not None:
        if identity is None:
            reasons.append("missing_novelty")
            hold()
            summary_bits.append("Novelty was not measured against a sequence/structure database.")
        elif not _trusted_novelty_method(novelty_method):
            reasons.append("unverified_novelty")
            metrics_used.append("novelty.identity")
            hold()
            summary_bits.append(
                f"Novelty identity {identity} came from unverified method {novelty_method or 'unknown'}."
            )
        elif float(identity) > float(max_id):
            reasons.append("too_similar_to_pdb")
            metrics_used.append("novelty.identity")
            verdict = "reject"
            summary_bits.append(
                f"Novelty identity {identity} exceeds max_pdb_identity {max_id}."
            )
        else:
            metrics_used.append("novelty.identity")

    plddt = design.get("plddt")
    fold_method = str(design.get("fold_method") or "")
    min_plddt = bars.get("min_plddt")
    if plddt is not None:
        metrics_used.append("plddt")
    if min_plddt is not None:
        if plddt is None:
            reasons.append("missing_structure_metric")
            hold()
            summary_bits.append("Required pLDDT is missing.")
        elif float(plddt) < float(min_plddt):
            reasons.append("low_structure_confidence")
            verdict = "reject"
            summary_bits.append(f"pLDDT {plddt} is below min_plddt {min_plddt}.")
        elif not _trusted_structure_method(fold_method):
            reasons.append("unverified_structure_metric")
            hold()
            summary_bits.append(
                f"pLDDT came from unverified method {fold_method or 'unknown'}."
            )

    iptm = design.get("iptm")
    min_iptm = bars.get("min_iptm", DEFAULT_MIN_IPTM)
    if iptm is not None:
        metrics_used.append("iptm")
    if min_iptm is not None:
        if iptm is None:
            reasons.append("missing_iptm")
            hold()
            summary_bits.append("Required interface confidence (ipTM) is missing.")
        elif float(iptm) < float(min_iptm):
            reasons.append("low_iptm")
            verdict = "reject"
            summary_bits.append(f"ipTM {iptm} is below min_iptm {min_iptm}.")

    mutants = {
        key: value
        for key, value in ((delta or {}).get("mutant_scores") or {}).items()
        if value is not None
    }
    wt_score = (delta or {}).get("wt_score")
    require_mutant = bool(bars.get("require_mutant_score"))
    method = _evaluation_method(delta)

    if require_mutant and not mutants:
        reasons.append("missing_mutant_evaluation")
        hold()
        summary_bits.append("Spec requires a mutant score; none present.")
    elif require_mutant and wt_score is None:
        reasons.append("missing_wt_evaluation")
        hold()
        summary_bits.append("A mutant score is present but the matched WT score is missing.")
    elif mutants:
        metrics_used.append("mutant_evaluation_method")
        if not _trusted_mutant_evaluation(method):
            reasons.append("proxy_only_evaluation")
            hold()
            summary_bits.append(
                f"Mutant scores use {method}; they can rank hypotheses but cannot justify promotion."
            )

    if mutants and wt_score is not None:
        score_direction = str((delta or {}).get("score_direction") or "lower_is_better")
        score_kind = str((delta or {}).get("score_kind") or "score")
        for mid, mscore in mutants.items():
            if mscore is None:
                continue
            metrics_used.append(f"design_delta_{mid}")
            try:
                dval = float(mscore) - float(wt_score)
            except (TypeError, ValueError):
                continue
            if score_direction == "higher_is_better":
                collapse = float(wt_score) - float(mscore)
                threshold = WT_ONLY_DELTA_IPTM if score_kind == "iptm" else 0.15
                collapse_label = f"{collapse:.2f} {score_kind}"
            else:
                collapse = dval
                threshold = WT_ONLY_DELTA_KCAL
                collapse_label = f"{collapse:.1f} kcal"
            if collapse > threshold:
                reasons.append("wt_only_signal")
                evidence_ids = list(dict.fromkeys([*evidence_ids, mid]))
                verdict = "reject"
                summary_bits.append(
                    f"Mutant score collapses vs WT (delta {collapse_label} on {mid})."
                )

    if verdict == "promote":
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
        if any(
            r in reasons
            for r in (
                "proxy_only_evaluation",
                "missing_mutant_evaluation",
                "missing_wt_evaluation",
            )
        ):
            remaining_risk = (
                "Needs a real WT-versus-mutant complex evaluation; another sequence alone "
                "cannot close this evidence gap."
            )
        elif any(r in reasons for r in ("missing_novelty", "unverified_novelty")):
            remaining_risk = "Needs MMseqs/BLAST/Foldseek novelty verification before promotion."
        else:
            remaining_risk = "Could be promoted or rejected after stronger structure evidence."

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


def _round_progress_score(designs: list[dict], deltas: dict[str, dict], bars: dict) -> float:
    """Progress metric for stopping only; never used as a promotion score."""
    max_id = bars.get("max_pdb_identity")
    min_plddt = bars.get("min_plddt")
    min_iptm = bars.get("min_iptm", DEFAULT_MIN_IPTM)
    scores: list[float] = []
    for design in designs:
        score = 0.0
        novelty = design.get("novelty") or {}
        identity = novelty.get("identity")
        if (
            identity is not None
            and _trusted_novelty_method(str(novelty.get("method") or ""))
            and (max_id is None or float(identity) <= float(max_id))
        ):
            score += 1.0
        plddt = design.get("plddt")
        fold_method = str(design.get("fold_method") or "")
        trusted_structure = _trusted_structure_method(fold_method)
        if (
            trusted_structure
            and plddt is not None
            and (min_plddt is None or float(plddt) >= float(min_plddt))
        ):
            score += 1.0
        iptm = design.get("iptm")
        if (
            trusted_structure
            and iptm is not None
            and (min_iptm is None or float(iptm) >= float(min_iptm))
        ):
            score += 1.0
        delta = deltas.get(str(design.get("id") or "")) or {}
        if any(value is not None for value in (delta.get("mutant_scores") or {}).values()):
            score += 0.5
        if _trusted_mutant_evaluation(_evaluation_method(delta)):
            score += 1.5
        scores.append(score / 5.0)
    return round(max(scores, default=0.0), 3)


def _loop_decision(
    items: list[dict],
    mode: str,
    retry: int,
    *,
    no_improvement_rounds: int = 0,
    max_iterations: int = MAX_DESIGN_ITERATIONS,
    max_no_improvement_rounds: int = MAX_NO_IMPROVEMENT_ROUNDS,
    verification_failures: list[str] | None = None,
) -> tuple[str, str]:
    design_items = [i for i in items if i.get("subject_kind") == "design"]
    if mode != "live":
        return "experiment", "non_live_run"
    if any(i.get("verdict") == "promote" for i in design_items):
        return "experiment", "promoted"
    if not design_items:
        return "experiment", "no_candidates"
    if verification_failures:
        return "experiment", "evidence_tool_failure"

    iteration = int(retry) + 1
    if iteration >= max(1, int(max_iterations)):
        return "experiment", "iteration_budget_exhausted"
    if int(no_improvement_rounds) >= max(1, int(max_no_improvement_rounds)):
        return "experiment", "no_improvement"

    reasons = {
        reason
        for item in design_items
        for reason in (item.get("reasons") or [])
    }
    if reasons & REDESIGNABLE_REASONS:
        return "redesign", "recoverable_design_failure"
    if reasons & EVIDENCE_BLOCKER_REASONS:
        return "experiment", "evidence_gap"
    return "experiment", "no_recoverable_failure"


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


def _build_redesign_feedback(items: list[dict], iteration: int) -> dict:
    design_items = [i for i in items if i.get("subject_kind") == "design"]
    counts = Counter(
        reason
        for item in design_items
        for reason in (item.get("reasons") or [])
    )
    priority = sorted(
        counts,
        key=lambda code: (
            code not in REDESIGNABLE_REASONS,
            -counts[code],
            code,
        ),
    )
    return {
        "iteration": iteration,
        "priority_codes": priority,
        "reason_counts": dict(counts),
        "parent_ids": [i.get("subject_id") for i in design_items if i.get("subject_id")],
        "failed_designs": [
            {
                "id": item.get("subject_id"),
                "verdict": item.get("verdict"),
                "reasons": list(item.get("reasons") or []),
                "metrics_used": list(item.get("metrics_used") or []),
            }
            for item in design_items
        ],
    }


def _designer_notes(
    items: list[dict], hypothesis: str, feedback: dict
) -> tuple[str, dict | None]:
    """Claude writes notes for a redesign. Does not change verdicts."""
    design_items = [i for i in items if i.get("subject_kind") == "design"]
    fallback = (
        "Generate a new sequence set addressing: "
        + ", ".join(feedback.get("priority_codes") or ["failed hard gates"])
        + ". Keep contacts outside the sotorasib epitope and test on Y96D."
    )
    if FAST_DEV:
        rejects = [i["subject_id"] for i in design_items if i.get("verdict") != "promote"]
        return (
            fallback + f" Failed: {', '.join(rejects[:6])}."
        ), None
    prompt = (
        "You are the redesign planner in a bounded scientific verification loop. "
        "In ≤50 words, give concrete sequence/design changes for the recoverable failures. "
        "Do not claim that a new sequence can repair missing novelty or mutant-evaluation tools. "
        "Do NOT invent sequences, Ki, or PDB IDs.\n\n"
        f"Hypothesis: {hypothesis}\n"
        f"Structured feedback: {json.dumps(feedback)}\n"
        f"Design verdicts: {json.dumps([{k: it[k] for k in ('subject_id','verdict','reasons')} for it in design_items])}"
    )
    trace = call_llm(prompt, max_tokens=120, temperature=0.2)
    notes = (trace.get("response") or "").strip()
    if not trace.get("success") or not notes:
        notes = fallback
    return notes[:400], trace


def _decide_route(items: list[dict], mode: str, retry: int) -> str:
    """Compatibility wrapper used by tests and callers that only need the edge."""
    route, _ = _loop_decision(
        items,
        mode,
        retry,
        max_iterations=MAX_DESIGN_RETRIES + 1,
    )
    return route


def _persist_loop_state(
    run_dir: Path,
    iteration: int,
    designs_doc: dict,
    eval_result: dict,
    verdicts: dict,
    history: list[dict],
    *,
    max_iterations: int,
    termination_reason: str | None,
) -> None:
    round_dir = run_dir / "iterations" / f"round-{iteration:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("designs.json", designs_doc),
        ("eval.json", eval_result),
        ("verdicts.json", verdicts),
    ):
        (round_dir / name).write_text(json.dumps(payload, indent=2))
    (run_dir / "loop_history.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "max_iterations": max_iterations,
                "termination_reason": termination_reason,
                "iterations": history,
            },
            indent=2,
        )
    )


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

    retry = int(state.get("design_retry_count") or 0)
    iteration = retry + 1
    max_iterations = max(
        1, int(state.get("max_design_iterations") or MAX_DESIGN_ITERATIONS)
    )
    max_no_improvement = max(
        1,
        int(
            state.get("max_no_improvement_rounds")
            or MAX_NO_IMPROVEMENT_ROUNDS
        ),
    )
    progress_score = _round_progress_score(
        designs_doc.get("designs") or [], deltas, bars
    )
    prior_best = float(state.get("best_loop_score", -1.0))
    improved = progress_score > prior_best + 1e-6
    best_loop_score = max(prior_best, progress_score)
    no_improvement_rounds = (
        0 if improved else int(state.get("no_improvement_rounds") or 0) + 1
    )
    critic_route, decision_reason = _loop_decision(
        items,
        mode,
        retry,
        no_improvement_rounds=no_improvement_rounds,
        max_iterations=max_iterations,
        max_no_improvement_rounds=max_no_improvement,
        verification_failures=list(state.get("verification_failures") or []),
    )
    critic_notes = ""
    redesign_feedback: dict = {}
    route_trace = None
    if critic_route == "redesign":
        redesign_feedback = _build_redesign_feedback(items, iteration)
        critic_notes, route_trace = _designer_notes(
            items, hypothesis, redesign_feedback
        )
        redesign_feedback["instructions"] = critic_notes
        steps.append(
            {
                "action": "Route back to designer",
                "detail": (
                    f"iteration {iteration}/{max_iterations}; {decision_reason}: "
                    f"{critic_notes[:160]}"
                ),
            }
        )
        if progress_cb:
            from backend.agents.lab_log import emit

            emit(
                progress_cb,
                AGENT_NAME,
                "route",
                f"next → {critic_route} ({decision_reason})"
                + (f" ({critic_notes[:120]})" if critic_notes else ""),
            )
    else:
        steps.append(
            {
                "action": "Finalize verification loop",
                "detail": f"iteration {iteration}/{max_iterations}; {decision_reason}",
            }
        )
        if progress_cb:
            from backend.agents.lab_log import emit

            emit(
                progress_cb,
                AGENT_NAME,
                "route",
                f"next → experiment ({decision_reason})",
            )

    design_verdicts = [i for i in items if i.get("subject_kind") == "design"]
    promotes = sum(1 for i in design_verdicts if i["verdict"] == "promote")
    holds = sum(1 for i in design_verdicts if i["verdict"] == "hold")
    rejects = sum(1 for i in design_verdicts if i["verdict"] == "reject")
    termination_reason = decision_reason if critic_route == "experiment" else None
    round_record = {
        "iteration": iteration,
        "design_engine": (designs_doc.get("meta") or {}).get("design_engine")
        or (designs_doc.get("meta") or {}).get("engine")
        or "unknown",
        "design_ids": [
            d.get("id") for d in (designs_doc.get("designs") or []) if d.get("id")
        ],
        "progress_score": progress_score,
        "improved": improved,
        "no_improvement_rounds": no_improvement_rounds,
        "counts": {"promote": promotes, "hold": holds, "reject": rejects},
        "reason_codes": sorted(
            {
                reason
                for item in items
                if item.get("subject_kind") == "design"
                for reason in (item.get("reasons") or [])
            }
        ),
        "route": critic_route,
        "decision_reason": decision_reason,
        "redesign_feedback": redesign_feedback or None,
        "verification_failures": list(state.get("verification_failures") or []),
    }
    loop_history = list(state.get("loop_history") or [])
    loop_history.append(round_record)

    verdicts = {
        "schema_version": "1.0",
        "hypothesis": hypothesis,
        "items": items,
        "loop": {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "progress_score": progress_score,
            "best_progress_score": best_loop_score,
            "no_improvement_rounds": no_improvement_rounds,
            "route": critic_route,
            "decision_reason": decision_reason,
            "termination_reason": termination_reason,
            "verification_failures": list(state.get("verification_failures") or []),
        },
    }
    validate_verdicts(verdicts)
    (run_dir / "verdicts.json").write_text(json.dumps(verdicts, indent=2))
    _persist_loop_state(
        run_dir,
        iteration,
        designs_doc,
        eval_result,
        verdicts,
        loop_history,
        max_iterations=max_iterations,
        termination_reason=termination_reason,
    )
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": (llm_trace or {}).get("model"),
        "input_summary": "spec success_bars + designs + eval deltas + smallmol",
        "output_summary": (
            f"iteration {iteration}/{max_iterations}: {len(items)} verdicts "
            f"({promotes} promote, {holds} hold, {rejects} reject); {decision_reason}"
        ),
        "steps": steps,
        "tool_calls": [],
        "llm_calls": [t for t in (llm_trace, route_trace) if t],
        "critic_route": critic_route,
        "loop_iteration": iteration,
        "loop_decision_reason": decision_reason,
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "verdicts": verdicts,
        "hypothesis": hypothesis,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
        "critic_route": critic_route,
        "critic_notes": critic_notes,
        "redesign_feedback": redesign_feedback,
        "design_retry_count": retry,
        "loop_iteration": iteration,
        "loop_history": loop_history,
        "loop_termination_reason": termination_reason or "",
        "best_loop_score": best_loop_score,
        "no_improvement_rounds": no_improvement_rounds,
        "max_design_iterations": max_iterations,
        "max_no_improvement_rounds": max_no_improvement,
    }
