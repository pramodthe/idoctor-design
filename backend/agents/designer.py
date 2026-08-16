"""Designer agent — Tamarind BindCraft first, then sequence_design, then fixtures.

Proto/Modal is deliberately not used: Tamarind hosts the same models (RFdiffusion3,
ProteinMPNN) plus BindCraft, against an API key that already works, so there is no
second GPU stack to keep deployed.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from backend.config import DATA_DIR, FAST_DEV, FIXTURES_DIR
from backend.contracts.validate import validate_designs
from backend.tools.sequence_design import designs_to_fasta


AGENT_NAME = "designer"
AGENT_DISPLAY = "Binder design"

BINDCRAFT_DIR = DATA_DIR / "bindcraft_designs"


def _engine_from_doc(doc: dict | None, default: str = "unknown") -> str:
    meta = (doc or {}).get("meta") or {}
    return str(meta.get("design_engine") or meta.get("engine") or default)


def _honest_bindcraft_flags(designs_doc: dict, engine: str) -> dict:
    """Do not claim BindCraft filters unless the engine is actually bindcraft."""
    if engine == "bindcraft":
        return designs_doc
    for d in designs_doc.get("designs") or []:
        scores = d.get("constraint_scores")
        if isinstance(scores, dict) and scores.get("passed_bindcraft_filters"):
            scores["passed_bindcraft_filters"] = False
    return designs_doc


def _load_bindcraft_designs() -> dict | None:
    """Load a completed BindCraft campaign from disk, if one exists."""
    path = BINDCRAFT_DIR / "designs.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return doc if doc.get("designs") else None


def run_designer(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    tool_calls: list[dict] = []
    steps: list[dict] = []
    designs_doc: dict | None = None
    node_source = "fixture"
    engine = "none"

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Designing binder sequences...")

    retry_count = int(state.get("design_retry_count") or 0)
    is_retry = state.get("critic_route") == "redesign"
    redesign_feedback = dict(state.get("redesign_feedback") or {})
    if is_retry:
        retry_count += 1
        if progress_cb:
            progress_cb(
                AGENT_NAME,
                "running",
                step=f"Redesign {retry_count} after critic: {(state.get('critic_notes') or '')[:80]}",
            )

    if mode == "replay":
        path = run_dir / "designs.json"
        designs_doc = json.loads(path.read_text())
        node_source = "cached"
        engine = _engine_from_doc(designs_doc, "cached")
        steps.append({"action": "Load cached designs", "detail": str(path)})
        fasta_path = run_dir / "designs.fasta"
        if not fasta_path.exists():
            fasta_path.write_text(
                designs_to_fasta(designs_doc.get("designs") or [])
            )
    else:
        # Critic retry: do not reload the same Tamarind campaign the critic already saw.
        if is_retry and mode == "live":
            try:
                from backend.tools.sequence_design import generate_designs

                notes = str(state.get("critic_notes") or "")
                tool_calls.append(
                    {
                        "tool": "sequence_design.local",
                        "detail": f"Critic redesign extra_seed={retry_count}; {notes[:120]}",
                    }
                )
                result = generate_designs(
                    state.get("scientific_spec") or {},
                    extra_seed=retry_count,
                    feedback=redesign_feedback,
                )
                if result and result.get("designs"):
                    designs_doc = result
                    engine = "sequence_design"
                    node_source = "live"
                    steps.append(
                        {
                            "action": "Critic-requested redesign",
                            "detail": (
                                f"{len(result['designs'])} new heuristic sequences "
                                f"(not BindCraft; extra_seed={retry_count})"
                            ),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                steps.append({"action": "Redesign unavailable", "detail": str(e)})

        if designs_doc is None and mode == "live":
            # BindCraft runs for hours on Tamarind's GPUs, so it cannot be called
            # inline per run. A completed campaign is picked up from disk here.
            bindcraft_doc = _load_bindcraft_designs()
            if bindcraft_doc:
                designs_doc = bindcraft_doc
                # Read the engine off the campaign rather than assuming BindCraft:
                # the same drop path is used by esmfold2-binder-design, whose output
                # has NOT passed BindCraft's acceptance filters. Claiming otherwise
                # would be the exact mislabelling the provenance banner exists to stop.
                engine = _engine_from_doc(bindcraft_doc, "unknown")
                if engine == "bindcraft" and (
                    (bindcraft_doc.get("meta") or {}).get("engine")
                    not in {None, "", "bindcraft"}
                ):
                    engine = str((bindcraft_doc.get("meta") or {}).get("engine"))
                node_source = "live"
                filtered = engine == "bindcraft"
                tool_calls.append(
                    {
                        "tool": f"tamarind.{engine}",
                        "detail": (
                            "RFdiffusion + ProteinMPNN + AF2 with acceptance filters"
                            if filtered
                            else "single-shot generative binder design, no acceptance filters"
                        ),
                        "job_name": (bindcraft_doc.get("meta") or {}).get("job_name"),
                    }
                )
                steps.append(
                    {
                        "action": f"Structure-based designs ({engine})",
                        "detail": (
                            f"{len(bindcraft_doc['designs'])} designs that passed "
                            "BindCraft acceptance filters"
                            if filtered
                            else f"{len(bindcraft_doc['designs'])} designs — generated by "
                            f"{engine}, NOT filter-passed; judged only by our critic"
                        ),
                    }
                )

        if designs_doc is None and mode == "live":
            try:
                from backend.tools.sequence_design import generate_designs

                tool_calls.append(
                    {
                        "tool": "sequence_design.local",
                        "detail": "Local interim generator — used only until a BindCraft campaign lands",
                    }
                )
                result = generate_designs(state.get("scientific_spec") or {})
                if result and result.get("designs"):
                    designs_doc = result
                    engine = "sequence_design"
                    node_source = "live"
                    steps.append(
                        {
                            "action": "Local sequence_design (no BindCraft campaign on disk)",
                            "detail": (
                                f"{len(result['designs'])} sequences; engine=sequence_design; "
                                "heuristic — not a structure-based design"
                            ),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                steps.append({"action": "Design unavailable", "detail": str(e)})
                engine = "unavailable"

        if designs_doc is None:
            src_json = FIXTURES_DIR / "designs.example.json"
            src_fa = FIXTURES_DIR / "designs.example.fasta"
            shutil.copy2(src_json, run_dir / "designs.json")
            if src_fa.is_file():
                shutil.copy2(src_fa, run_dir / "designs.fasta")
            designs_doc = json.loads((run_dir / "designs.json").read_text())
            for d in designs_doc.get("designs") or []:
                d["provenance"] = "fixture"
            designs_doc.setdefault("meta", {})["design_engine"] = "fixture"
            (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
            node_source = "fixture"
            engine = "fixture"
            steps.append({"action": "Load fixture designs", "detail": str(src_json)})

    validate_designs(designs_doc)
    designs_doc.setdefault("meta", {})["design_engine"] = engine
    designs_doc = _honest_bindcraft_flags(designs_doc, engine)
    iteration = retry_count + 1
    failure_codes = list(redesign_feedback.get("priority_codes") or [])
    parent_ids = list(redesign_feedback.get("parent_ids") or [])
    for design in designs_doc.get("designs") or []:
        design["iteration"] = iteration
        design["lineage"] = {
            "iteration": iteration,
            "parent_ids": parent_ids,
            "failure_codes": failure_codes,
        }
    designs_doc.setdefault("meta", {})["loop_iteration"] = iteration
    if is_retry:
        designs_doc.setdefault("meta", {})["critic_notes"] = state.get("critic_notes") or ""
        designs_doc.setdefault("meta", {})["design_retry"] = retry_count
        designs_doc.setdefault("meta", {})["redesign_feedback"] = redesign_feedback
    (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
    (run_dir / "designs.fasta").write_text(
        designs_to_fasta(designs_doc.get("designs") or [])
    )

    provenance_nodes[AGENT_NAME] = node_source
    elapsed = time.perf_counter() - start
    n = len(designs_doc.get("designs") or [])
    llm_trace = None
    if mode == "live" and not FAST_DEV:
        from backend.agents.lab_log import emit
        from backend.agents.llm import call_llm

        spec = state.get("scientific_spec") or {}
        emit(progress_cb, AGENT_NAME, "thought", "Claude: design plan (not generating sequences)")
        llm_trace = call_llm(
            "You are the iDoctor designer. In ≤50 words: state the engine already used "
            f"({engine}) and the Y96D constraint that matters. Do NOT invent sequences, "
            "Ki, or PDB ids. Do NOT say BindCraft unless the engine is exactly bindcraft.\n"
            f"Hypothesis: {spec.get('hypothesis') or ''}\n"
            f"Critic notes: {state.get('critic_notes') or 'none'}\n"
            f"Structured failure codes: {failure_codes or 'none'}\n"
            f"n_designs: {n}",
            max_tokens=120,
        )
        if llm_trace.get("success"):
            plan = (llm_trace.get("response") or "").strip()
            steps.append({"action": "Claude design plan", "detail": plan[:240]})
            emit(progress_cb, AGENT_NAME, "output", plan[:400])
        else:
            steps.append(
                {
                    "action": "Claude design plan skipped",
                    "detail": llm_trace.get("error") or llm_trace.get("anthropic_error") or "failed",
                }
            )

    if engine == "bindcraft":
        honest = f"engine={engine} (Tamarind BindCraft — structure-based, filter-passed)"
    elif engine in {"esmfold2-binder-design", "rfdiffusion3", "boltzdesign", "boltzgen"}:
        honest = f"engine={engine} (Tamarind — structure-based, NOT filter-passed)"
    else:
        honest = f"engine={engine} (heuristic — not a structure-based design)"
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": (llm_trace or {}).get("model") if (llm_trace or {}).get("success") else None,
        "input_summary": f"mode={mode}; design_engine={engine}",
        "output_summary": f"{n} designs; {honest}",
        "steps": steps,
        "tool_calls": tool_calls,
        "llm_calls": [llm_trace] if llm_trace else [],
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "designs": designs_doc,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
        "design_retry_count": retry_count,
    }
