"""iDoctor Design LangGraph pipeline.

Evidence agent uses Claude + Paperclip/Europe PMC tools in live mode.
The critic runs a bounded design -> verify -> critique loop in live mode.
Fixture and replay stay linear and deterministic.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from backend.agents.complex_evaluator import run_complex_evaluator
from backend.agents.critic import run_critic
from backend.agents.designer import run_designer
from backend.agents.evaluator import run_evaluator
from backend.agents.evidence import run_evidence
from backend.agents.experiment import run_experiment
from backend.agents.graph_policy import route_after_critic
from backend.agents.novelty import run_novelty
from backend.agents.physics_control import run_physics
from backend.agents.structure import run_structure
from backend.config import (
    IDOCTOR_DESIGN_DEFAULT_MODE,
    MAX_DESIGN_ITERATIONS,
    MAX_NO_IMPROVEMENT_ROUNDS,
    RUNS_DIR,
)
from backend.contracts.novel_designs import export_from_run
from backend.contracts.validate import validate_provenance

AGENT_DISPLAY = {
    "evidence": "Literature (Paperclip MCP)",
    "designer": "Binder design",
    "structure": "Fold metrics",
    "novelty": "PDB novelty check",
    "complex": "WT/mutant complexes",
    "physics": "Docking control",
    "evaluate": "Score vs Ki",
    "critic": "Scientist critic",
    "experiment": "Monday lab card",
}


class IDoctorDesignState(TypedDict, total=False):
    run_id: str
    run_dir: str
    mode: str
    scientific_spec: dict
    designs: dict
    smallmol: dict
    eval_result: dict
    verdicts: dict
    experiment_md: str
    hypothesis: str
    provenance: dict
    provenance_nodes: dict
    agent_traces: list
    design_scores: dict
    skip_reeval: bool
    design_retry_count: int
    critic_route: str
    critic_notes: str
    redesign_feedback: dict
    loop_iteration: int
    loop_history: list[dict]
    loop_termination_reason: str
    best_loop_score: float
    no_improvement_rounds: int
    max_design_iterations: int
    max_no_improvement_rounds: int
    verification_failures: list[str]


def _wrap_node(fn: Callable, name: str, callback: Callable | None = None):
    def wrapper(state: dict) -> dict:
        if callback:
            callback(name, "running")
        if callback:
            result = fn(state, progress_cb=callback)
        else:
            result = fn(state)
        if callback:
            callback(name, "completed")
        return result

    return wrapper


def build_idoctor_design_graph(progress_callback: Callable | None = None) -> StateGraph:
    graph = StateGraph(IDoctorDesignState)
    graph.add_node("evidence", _wrap_node(run_evidence, "evidence", progress_callback))
    graph.add_node("designer", _wrap_node(run_designer, "designer", progress_callback))
    graph.add_node("structure", _wrap_node(run_structure, "structure", progress_callback))
    graph.add_node("novelty", _wrap_node(run_novelty, "novelty", progress_callback))
    graph.add_node(
        "complex", _wrap_node(run_complex_evaluator, "complex", progress_callback)
    )
    graph.add_node("physics", _wrap_node(run_physics, "physics", progress_callback))
    graph.add_node("evaluate", _wrap_node(run_evaluator, "evaluate", progress_callback))
    graph.add_node("critic", _wrap_node(run_critic, "critic", progress_callback))
    graph.add_node("experiment", _wrap_node(run_experiment, "experiment", progress_callback))

    graph.add_edge(START, "evidence")
    graph.add_edge("evidence", "designer")
    graph.add_edge("designer", "structure")
    graph.add_edge("structure", "novelty")
    graph.add_edge("novelty", "complex")
    graph.add_edge("complex", "physics")
    graph.add_edge("physics", "evaluate")
    graph.add_edge("evaluate", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"designer": "designer", "experiment": "experiment"},
    )
    graph.add_edge("experiment", END)
    return graph


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def _write_run_meta(run_dir: Path, run_id: str, mode: str, nodes: dict, traces: list) -> dict:
    provenance = {
        "run_id": run_id,
        "mode": mode,
        "nodes": nodes,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    validate_provenance(provenance)
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    (run_dir / "traces.json").write_text(json.dumps(traces, indent=2))
    return provenance


def _load_run_payload(run_dir: Path) -> dict[str, Any]:
    def _json(name: str):
        path = run_dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text())

    experiment_md = ""
    exp_path = run_dir / "experiment.md"
    if exp_path.exists():
        experiment_md = exp_path.read_text()

    return {
        "scientific_spec": _json("spec.json"),
        "designs": _json("designs.json"),
        "smallmol": _json("smallmol.json"),
        "eval_result": _json("eval.json"),
        "complex_scores": _json("complex_scores.json"),
        "verdicts": _json("verdicts.json"),
        "experiment_md": experiment_md,
        "novel_designs": _json("novel_designs.json"),
        "provenance": _json("provenance.json"),
        "agent_traces": _json("traces.json") or [],
        "loop_history": _json("loop_history.json"),
        "hypothesis": (_json("spec.json") or {}).get("hypothesis", ""),
    }


def run_idoctor_design(
    mode: str = "fixture",
    run_id: str | None = None,
    progress_callback: Callable | None = None,
    resume: bool = False,
) -> dict:
    """Run the iDoctor Design graph. Modes: fixture | replay | live."""
    mode = (mode or IDOCTOR_DESIGN_DEFAULT_MODE or "fixture").lower()
    if mode not in {"fixture", "replay", "live"}:
        raise ValueError(f"Invalid mode: {mode}")

    if mode == "replay":
        if run_id:
            run_dir = RUNS_DIR / run_id
        else:
            runs = [p for p in RUNS_DIR.iterdir() if p.is_dir()] if RUNS_DIR.exists() else []
            if not runs:
                raise FileNotFoundError("No runs available to replay")
            run_dir = max(runs, key=lambda p: p.stat().st_mtime)
            run_id = run_dir.name
        if not run_dir.exists():
            raise FileNotFoundError(f"Run folder not found: {run_dir}")
    else:
        run_id = run_id or _new_run_id()
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = run_dir / "langgraph.sqlite"
    if resume and mode == "replay":
        raise ValueError("Replay mode cannot resume a live checkpoint")
    if resume and not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found for run {run_id}")
    if not resume and checkpoint_path.is_file() and mode != "replay":
        raise FileExistsError(
            f"Run {run_id} already has a checkpoint; pass resume=true to continue it"
        )

    graph = build_idoctor_design_graph(progress_callback)

    initial: IDoctorDesignState = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "mode": mode,
        "agent_traces": [],
        "provenance_nodes": {},
        "design_retry_count": 0,
        "critic_route": "",
        "critic_notes": "",
        "redesign_feedback": {},
        "loop_iteration": 0,
        "loop_history": [],
        "loop_termination_reason": "",
        "best_loop_score": -1.0,
        "no_improvement_rounds": 0,
        "max_design_iterations": MAX_DESIGN_ITERATIONS,
        "max_no_improvement_rounds": MAX_NO_IMPROVEMENT_ROUNDS,
        "verification_failures": [],
    }

    invoke_config = {
        "recursion_limit": 60,
        "configurable": {"thread_id": str(run_id)},
    }
    if mode == "replay":
        app = graph.compile()
        result = app.invoke(initial, invoke_config)
    else:
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            app = graph.compile(checkpointer=checkpointer)
            if resume:
                snapshot = app.get_state(invoke_config)
                if not snapshot.values:
                    raise RuntimeError(f"Checkpoint for {run_id} contains no graph state")
                if not snapshot.next:
                    raise RuntimeError(f"Run {run_id} is already complete")
                result = app.invoke(None, invoke_config)
            else:
                result = app.invoke(initial, invoke_config)

    nodes = result.get("provenance_nodes") or {}
    for name in AGENT_DISPLAY:
        nodes.setdefault(name, "skipped")
    traces = result.get("agent_traces") or []
    provenance = _write_run_meta(run_dir, run_id, mode, nodes, traces)

    try:
        export_from_run(run_dir)
    except Exception as exc:  # noqa: BLE001
        (run_dir / "novel_designs.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source": "idoctor-design",
                    "refused": [],
                    "novel_designs": [],
                    "error": str(exc),
                },
                indent=2,
            )
            + "\n"
        )

    payload = _load_run_payload(run_dir)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "mode": mode,
        "status": "completed",
        "hypothesis": payload.get("hypothesis") or result.get("hypothesis", ""),
        "scientific_spec": payload.get("scientific_spec") or result.get("scientific_spec"),
        "designs": payload.get("designs") or result.get("designs"),
        "smallmol": payload.get("smallmol") or result.get("smallmol"),
        "eval": payload.get("eval_result") or result.get("eval_result"),
        "eval_result": payload.get("eval_result") or result.get("eval_result"),
        "complex_scores": payload.get("complex_scores") or result.get("design_scores"),
        "verdicts": payload.get("verdicts") or result.get("verdicts"),
        "experiment_md": payload.get("experiment_md") or result.get("experiment_md", ""),
        "novel_designs": payload.get("novel_designs"),
        "provenance": payload.get("provenance") or provenance,
        "agent_traces": payload.get("agent_traces") or traces,
        "loop_history": payload.get("loop_history")
        or {
            "schema_version": "1.0",
            "max_iterations": result.get("max_design_iterations", MAX_DESIGN_ITERATIONS),
            "termination_reason": result.get("loop_termination_reason") or None,
            "iterations": result.get("loop_history") or [],
        },
        "loop_termination_reason": result.get("loop_termination_reason")
        or ((payload.get("loop_history") or {}).get("termination_reason")),
        "checkpointed": mode != "replay",
    }


async def run_idoctor_design_async(
    mode: str = "fixture",
    run_id: str | None = None,
    progress_callback: Callable | None = None,
    resume: bool = False,
) -> dict:
    return await asyncio.to_thread(
        run_idoctor_design, mode, run_id, progress_callback, resume
    )
