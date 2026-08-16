"""WT-versus-mutant target:binder complex evaluation using Tamarind multimer."""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

import requests

from backend.config import (
    COMPLEX_EVALUATION_TIMEOUT,
    FAST_DEV,
    MAX_COMPLEX_DESIGNS,
    MAX_COMPLEX_MUTANTS,
)
from backend.tools import tamarind


AGENT_NAME = "complex"
AGENT_DISPLAY = "WT/mutant complexes"


class TargetSequenceUnavailable(RuntimeError):
    pass


def _replace_failures(state: dict, prefix: str, current: list[str]) -> list[str]:
    prior = [
        str(item)
        for item in (state.get("verification_failures") or [])
        if not str(item).startswith(prefix)
    ]
    return [*prior, *current]


def _uniprot_sequence(uniprot_id: str, run_dir: Path) -> str:
    cache = run_dir / "target_sequence.fasta"
    if cache.is_file():
        text = cache.read_text()
    else:
        if not uniprot_id:
            raise TargetSequenceUnavailable("spec target.uniprot_id is missing")
        last_error = "unknown error"
        for attempt in range(3):
            try:
                response = requests.get(
                    f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta",
                    timeout=30,
                )
                response.raise_for_status()
                text = response.text
                cache.write_text(text)
                break
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt == 2:
                    raise TargetSequenceUnavailable(
                        f"UniProt {uniprot_id} unavailable: {last_error}"
                    ) from exc
                time.sleep(1.5 * (attempt + 1))
    sequence = "".join(line.strip() for line in text.splitlines() if not line.startswith(">"))
    if not sequence:
        raise TargetSequenceUnavailable(f"UniProt {uniprot_id} returned an empty sequence")
    return sequence


def _apply_mutation(sequence: str, mutation: str) -> str:
    match = re.fullmatch(r"([A-Z])(\d+)([A-Z])", mutation.upper())
    if not match:
        raise TargetSequenceUnavailable(f"Unsupported mutation code: {mutation}")
    expected, raw_position, replacement = match.groups()
    position = int(raw_position) - 1
    if position < 0 or position >= len(sequence):
        raise TargetSequenceUnavailable(f"Mutation {mutation} is outside the target sequence")
    observed = sequence[position]
    if observed not in {expected, replacement}:
        raise TargetSequenceUnavailable(
            f"Mutation {mutation} expected {expected} at {position + 1}, found {observed}"
        )
    return sequence[:position] + replacement + sequence[position + 1 :]


def _target_panel(spec: dict, run_dir: Path) -> tuple[str, dict[str, str]]:
    target = spec.get("target") or {}
    canonical = _uniprot_sequence(str(target.get("uniprot_id") or ""), run_dir)
    baseline_codes = re.findall(r"\b[A-Z]\d+[A-Z]\b", str(target.get("name") or "").upper())
    baseline = canonical
    for code in baseline_codes:
        baseline = _apply_mutation(baseline, code)
    baseline_label = "+".join(baseline_codes) or "WT"
    targets = {baseline_label: baseline}
    mutation_ids = [
        str(row.get("id"))
        for row in (spec.get("mutations") or [])
        if isinstance(row, dict) and row.get("id")
    ][:MAX_COMPLEX_MUTANTS]
    for mutation in mutation_ids:
        targets[mutation] = _apply_mutation(baseline, mutation)
    return baseline_label, targets


def _novel_enough(design: dict, max_identity: float | None) -> bool:
    novelty = design.get("novelty") or {}
    method = str(novelty.get("method") or "").lower()
    identity = novelty.get("identity")
    if identity is None or not any(x in method for x in ("rcsb", "mmseqs", "blast", "foldseek")):
        return False
    return max_identity is None or float(identity) <= float(max_identity)


def _candidate_rank(design: dict) -> tuple[float, float]:
    return (float(design.get("iptm") or 0.0), float(design.get("plddt") or 0.0))


def run_complex_evaluator(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    spec = state.get("scientific_spec") or {}
    designs_doc = copy.deepcopy(state.get("designs") or {})
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    traces = list(state.get("agent_traces") or [])
    failures: list[str] = []
    steps: list[dict] = []
    tool_calls: list[dict] = []
    design_scores: dict[str, dict] | None = None

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Testing top binders on G12C and resistance complexes...")

    if mode == "replay":
        node_source = "cached"
        design_scores = state.get("design_scores")
        steps.append({"action": "Reuse complex scores", "detail": "Replay mode"})
    elif mode == "fixture":
        node_source = "fixture"
        steps.append({"action": "Fixture complex scores", "detail": "Evaluator loads fixture deltas"})
    elif FAST_DEV:
        node_source = "skipped"
        design_scores = {}
        failures.append("complex:skipped_fast_mode")
        steps.append(
            {
                "action": "Tamarind complexes skipped",
                "detail": "IDOCTOR_FAST=1; proxy scoring cannot promote",
            }
        )
    else:
        bars = spec.get("success_bars") or {}
        max_identity = bars.get("max_pdb_identity")
        min_plddt = bars.get("min_plddt")
        candidates = [
            design
            for design in (designs_doc.get("designs") or [])
            if _novel_enough(design, max_identity)
            and (
                min_plddt is None
                or design.get("plddt") is None
                or float(design.get("plddt")) >= float(min_plddt)
            )
        ]
        candidates.sort(key=_candidate_rank, reverse=True)
        selected = candidates[:MAX_COMPLEX_DESIGNS]
        design_scores = {}
        if not selected:
            node_source = "skipped"
            steps.append(
                {
                    "action": "No complex submission",
                    "detail": "No candidate passed novelty/structure prerequisites",
                }
            )
        else:
            node_source = "live"
            try:
                baseline_label, target_panel = _target_panel(spec, run_dir)
            except TargetSequenceUnavailable as exc:
                failures.append(f"complex:target:{exc}")
                target_panel = {}
                baseline_label = "WT"
            by_id = {str(d.get("id")): d for d in designs_doc.get("designs") or []}
            for design in selected:
                did = str(design.get("id") or "design")
                if not target_panel:
                    break
                try:
                    panel = tamarind.submit_complex_panel(
                        did,
                        str(design.get("sequence") or ""),
                        target_panel,
                        structures_dir=str(run_dir / "structures" / "complexes"),
                        timeout=float(COMPLEX_EVALUATION_TIMEOUT),
                    )
                    metrics = panel["metrics"]
                    missing_variants = [
                        variant for variant in target_panel if variant not in metrics
                    ]
                    if missing_variants:
                        raise tamarind.TamarindUnavailable(
                            f"{did}: incomplete complex panel; missing "
                            + ", ".join(missing_variants)
                        )
                    baseline = metrics.get(baseline_label)
                    if not baseline:
                        raise tamarind.TamarindUnavailable(
                            f"{did}: baseline {baseline_label} result missing"
                        )
                    mutant_scores = {
                        variant: float(row["iptm"])
                        for variant, row in metrics.items()
                        if variant != baseline_label and row.get("iptm") is not None
                    }
                    design_scores[did] = {
                        "wt_score": float(baseline["iptm"]),
                        "mutant_scores": mutant_scores,
                        "method": "tamarind_alphafold_multimer_complex_iptm",
                        "confidence": "predicted_complex",
                        "score_kind": "iptm",
                        "score_direction": "higher_is_better",
                        "note": (
                            "Target:binder AlphaFold-Multimer comparison from Tamarind; "
                            "scores are complex ipTM, higher is better."
                        ),
                    }
                    current = by_id.get(did)
                    if current is not None:
                        current["iptm"] = float(baseline["iptm"])
                        if baseline.get("plddt") is not None:
                            current["plddt"] = float(baseline["plddt"])
                        if baseline.get("pdb_path"):
                            current["pdb_path"] = baseline["pdb_path"]
                        current["fold_method"] = "tamarind:alphafold2_multimer_complex"
                        current["complex_metrics"] = metrics
                    tool_calls.append(
                        {
                            "tool": "tamarind.alphafold_multimer",
                            "detail": (
                                f"{did}: {baseline_label} ipTM={float(baseline['iptm']):.3f}; "
                                f"mutants={len(mutant_scores)}"
                            ),
                        }
                    )
                except tamarind.TamarindUnavailable as exc:
                    failures.append(f"complex:{did}:{exc}")
            if failures:
                node_source = "skipped"
            detail = f"scored={len(design_scores)}; failures={len(failures)}"
            if failures:
                detail += " — " + "; ".join(str(f)[:200] for f in failures[:3])
            steps.append({"action": "Tamarind WT/mutant complexes", "detail": detail})

    (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
    if design_scores is not None:
        (run_dir / "complex_scores.json").write_text(json.dumps(design_scores, indent=2))
    provenance_nodes[AGENT_NAME] = node_source
    elapsed = time.perf_counter() - start
    traces.append(
        {
            "agent": AGENT_NAME,
            "agent_name": AGENT_DISPLAY,
            "duration_seconds": round(elapsed, 2),
            "model": None,
            "input_summary": f"mode={mode}; top={MAX_COMPLEX_DESIGNS}",
            "output_summary": (
                f"real complex scores={len(design_scores or {})}; failures={len(failures)}"
            ),
            "steps": steps,
            "tool_calls": tool_calls,
            "llm_calls": [],
        }
    )
    return {
        "designs": designs_doc,
        "design_scores": design_scores,
        "verification_failures": _replace_failures(state, "complex:", failures),
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
