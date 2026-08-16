"""Tamarind fold/complex client — REST when TAMARIND_API_KEY set, else unavailable.

Follows https://app.tamarind.bio/llms-full.txt:
  GET /tools → validate-job → submit-job → poll GET /jobs?jobName= → Score / result.

Heuristic fold metrics (sequence_design.estimate_fold_metrics) are available via
`apply_heuristic_metrics` for structure-agent fallback. Never present heuristics
as Tamarind/AlphaFold results.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import requests

from backend.config import TAMARIND_API_KEY

TAMARIND_BASE = "https://app.tamarind.bio/api/"
TAMARIND_TOOLS = TAMARIND_BASE + "tools"
TAMARIND_VALIDATE = TAMARIND_BASE + "validate-job"
TAMARIND_SUBMIT = TAMARIND_BASE + "submit-job"
TAMARIND_JOBS = TAMARIND_BASE + "jobs"
TAMARIND_RESULT = TAMARIND_BASE + "result"
SMOKE_TIMEOUT_S = 180
# Prefer fast monomer fold for smoke; fall back to heavier predictors.
PREFERRED_FOLD_TYPES = ("esmfold", "alphafold", "boltz", "chai")


class TamarindUnavailable(RuntimeError):
    """Raised when Tamarind cannot be reached or is not configured."""


def is_configured() -> bool:
    return bool(TAMARIND_API_KEY)


def _headers() -> dict[str, str]:
    return {
        "x-api-key": TAMARIND_API_KEY or "",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _safe_job_name(prefix: str) -> str:
    """Tamarind jobName: ^[a-zA-Z0-9_-]+$, unique per account."""
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", prefix).strip("-")[:40] or "idoctor-design"
    return f"{stem}-{uuid.uuid4().hex[:8]}"


def list_tools() -> list[dict[str, Any]]:
    r = requests.get(TAMARIND_TOOLS, headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise TamarindUnavailable(f"Unexpected /tools shape: {type(data)}")
    return data


def pick_fold_tool(tools: list[dict[str, Any]] | None = None) -> str:
    """Choose a live fold tool from GET /tools (never invent names)."""
    tools = tools if tools is not None else list_tools()
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    for preferred in PREFERRED_FOLD_TYPES:
        if preferred in names:
            return preferred
    # Last resort: any tool whose description mentions structure/fold/predict
    for t in tools:
        blob = f"{t.get('name','')} {t.get('description','')}".lower()
        if "fold" in blob or "structure predict" in blob:
            name = t.get("name")
            if name:
                return str(name)
    raise TamarindUnavailable("No fold/structure tool found in live GET /tools catalog.")


def _validate_and_normalize(job_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        TAMARIND_VALIDATE,
        headers=_headers(),
        json={"type": job_type, "settings": settings},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if not payload.get("valid"):
        raise TamarindUnavailable(
            f"validate-job failed for {job_type}: {payload.get('error')}"
        )
    return payload.get("normalized") or settings


def _submit_job(job_type: str, sequence: str, name: str) -> str:
    """Submit one fold job; return jobName used for polling."""
    settings = _validate_and_normalize(job_type, {"sequence": sequence})
    body = {"jobName": name, "type": job_type, "settings": settings}
    resp = requests.post(TAMARIND_SUBMIT, headers=_headers(), json=body, timeout=30)
    if resp.status_code >= 400:
        raise TamarindUnavailable(
            f"submit-job {job_type} HTTP {resp.status_code}: {resp.text[:300]}"
        )
    # API returns a confirmation string; jobs are addressed by jobName
    return name


def _poll_job(job_name: str, budget_s: float = SMOKE_TIMEOUT_S) -> dict[str, Any]:
    """Poll GET /jobs?jobName= until terminal. Returns job row."""
    deadline = time.time() + budget_s
    last: dict[str, Any] = {}
    terminal = {"Complete", "Stopped", "Deleted"}
    while time.time() < deadline:
        r = requests.get(
            TAMARIND_JOBS,
            headers=_headers(),
            params={"jobName": job_name},
            timeout=30,
        )
        if r.status_code >= 400:
            time.sleep(5)
            continue
        last = r.json() if r.content else {}
        # By-name returns the job row directly (no jobs wrapper)
        if isinstance(last, dict) and "jobs" in last and isinstance(last["jobs"], list):
            last = last["jobs"][0] if last["jobs"] else {}
        status = last.get("JobStatus") or last.get("jobStatus") or last.get("status")
        if status in terminal:
            if status != "Complete":
                raise TamarindUnavailable(f"Tamarind job {job_name} ended as {status}")
            return last
        time.sleep(10)
    raise TamarindUnavailable(f"Tamarind job {job_name} timed out after {budget_s}s")


def _metrics_from_job(job: dict[str, Any]) -> dict[str, Any]:
    """Parse Tamarind job row Score (often a JSON string) into pLDDT / iptm / ptm."""
    out: dict[str, Any] = {"plddt": None, "iptm": None, "ptm": None}
    raw = job.get("Score")
    if raw in (None, ""):
        return out
    parsed: Any = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            try:
                out["plddt"] = float(raw)
            except ValueError:
                pass
            return out
    if isinstance(parsed, (int, float)):
        out["plddt"] = float(parsed)
        return out
    if isinstance(parsed, dict):
        for key in ("plddt", "meanPlddt", "mean_plddt", "pLDDT"):
            if parsed.get(key) is not None:
                try:
                    out["plddt"] = float(parsed[key])
                    break
                except (TypeError, ValueError):
                    pass
        for key in ("iptm", "ipTM"):
            if parsed.get(key) is not None:
                try:
                    out["iptm"] = float(parsed[key])
                    break
                except (TypeError, ValueError):
                    pass
        for key in ("ptm", "pTM"):
            if parsed.get(key) is not None:
                try:
                    out["ptm"] = float(parsed[key])
                    break
                except (TypeError, ValueError):
                    pass
    return out


def _maybe_download_pdb(job_name: str, dest_dir: str | None = None) -> str | None:
    """Download result zip and extract first .pdb if dest_dir given."""
    if not dest_dir:
        return None
    try:
        import io
        import zipfile
        from pathlib import Path

        url = requests.post(
            TAMARIND_RESULT, headers=_headers(), json={"jobName": job_name}, timeout=60
        ).text.strip().strip('"')
        if not url.startswith("http"):
            return None
        zbytes = requests.get(url, timeout=120).content
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
        out_dir = Path(dest_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in zf.namelist():
            if name.lower().endswith(".pdb"):
                target = out_dir / f"{job_name}.pdb"
                target.write_bytes(zf.read(name))
                return str(target)
    except Exception:
        return None
    return None


def _score_from_job(job: dict[str, Any]) -> float | None:
    return _metrics_from_job(job).get("plddt")


def submit_fold(sequences: list[dict[str, str]], **kwargs: Any) -> dict[str, Any] | None:
    """Submit fold jobs via Tamarind REST. Raises TamarindUnavailable if no key / errors.

    Discovers a live fold tool via GET /tools (prefers esmfold). Smoke: ≤3 jobs.
    """
    if not is_configured():
        raise TamarindUnavailable(
            "Tamarind unavailable: TAMARIND_API_KEY not set. Use heuristic/fixture fallback."
        )

    if not sequences:
        return {"metrics": []}

    budget = float(kwargs.get("timeout", SMOKE_TIMEOUT_S))
    tools = list_tools()
    job_type = kwargs.get("job_type") or pick_fold_tool(tools)

    metrics: list[dict[str, Any]] = []
    errors: list[str] = []
    capped = sequences[: int(kwargs.get("max_jobs", 3))]
    per_seq_budget = max(45.0, budget / max(len(capped), 1))

    for item in capped:
        seq = item.get("sequence") or ""
        did = item.get("id") or "design"
        job_name = _safe_job_name(f"rl-{did}")
        try:
            _submit_job(job_type, seq, job_name)
            job = _poll_job(job_name, budget_s=per_seq_budget)
            parsed = _metrics_from_job(job)
            pdb_path = _maybe_download_pdb(job_name, kwargs.get("structures_dir"))
            metrics.append(
                {
                    "id": did,
                    "plddt": parsed.get("plddt"),
                    "iptm": parsed.get("iptm"),
                    "ptm": parsed.get("ptm"),
                    "pdb_path": pdb_path,
                    "job_name": job_name,
                    "job_type": job_type,
                    "raw_status": job.get("JobStatus"),
                    "raw": {"Score": job.get("Score"), "Type": job.get("Type")},
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{did}: {exc}")

    if not metrics:
        raise TamarindUnavailable(
            "Tamarind unavailable: no successful fold metrics. " + "; ".join(errors[:3])
        )
    return {"metrics": metrics, "errors": errors, "job_type": job_type}


def get_structure_metrics(design_id: str) -> dict[str, Any] | None:
    """Fetch cached metrics for a design if Tamarind is live."""
    if not is_configured():
        return None
    try:
        r = requests.get(
            TAMARIND_JOBS,
            headers=_headers(),
            params={"jobName": f"rl-{design_id}"},
            timeout=30,
        )
        if not r.ok:
            return None
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def apply_heuristic_metrics(designs: dict[str, Any]) -> dict[str, Any]:
    """Patch designs with sequence_design.estimate_fold_metrics (structure agent fallback)."""
    from backend.tools.sequence_design import estimate_fold_metrics

    out = dict(designs)
    items = list(out.get("designs") or [])
    patched = []
    for d in items:
        d = dict(d)
        seq = d.get("sequence") or ""
        metrics = estimate_fold_metrics(seq)
        d["plddt"] = metrics["plddt"]
        d["iptm"] = metrics["iptm"]
        d["fold_method"] = "heuristic_v1"
        patched.append(d)
    out["designs"] = patched
    return out
