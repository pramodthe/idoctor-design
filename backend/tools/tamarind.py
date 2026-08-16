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


def _drop_inapplicable(settings: dict[str, Any]) -> dict[str, Any]:
    """Remove conditional keys validate-job echoes back but submit-job rejects.

    validate-job fills every default, including settings that are only legal
    when a controlling field has a particular value. Submitting that dict back
    verbatim then 400s, e.g. `bfvdTemplates` is only accepted when
    templateMode == "pdb100".
    """
    out = dict(settings)
    if str(out.get("templateMode") or "") != "pdb100":
        out.pop("bfvdTemplates", None)
    return out


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
    return _drop_inapplicable(payload.get("normalized") or settings)


def validate_job_spec(job_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Public Tamarind seam for Ryan's designspec.py (and any sibling engine).

    Payload shape is exactly Tamarind's POST /validate-job body:

        {"type": job_type, "settings": settings}

    Returns the service's `normalized` settings dict. Raises
    TamarindUnavailable if TAMARIND_API_KEY is missing or the spec is invalid.
    This is a validation-only call — it does not submit a BindCraft/fold job
    and must not be described as a completed design run.

    BindCraft example (pdbFile must already be a Tamarind file ref):

        validate_job_spec(
            "bindcraft",
            {
                "mode": "default",
                "pdbFile": "<file-ref>",
                "chains": ["A"],
                "numDesigns": 10,
                "binderLengthRange": "70,150",
                "maxRunTime": 4,
                "hotspotResidues": {"A": "12,69,95,96"},
            },
        )
    """
    if not is_configured():
        raise TamarindUnavailable("Tamarind unavailable: TAMARIND_API_KEY not set.")
    try:
        return _validate_and_normalize(job_type, settings)
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            body = (exc.response.text or "")[:300]
        raise TamarindUnavailable(
            f"validate-job HTTP error for {job_type}: {exc} {body}".strip()
        ) from exc


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


def _complex_metrics_from_zip(
    job_name: str,
    dest_dir: str | None = None,
    artifact_label: str | None = None,
) -> dict[str, Any]:
    """Read metrics and preserve useful Tamarind result artifacts.

    Tamarind returns substantially more than one PDB: confidence plots, PAE
    matrices, score JSON, settings, logs, alignments, and CSV tables.  Keep a
    manifest of those files so the trust UI can expose the actual model output
    instead of reducing a job to two scalar scores.
    """
    import csv
    import io
    import zipfile
    from pathlib import Path

    response = requests.post(
        TAMARIND_RESULT, headers=_headers(), json={"jobName": job_name}, timeout=60
    )
    response.raise_for_status()
    url = response.text.strip().strip('"')
    if not url.startswith("http"):
        raise TamarindUnavailable(f"result for {job_name} did not return a URL")
    archive_response = requests.get(url, timeout=180)
    archive_response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(archive_response.content))

    rows: list[dict[str, str]] = []
    for name in archive.namelist():
        if name.lower().endswith(".csv"):
            text = archive.read(name).decode("utf-8", "replace").splitlines()
            rows.extend(list(csv.DictReader(text)))

    def number(row: dict[str, Any], *wanted: str) -> float | None:
        normalized = {
            re.sub(r"[^a-z0-9]+", "", str(key).lower()): value
            for key, value in row.items()
        }
        for key in wanted:
            value = normalized.get(re.sub(r"[^a-z0-9]+", "", key.lower()))
            if value not in (None, ""):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    parsed_rows = [
        {
            "iptm": number(row, "iptm", "interface_ptm"),
            "plddt": number(row, "plddt", "avg_plddt", "mean_plddt"),
            "ptm": number(row, "ptm"),
            "ipsae": number(row, "ipsae", "ipsae_score"),
            "ranking_score": number(row, "ranking_score", "aggregate_score"),
            "raw": row,
        }
        for row in rows
    ]
    best = max(
        parsed_rows,
        key=lambda row: (
            row.get("iptm") if row.get("iptm") is not None else -1.0,
            row.get("ranking_score")
            if row.get("ranking_score") is not None
            else -1.0,
        ),
        default={},
    )

    pdb_path = None
    artifacts: list[dict[str, str]] = []
    if dest_dir:
        out_dir = Path(dest_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        label = re.sub(r"[^a-zA-Z0-9_-]+", "-", artifact_label or job_name)
        artifact_dir = out_dir / f"{label}-artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        def artifact_kind(filename: str) -> str:
            lower = filename.lower()
            if lower.endswith(".png"):
                return "image"
            if lower.endswith(".pdb"):
                return "structure"
            if lower.endswith((".csv", ".parquet")):
                return "table"
            if lower.endswith(".a3m"):
                return "alignment"
            if lower.endswith(".json"):
                return "data"
            if lower.endswith((".log", ".txt")):
                return "log"
            return "file"

        for member in archive.infolist():
            if member.is_dir():
                continue
            safe_name = Path(member.filename).name
            if not safe_name:
                continue
            target = artifact_dir / safe_name
            target.write_bytes(archive.read(member.filename))
            artifacts.append(
                {
                    "name": safe_name,
                    "kind": artifact_kind(safe_name),
                    "path": str(target),
                }
            )

        pdb_names = [name for name in archive.namelist() if name.lower().endswith(".pdb")]
        if pdb_names:
            target = out_dir / f"{label}.pdb"
            target.write_bytes(archive.read(pdb_names[0]))
            pdb_path = str(target)
    return {**best, "pdb_path": pdb_path, "artifacts": artifacts}


def submit_complex_panel(
    binder_id: str,
    binder_sequence: str,
    targets: dict[str, str],
    *,
    structures_dir: str | None = None,
    timeout: float = 1800.0,
    job_type: str = "alphafold",
) -> dict[str, Any]:
    """Predict target:binder complexes and return real interface metrics per target.

    AlphaFold multimer receives colon-separated chains and Tamarind's IPSAE option.
    All target variants are submitted first, then polled concurrently.
    """
    if not is_configured():
        raise TamarindUnavailable("Tamarind unavailable: TAMARIND_API_KEY not set.")
    if not binder_sequence or not targets:
        raise TamarindUnavailable("Complex panel needs a binder and at least one target")

    available = {str(tool.get("name") or "") for tool in list_tools()}
    if job_type not in available:
        raise TamarindUnavailable(f"Tamarind tool {job_type!r} is not available")

    submitted: list[tuple[str, str]] = []
    errors: list[str] = []
    for variant, target_sequence in targets.items():
        settings = {
            "sequence": f"{target_sequence}:{binder_sequence}",
            "numModels": "1",
            "numRecycles": 3,
            "numRelax": 0,
            "useMSA": True,
            "pairMode": "unpaired_paired",
            "templateMode": "none",
            "ipsaeScoring": True,
            "modelType": "alphafold2_multimer_v3",
        }
        try:
            normalized = _validate_and_normalize(job_type, settings)
            job_name = _safe_job_name(f"complex-{binder_id}-{variant}")
            response = requests.post(
                TAMARIND_SUBMIT,
                headers=_headers(),
                json={"jobName": job_name, "type": job_type, "settings": normalized},
                timeout=60,
            )
            if response.status_code >= 400:
                raise TamarindUnavailable(
                    f"submit-job {job_type} HTTP {response.status_code}: {response.text[:240]}"
                )
            submitted.append((variant, job_name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{variant}: {exc}")

    if not submitted:
        raise TamarindUnavailable("No complex jobs accepted. " + "; ".join(errors[:3]))

    from concurrent.futures import ThreadPoolExecutor

    def collect(pair: tuple[str, str]) -> tuple[str, dict[str, Any] | None]:
        variant, job_name = pair
        try:
            job = _poll_job(job_name, budget_s=timeout)
            metrics = _complex_metrics_from_zip(
                job_name,
                structures_dir,
                artifact_label=f"{binder_id}-{variant}-complex",
            )
            fallback = _metrics_from_job(job)
            for key in ("plddt", "iptm", "ptm"):
                if metrics.get(key) is None:
                    metrics[key] = fallback.get(key)
            metrics.update(
                {
                    "job_name": job_name,
                    "job_type": job_type,
                    "variant": variant,
                }
            )
            if metrics.get("iptm") is None:
                raise TamarindUnavailable(f"{job_name}: result had no ipTM")
            return variant, metrics
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{variant}: {exc}")
            return variant, None

    with ThreadPoolExecutor(max_workers=min(4, len(submitted))) as pool:
        collected = list(pool.map(collect, submitted))
    metrics = {variant: row for variant, row in collected if row is not None}
    if not metrics:
        raise TamarindUnavailable("Complex jobs produced no ipTM. " + "; ".join(errors[:3]))
    return {
        "binder_id": binder_id,
        "metrics": metrics,
        "errors": errors,
        "job_type": job_type,
        "score_kind": "iptm",
        "score_direction": "higher_is_better",
    }


def upload_file(path: str, folder: str = "inputs") -> str:
    """PUT a local file to Tamarind storage; return the reference used in settings.

    Per the API docs a file-typed setting given a plain string is treated as inline
    content, so a job must reference an uploaded file by name — never by raw text
    or URL.
    """
    from pathlib import Path

    src = Path(path)
    if not src.is_file():
        raise TamarindUnavailable(f"upload_file: {path} does not exist")

    headers = {"x-api-key": TAMARIND_API_KEY or "", "Content-Type": "application/octet-stream"}
    url = f"{TAMARIND_BASE}upload/{src.name}"
    params = {"folder": folder} if folder else None
    r = requests.put(url, headers=headers, params=params, data=src.read_bytes(), timeout=120)
    if r.status_code >= 400:
        raise TamarindUnavailable(f"upload {src.name} HTTP {r.status_code}: {r.text[:200]}")
    return f"{folder}/{src.name}" if folder else src.name


def _designs_from_zip(job_name: str, dest_dir: str | None) -> list[dict[str, Any]]:
    """Pull designed sequences (FASTA) and structures (PDB) out of a result zip."""
    import io
    import zipfile
    from pathlib import Path

    url = requests.post(
        TAMARIND_RESULT, headers=_headers(), json={"jobName": job_name}, timeout=60
    ).text.strip().strip('"')
    if not url.startswith("http"):
        raise TamarindUnavailable(f"result for {job_name} did not return a URL")

    zf = zipfile.ZipFile(io.BytesIO(requests.get(url, timeout=300).content))
    out_dir = Path(dest_dir) if dest_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    sequences: dict[str, str] = {}
    pdbs: dict[str, str] = {}

    for name in zf.namelist():
        low = name.lower()
        if low.endswith((".fasta", ".fa")):
            cur_id = None
            chunks: list[str] = []
            for line in zf.read(name).decode("utf-8", "replace").splitlines():
                line = line.strip()
                if line.startswith(">"):
                    if cur_id and chunks:
                        sequences[cur_id] = "".join(chunks)
                    cur_id = line[1:].split()[0] if len(line) > 1 else None
                    chunks = []
                elif line:
                    chunks.append(line)
            if cur_id and chunks:
                sequences[cur_id] = "".join(chunks)
        elif low.endswith(".pdb") and out_dir:
            stem = Path(name).stem
            target = out_dir / f"{job_name}-{stem}.pdb"
            target.write_bytes(zf.read(name))
            pdbs[stem] = str(target)

    # CSVs carry BindCraft's per-design filter metrics (pLDDT, i_pAE, ipTM, ...).
    metrics_rows: list[dict[str, str]] = []
    for name in zf.namelist():
        if name.lower().endswith(".csv"):
            import csv

            text = zf.read(name).decode("utf-8", "replace").splitlines()
            metrics_rows.extend(list(csv.DictReader(text)))

    out: list[dict[str, Any]] = []
    for design_id, seq in sequences.items():
        row = next(
            (r for r in metrics_rows if design_id in " ".join(str(v) for v in r.values())),
            {},
        )

        def _num(*keys: str) -> float | None:
            for k in keys:
                for rk, rv in row.items():
                    if rk and rk.strip().lower() == k and rv not in (None, ""):
                        try:
                            return float(rv)
                        except (TypeError, ValueError):
                            pass
            return None

        out.append(
            {
                "id": design_id,
                "sequence": seq,
                "plddt": _num("plddt", "average_plddt", "mean_plddt"),
                "iptm": _num("iptm", "i_ptm"),
                "ipae": _num("i_pae", "ipae", "interface_pae"),
                "pdb_path": pdbs.get(design_id),
                "raw_metrics": row or None,
            }
        )
    if not out:
        raise TamarindUnavailable(f"{job_name}: result zip held no designed sequences")
    return out


# BindCraft's per-design acceptance thresholds. They are returned by validate-job
# for visibility, but may only be submitted when filterType is "custom".
_BINDCRAFT_FILTER_KEYS = (
    "pLDDT",
    "pTM",
    "ipTM",
    "i_pAE",
    "Surface_Hydrophobicity",
    "n_InterfaceResidues",
    "n_InterfaceHbonds",
    "Hotspot_RMSD",
    "Binder_pLDDT",
    "Binder_RMSD",
)


def _hotspots_by_chain(
    hotspots: list[str] | str | dict[str, str], default_chain: str = "A"
) -> dict[str, str]:
    """Normalize hotspots to BindCraft's {chain: "12,69,95"} shape.

    Accepts what the rest of the codebase already produces — "A96", "96", or a
    plain list of either — since proto_binder emits chain-prefixed residue ids.
    """
    if isinstance(hotspots, dict):
        return {str(k): str(v) for k, v in hotspots.items()}

    items = hotspots.split(",") if isinstance(hotspots, str) else list(hotspots)
    by_chain: dict[str, list[str]] = {}
    for raw in items:
        token = str(raw).strip()
        if not token:
            continue
        m = re.fullmatch(r"([A-Za-z]?)[-_]?(\d+)", token)
        if not m:
            continue
        chain = m.group(1).upper() or default_chain
        by_chain.setdefault(chain, []).append(m.group(2))
    return {c: ",".join(nums) for c, nums in by_chain.items() if nums}


def submit_bindcraft(
    pdb_path: str,
    chains: list[str] | str,
    hotspot_residues: list[str] | str | None = None,
    num_designs: int = 10,
    binder_length_range: str = "70,150",
    mode: str = "default",
    structures_dir: str | None = None,
    timeout: float = 7200.0,
    max_run_time: int = 4,
) -> dict[str, Any]:
    """Design binders against a target with BindCraft (RFdiffusion + MPNN + AF2 filters).

    BindCraft generates candidates and keeps only those passing its confidence
    filters, so the returned designs are survivors of a real screen rather than
    raw model output.
    """
    if not is_configured():
        raise TamarindUnavailable("Tamarind unavailable: TAMARIND_API_KEY not set.")

    file_ref = upload_file(pdb_path)
    chain_list = chains if isinstance(chains, list) else [chains]
    settings: dict[str, Any] = {
        "mode": mode,
        "pdbFile": file_ref,
        "chains": chain_list,
        "numDesigns": int(num_designs),
        "binderLengthRange": binder_length_range,
        # Free Tamarind accounts reject anything above 4h; the validator defaults to 16.
        "maxRunTime": int(max_run_time),
    }
    if hotspot_residues:
        settings["hotspotResidues"] = _hotspots_by_chain(hotspot_residues, chain_list[0])

    settings = _validate_and_normalize("bindcraft", settings)
    # validate-job echoes BindCraft's default filter thresholds, but submit-job
    # rejects them unless filterType is "custom". Keep the defaults implicit.
    if str(settings.get("filterType", "default")) != "custom":
        for key in _BINDCRAFT_FILTER_KEYS:
            settings.pop(key, None)
    job_name = _safe_job_name("bindcraft-kras")
    body = {"jobName": job_name, "type": "bindcraft", "settings": settings}
    resp = requests.post(TAMARIND_SUBMIT, headers=_headers(), json=body, timeout=60)
    if resp.status_code >= 400:
        raise TamarindUnavailable(
            f"submit-job bindcraft HTTP {resp.status_code}: {resp.text[:300]}"
        )

    job = _poll_job(job_name, budget_s=timeout)
    designs = _designs_from_zip(job_name, structures_dir)
    return {
        "designs": designs,
        "job_name": job_name,
        "job_type": "bindcraft",
        "settings": settings,
        "raw_status": job.get("JobStatus"),
    }


def submit_vina_docking(
    receptor_pdb: str,
    compounds: list[dict[str, Any]],
    center: list[float],
    box: list[float],
    exhaustiveness: int = 32,
    structures_dir: str | None = None,
    timeout: float = 5400.0,
    job_label: str = "vina",
) -> dict[str, Any]:
    """Dock many compounds against one receptor with AutoDock Vina on Tamarind.

    Tamarind accepts a CSV of SMILES to dock a whole library against a single
    receptor in one job, so the entire control-arm panel goes up at once rather
    than one submission per compound.
    """
    if not is_configured():
        raise TamarindUnavailable("Tamarind unavailable: TAMARIND_API_KEY not set.")

    usable = [c for c in compounds if c.get("smiles") and c.get("id")]
    if not usable:
        raise TamarindUnavailable("submit_vina_docking: no compounds with SMILES")

    # A multi-SMILES block passes validate-job but dies at runtime, so each
    # ligand goes up as its own job and they are polled concurrently.
    receptor_ref = upload_file(receptor_pdb)
    base: dict[str, Any] = {
        "receptorFile": receptor_ref,
        "ligandFormat": "smiles",
        "boxX": float(center[0]),
        "boxY": float(center[1]),
        "boxZ": float(center[2]),
        "width": float(box[0]),
        "height": float(box[1]),
        "depth": float(box[2]),
        "exhaustiveness": int(exhaustiveness),
    }

    submitted: list[tuple[str, str]] = []
    errors: list[str] = []
    for c in usable:
        cid = str(c["id"])
        settings = _validate_and_normalize(
            "autodock-vina", {**base, "ligandSmiles": str(c["smiles"]).strip()}
        )
        job_name = _safe_job_name(f"vina-{job_label}-{cid}")
        resp = requests.post(
            TAMARIND_SUBMIT,
            headers=_headers(),
            json={"jobName": job_name, "type": "autodock-vina", "settings": settings},
            timeout=60,
        )
        if resp.status_code >= 400:
            errors.append(f"{cid}: HTTP {resp.status_code} {resp.text[:120]}")
            continue
        submitted.append((cid, job_name))

    if not submitted:
        raise TamarindUnavailable(
            "submit_vina_docking: no jobs accepted. " + "; ".join(errors[:3])
        )

    from concurrent.futures import ThreadPoolExecutor

    def _collect(pair: tuple[str, str]) -> tuple[str, float | None]:
        cid, job_name = pair
        try:
            _poll_job(job_name, budget_s=timeout)
            found = _vina_scores_from_zip(job_name, structures_dir, {}, [cid])
            return cid, next(iter(found.values()), None)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{cid}: {exc}")
            return cid, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        collected = list(pool.map(_collect, submitted))

    scores = {cid: val for cid, val in collected if val is not None}
    if not scores:
        raise TamarindUnavailable(
            f"submit_vina_docking({job_label}): no affinities. " + "; ".join(errors[:3])
        )
    return {
        "scores": scores,
        "job_names": dict(submitted),
        "job_type": "autodock-vina",
        "settings": base,
        "errors": errors,
    }


def _vina_scores_from_zip(
    job_name: str,
    dest_dir: str | None,
    by_smiles: dict[str, str] | None = None,
    order: list[str] | None = None,
) -> dict[str, float]:
    """Read per-ligand affinities out of Vina's results-processed.csv.

    Ligands are submitted as an inline SMILES block, so the results are keyed
    back to compound ids by SMILES where the CSV echoes it, and by submission
    order otherwise.
    """
    import csv
    import io
    import zipfile
    from pathlib import Path

    url = requests.post(
        TAMARIND_RESULT, headers=_headers(), json={"jobName": job_name}, timeout=60
    ).text.strip().strip('"')
    if not url.startswith("http"):
        raise TamarindUnavailable(f"result for {job_name} did not return a URL")

    zf = zipfile.ZipFile(io.BytesIO(requests.get(url, timeout=300).content))
    out_dir = Path(dest_dir) if dest_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in zf.namelist():
            if name.lower().endswith((".pdb", ".sdf")):
                (out_dir / Path(name).name).write_bytes(zf.read(name))

    by_smiles = by_smiles or {}
    scores: dict[str, float] = {}
    for name in zf.namelist():
        if not name.lower().endswith(".csv"):
            continue
        rows = list(csv.DictReader(zf.read(name).decode("utf-8", "replace").splitlines()))
        for idx, row in enumerate(rows):
            ligand = None
            affinity = None
            for k, v in row.items():
                if not k:
                    continue
                key = k.strip().lower()
                val = str(v).strip()
                if affinity is None and "affinity" in key:
                    try:
                        affinity = float(v)
                    except (TypeError, ValueError):
                        pass
                if ligand is None and val in by_smiles:
                    ligand = by_smiles[val]
                elif ligand is None and key in ("name", "ligand", "ligand_name", "id") and val:
                    ligand = val
            if ligand is None and order and idx < len(order):
                ligand = order[idx]
            if ligand and affinity is not None:
                scores[ligand] = affinity
    if not scores:
        raise TamarindUnavailable(f"{job_name}: no affinities parsed from results CSV")
    return scores


def bindcraft_designs_doc(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a submit_bindcraft result into the designs.json contract shape.

    Every design here already passed BindCraft's published acceptance filters
    (pLDDT, ipTM, i_pAE, interface residue/H-bond counts, hotspot RMSD), so the
    scores are measured rather than estimated.
    """
    designs: list[dict[str, Any]] = []
    for i, d in enumerate(result.get("designs") or []):
        seq = d.get("sequence") or ""
        if not seq:
            continue
        designs.append(
            {
                "id": d.get("id") or f"bindcraft_{i + 1:03d}",
                "sequence": seq,
                "length": len(seq),
                "molecule_type": "miniprotein",
                "constraint_scores": {
                    "i_pae": d.get("ipae"),
                    "passed_bindcraft_filters": True,
                },
                "score_direction": "lower_is_better",
                "plddt": d.get("plddt"),
                "iptm": d.get("iptm"),
                "pdb_path": d.get("pdb_path"),
                "novelty": {"identity": None, "method": "unchecked"},
                "fold_method": "bindcraft:af2",
                "generator": "tamarind:bindcraft",
                "provenance": "live",
                "raw_metrics": d.get("raw_metrics"),
                "notes": (
                    "Designed by BindCraft on Tamarind (RFdiffusion + ProteinMPNN + "
                    "AlphaFold2), targeting KRAS G12C 6OIM chain A at hotspots "
                    "12/69/95/96. Survived BindCraft's default acceptance filters; "
                    "metrics are AF2 predictions, not wet-lab measurements."
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "score_direction": "lower_is_better",
        "designs": designs,
        "meta": {
            "engine": "bindcraft",
            "design_engine": "bindcraft",
            "job_name": result.get("job_name"),
            "settings": result.get("settings"),
        },
    }


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
