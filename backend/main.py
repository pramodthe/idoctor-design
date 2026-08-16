"""iDoctor Design FastAPI application."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.compounds import KRAS_COMPOUNDS, TARGET_COMPOUNDS
from backend.config import IDOCTOR_DESIGN_DEFAULT_MODE, KNOWN_TARGETS, RUNS_DIR
from backend.pipeline import AGENT_DISPLAY, run_idoctor_design_async
from backend.simulation.openmm_runner import download_pdb

jobs: dict[str, dict] = {}

AGENT_NAMES = [
    "evidence",
    "designer",
    "structure",
    "physics",
    "evaluate",
    "critic",
    "experiment",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    jobs.clear()


app = FastAPI(title="iDoctor Design", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    mode: Literal["fixture", "replay", "live"] = "fixture"
    run_id: str | None = None


class TamarindJobSpec(BaseModel):
    """Ryan's designspec.py seam: same body as Tamarind POST /validate-job."""

    type: str
    settings: dict


class RunResponse(BaseModel):
    job_id: str
    status: str
    run_id: str | None = None


def _latest_run_dir() -> Path | None:
    if not RUNS_DIR.exists():
        return None
    runs = [p for p in RUNS_DIR.iterdir() if p.is_dir()]
    if not runs:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime)


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


@app.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest):
    job_id = str(uuid.uuid4())[:8]
    mode = req.mode or IDOCTOR_DESIGN_DEFAULT_MODE
    jobs[job_id] = {
        "status": "running",
        "mode": mode,
        "run_id": req.run_id,
        "agent_status": {name: "pending" for name in AGENT_NAMES},
        "result": None,
        "events": asyncio.Queue(),
    }

    async def _run():
        def progress_cb(agent_name: str, status: str, **kwargs):
            if agent_name in jobs[job_id]["agent_status"]:
                jobs[job_id]["agent_status"][agent_name] = status
            event = {
                "agent": agent_name,
                "agent_display": AGENT_DISPLAY.get(agent_name, agent_name),
                "status": status,
            }
            if "step" in kwargs:
                event["step"] = kwargs["step"]
                jobs[job_id]["current_step"] = kwargs["step"]
            try:
                jobs[job_id]["events"].put_nowait(event)
            except asyncio.QueueFull:
                pass

        try:
            result = await run_idoctor_design_async(mode, req.run_id, progress_cb)
            jobs[job_id]["result"] = result
            jobs[job_id]["run_id"] = result.get("run_id")
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["events"].put_nowait(
                {"status": "completed", "run_id": result.get("run_id")}
            )
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["events"].put_nowait({"status": "failed", "error": str(e)})

    asyncio.create_task(_run())
    return RunResponse(job_id=job_id, status="running", run_id=req.run_id)


@app.get("/api/status/{job_id}")
@app.get("/api/run/{job_id}/status")
async def stream_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        job = jobs[job_id]
        yield {
            "event": "status",
            "data": json.dumps(
                {
                    "status": job["status"],
                    "agent_status": job["agent_status"],
                    "run_id": job.get("run_id"),
                }
            ),
        }

        while job["status"] == "running":
            try:
                event = await asyncio.wait_for(job["events"].get(), timeout=30.0)
                yield {"event": "update", "data": json.dumps(event)}
                if event.get("status") in ("completed", "failed"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}

        yield {
            "event": "done",
            "data": json.dumps({"status": job["status"], "run_id": job.get("run_id")}),
        }

    return EventSourceResponse(event_generator())


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] == "running":
        resp = {
            "status": "running",
            "agent_status": job["agent_status"],
            "run_id": job.get("run_id"),
        }
        if "current_step" in job:
            resp["current_step"] = job["current_step"]
        return resp
    if job["status"] == "failed":
        raise HTTPException(status_code=500, detail=job.get("error", "Pipeline failed"))

    result = job["result"] or {}
    return {
        "status": "completed",
        "run_id": result.get("run_id"),
        "mode": result.get("mode"),
        "hypothesis": result.get("hypothesis"),
        "scientific_spec": result.get("scientific_spec"),
        "designs": result.get("designs"),
        "smallmol": result.get("smallmol"),
        "eval": result.get("eval") or result.get("eval_result"),
        "verdicts": result.get("verdicts"),
        "experiment_md": result.get("experiment_md"),
        "provenance": result.get("provenance"),
        "agent_traces": result.get("agent_traces", []),
        "agent_status": job.get("agent_status"),
    }


@app.get("/api/runs/latest")
async def get_latest_run():
    run_dir = _latest_run_dir()
    if not run_dir:
        raise HTTPException(status_code=404, detail="No runs found")
    files = sorted(p.name for p in run_dir.iterdir() if p.is_file())
    subdirs = sorted(p.name for p in run_dir.iterdir() if p.is_dir())
    return {
        "run_id": run_dir.name,
        "path": str(run_dir),
        "files": files,
        "directories": subdirs,
        "spec": _read_json(run_dir / "spec.json"),
        "designs": _read_json(run_dir / "designs.json"),
        "smallmol": _read_json(run_dir / "smallmol.json"),
        "eval": _read_json(run_dir / "eval.json"),
        "verdicts": _read_json(run_dir / "verdicts.json"),
        "provenance": _read_json(run_dir / "provenance.json"),
        "agent_traces": _read_json(run_dir / "traces.json"),
        "experiment_md": (run_dir / "experiment.md").read_text()
        if (run_dir / "experiment.md").exists()
        else None,
        "hypothesis": (_read_json(run_dir / "spec.json") or {}).get("hypothesis"),
    }


@app.get("/api/runs/{run_id}/file/{name}")
async def get_run_file(run_id: str, name: str):
    safe = Path(name).name
    if safe != name or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    path = RUNS_DIR / run_id / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {safe}")
    if safe.endswith((".md", ".fasta", ".txt")):
        return PlainTextResponse(path.read_text())
    if safe.endswith(".json"):
        return _read_json(path)
    return FileResponse(path)


@app.get("/api/protein/{pdb_id}")
async def get_protein(pdb_id: str):
    try:
        pdb_path = await asyncio.to_thread(download_pdb, pdb_id)
        return {"pdb_id": pdb_id.upper(), "pdb_data": pdb_path.read_text()}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch PDB {pdb_id}: {e}")


@app.get("/api/targets")
async def list_targets():
    return {
        "targets": [
            {"pdb_id": k, "name": v["name"], "ligand_id": v.get("ligand_id", "UNK")}
            for k, v in KNOWN_TARGETS.items()
        ]
    }


@app.get("/api/compounds")
async def list_compounds(pdb_id: str = "6OIM"):
    compounds = TARGET_COMPOUNDS.get(pdb_id.upper(), KRAS_COMPOUNDS)
    return {"compounds": compounds}


@app.get("/api/dock/{pdb_id}/{compound_id}")
async def dock_single(pdb_id: str, compound_id: str):
    """Dock a single compound — returns 3D pose PDB string for the viewer."""
    from backend.simulation.docking import dock_compound

    target_info = KNOWN_TARGETS.get(pdb_id.upper())
    if not target_info:
        raise HTTPException(status_code=404, detail=f"Unknown target: {pdb_id}")

    target_compounds = TARGET_COMPOUNDS.get(pdb_id.upper(), KRAS_COMPOUNDS)
    compound = next((c for c in target_compounds if c["id"] == compound_id), None)
    if not compound:
        raise HTTPException(status_code=404, detail=f"Unknown compound: {compound_id}")

    pdb_path = await asyncio.to_thread(download_pdb, pdb_id)
    center = target_info.get("binding_site_center", [0, 0, 0])

    result = await asyncio.to_thread(
        dock_compound, str(pdb_path), compound["smiles"], compound_id, center
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/tamarind/validate-job")
async def validate_tamarind_job(spec: TamarindJobSpec):
    """Validate a `{type, settings}` job against live Tamarind. Does not submit."""
    from backend.tools.tamarind import TamarindUnavailable, is_configured, validate_job_spec

    if not is_configured():
        raise HTTPException(status_code=503, detail="TAMARIND_API_KEY not set")
    try:
        normalized = await asyncio.to_thread(validate_job_spec, spec.type, spec.settings)
    except TamarindUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "type": spec.type, "normalized": normalized}


@app.get("/api/health")
async def health():
    from backend.tools.tamarind import is_configured as tamarind_configured

    return {
        "status": "ok",
        "service": "idoctor-design",
        "tamarind_configured": tamarind_configured(),
    }
