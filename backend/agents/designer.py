"""Designer agent — Proto binder first, then sequence_design, then fixtures."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from backend.config import FIXTURES_DIR, USE_PROTO
from backend.contracts.validate import validate_designs
from backend.tools import proto_runner


AGENT_NAME = "designer"
AGENT_DISPLAY = "Sequence design (Proto)"


def _engine_from_doc(doc: dict | None, default: str) -> str:
    meta = (doc or {}).get("meta") or {}
    return str(meta.get("design_engine") or default)


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

    if mode == "replay":
        path = run_dir / "designs.json"
        designs_doc = json.loads(path.read_text())
        node_source = "cached"
        engine = _engine_from_doc(designs_doc, "cached")
        steps.append({"action": "Load cached designs", "detail": str(path)})
        fasta_path = run_dir / "designs.fasta"
        if not fasta_path.exists():
            fasta_path.write_text(
                proto_runner.designs_to_fasta(designs_doc.get("designs") or [])
            )
    else:
        if mode == "live":
            try:
                detail = (
                    "Proto binder (RFdiffusion3+MPNN+ipTM) if USE_PROTO/packages; "
                    "else local sequence_design interim"
                )
                tool_calls.append(
                    {
                        "tool": "proto.run",
                        "detail": detail,
                        "use_proto_env": USE_PROTO,
                        "modal_configured": proto_runner.is_configured(),
                    }
                )
                result = proto_runner.run_proto(
                    state.get("scientific_spec") or {},
                    out_dir=run_dir,
                    live=True,
                )
                if result and result.get("designs"):
                    designs_doc = result
                    engine = _engine_from_doc(result, "unknown")
                    any_live = any(d.get("provenance") == "live" for d in result["designs"])
                    node_source = "live" if any_live else "fixture"
                    if engine == "proto_language":
                        action = "Proto binder design"
                    elif engine == "sequence_design":
                        action = "Local sequence_design (Proto not used)"
                    else:
                        action = "Design"
                    steps.append(
                        {
                            "action": action,
                            "detail": (
                                f"{len(result['designs'])} sequences; "
                                f"engine={engine}; node={node_source}"
                            ),
                        }
                    )
            except proto_runner.ProtoUnavailable as e:
                steps.append({"action": "Design unavailable", "detail": str(e)})
                engine = "unavailable"

        if designs_doc is None:
            src_json = FIXTURES_DIR / "designs.example.json"
            src_fa = FIXTURES_DIR / "designs.example.fasta"
            shutil.copy2(src_json, run_dir / "designs.json")
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
    (run_dir / "designs.json").write_text(json.dumps(designs_doc, indent=2))
    if not (run_dir / "designs.fasta").exists():
        (run_dir / "designs.fasta").write_text(
            proto_runner.designs_to_fasta(designs_doc.get("designs") or [])
        )

    provenance_nodes[AGENT_NAME] = node_source
    elapsed = time.perf_counter() - start
    n = len(designs_doc.get("designs") or [])
    honest = (
        f"engine={engine}"
        if engine == "proto_language"
        else f"engine={engine} (not Proto — do not claim Modal Proto)"
    )
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": "proto_language" if engine == "proto_language" else None,
        "input_summary": f"mode={mode}; USE_PROTO={USE_PROTO}",
        "output_summary": f"{n} designs; {honest}",
        "steps": steps,
        "tool_calls": tool_calls,
    }
    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "designs": designs_doc,
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
