"""iDoctor Design LangGraph pipeline."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.critic import run_critic
from backend.agents.designer import run_designer
from backend.agents.evaluator import run_evaluator
from backend.agents.evidence import run_evidence
from backend.agents.experiment import run_experiment
from backend.agents.physics_control import run_physics
from backend.agents.structure import run_structure
from backend.config import IDOCTOR_DESIGN_DEFAULT_MODE, RUNS_DIR
from backend.contracts.novel_designs import export_from_run
from backend.contracts.validate import validate_provenance

AGENT_DISPLAY = {
    "evidence": "Literature & databases (Paperclip)",
    "designer": "Sequence design (BindCraft)",
    "structure": "Fold & complex (Tamarind)",
    "physics": "Docking control (AutoDock Vina)",
    "evaluate": "Score vs experiment",
    "critic": "Scientist critic (Claude)",
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
    graph.add_node("physics", _wrap_node(run_physics, "physics", progress_callback))
    graph.add_node("evaluate", _wrap_node(run_evaluator, "evaluate", progress_callback))
    graph.add_node("critic", _wrap_node(run_critic, "critic", progress_callback))
    graph.add_node("experiment", _wrap_node(run_experiment, "experiment", progress_callback))

    graph.add_edge(START, "evidence")
    graph.add_edge("evidence", "designer")
    graph.add_edge("designer", "structure")
    graph.add_edge("structure", "physics")
    graph.add_edge("physics", "evaluate")
    graph.add_edge("evaluate", "critic")
    graph.add_edge("critic", "experiment")
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
        "verdicts": _json("verdicts.json"),
        "experiment_md": experiment_md,
        "novel_designs": _json("novel_designs.json"),
        "provenance": _json("provenance.json"),
        "agent_traces": _json("traces.json") or [],
        "hypothesis": (_json("spec.json") or {}).get("hypothesis", ""),
    }


def run_idoctor_design(
    mode: str = "fixture",
    run_id: str | None = None,
    progress_callback: Callable | None = None,
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

    graph = build_idoctor_design_graph(progress_callback)
    app = graph.compile()

    initial: IDoctorDesignState = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "mode": mode,
        "agent_traces": [],
        "provenance_nodes": {},
    }

    result = app.invoke(initial)

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
        "verdicts": payload.get("verdicts") or result.get("verdicts"),
        "experiment_md": payload.get("experiment_md") or result.get("experiment_md", ""),
        "novel_designs": payload.get("novel_designs"),
        "provenance": payload.get("provenance") or provenance,
        "agent_traces": payload.get("agent_traces") or traces,
    }


async def run_idoctor_design_async(
    mode: str = "fixture",
    run_id: str | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    return await asyncio.to_thread(run_idoctor_design, mode, run_id, progress_callback)
