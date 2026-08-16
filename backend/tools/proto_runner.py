"""Leftover Proto design runner — not imported by backend/agents/designer.py.

Live designer: BindCraft-from-disk → sequence_design → fixtures.
Keep USE_PROTO=0. Do not claim this module ran on a pipeline click.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.config import MODAL_TOKEN_ID, MODAL_TOKEN_SECRET, USE_PROTO, live_design_requested

REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_SCRIPT = REPO_ROOT / "design" / "kras_g12c.py"


class ProtoUnavailable(RuntimeError):
    """Raised when Proto/sequence_design cannot produce designs."""


def is_configured() -> bool:
    """Modal tokens present (needed for Proto GPU tools at re:AGENT)."""
    return bool(MODAL_TOKEN_ID and MODAL_TOKEN_SECRET)


def designs_to_fasta(designs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for d in designs:
        lines.append(f">{d['id']}")
        lines.append(d.get("sequence", ""))
    return "\n".join(lines) + ("\n" if lines else "")


def _run_real_proto(spec: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    """Attempt design/proto_binder.py (RFdiffusion3 + MPNN + ipTM)."""
    try:
        from design.proto_binder import (
            ProtoNotInstalled,
            ProtoRunFailed,
            build_and_run_binder_program,
            should_attempt_proto,
        )
    except ImportError as exc:
        print(f"proto_runner: cannot import design.proto_binder ({exc})", file=sys.stderr)
        return None

    if not should_attempt_proto():
        print(
            "proto_runner: Proto skipped — install proto-language/proto-tools and set USE_PROTO=1",
            file=sys.stderr,
        )
        return None

    if USE_PROTO and not is_configured():
        print(
            "proto_runner: USE_PROTO=1 but MODAL_TOKEN_ID/SECRET missing — "
            "Proto GPU tools usually need Modal. Attempting anyway…",
            file=sys.stderr,
        )

    try:
        payload = build_and_run_binder_program(spec, out_dir)
        if payload and payload.get("designs"):
            (out_dir / "designs.json").write_text(json.dumps(payload, indent=2) + "\n")
            (out_dir / "designs.fasta").write_text(designs_to_fasta(payload["designs"]))
            return payload
    except ProtoNotInstalled as exc:
        print(f"proto_runner: {exc}", file=sys.stderr)
    except ProtoRunFailed as exc:
        print(f"proto_runner: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"proto_runner: unexpected Proto error ({exc})", file=sys.stderr)
    return None


def _run_sequence_design(spec: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    """Interim live path: backend.tools.sequence_design (provenance=live)."""
    try:
        from backend.tools.sequence_design import designs_to_fasta as sdfasta
        from backend.tools.sequence_design import generate_designs

        payload = generate_designs(spec, n=8)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "designs.json").write_text(json.dumps(payload, indent=2) + "\n")
        (out_dir / "designs.fasta").write_text(sdfasta(payload.get("designs") or []))
        return payload
    except Exception as exc:  # noqa: BLE001
        print(f"proto_runner: sequence_design failed ({exc})", file=sys.stderr)
        return None


def run_proto_design(
    spec_path: str | Path,
    out_dir: str | Path,
    live: bool = False,
) -> dict[str, Any] | None:
    """Run `design/kras_g12c.py` and return parsed designs.json, or None on failure."""
    spec_path = Path(spec_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not DESIGN_SCRIPT.is_file():
        print(f"proto_runner: missing design script {DESIGN_SCRIPT}", file=sys.stderr)
        return None

    try:
        sys.path.insert(0, str(REPO_ROOT))
        from design.kras_g12c import run as design_run

        payload = design_run(spec_path, out_dir, live=live)
        return payload
    except Exception as exc:  # noqa: BLE001 — fall through to CLI
        print(f"proto_runner: import path failed ({exc}); trying CLI", file=sys.stderr)

    cmd = [
        sys.executable,
        str(DESIGN_SCRIPT),
        "--spec",
        str(spec_path),
        "--out-dir",
        str(out_dir),
    ]
    if live:
        cmd.append("--live")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        return None

    designs_path = out_dir / "designs.json"
    if not designs_path.is_file():
        return None
    with designs_path.open() as f:
        return json.load(f)


def run_proto(
    spec: dict[str, Any],
    out_dir: str | Path | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Live path: Proto binder → sequence_design → raise if nothing worked.

    Never claims Modal Proto succeeded when only the local generator ran.
    Returns payload with designs[].generator / meta.engine for honest traces.
    """
    if out_dir is None:
        raise ProtoUnavailable(
            "Proto unavailable: no out_dir for design. Use fixtures."
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_path = out_dir / "spec.json"
    if spec:
        if not spec_path.exists():
            spec_path.write_text(json.dumps(spec, indent=2))
        else:
            try:
                existing = json.loads(spec_path.read_text())
                if existing.get("provenance") != "live" and spec.get("provenance") == "live":
                    spec_path.write_text(json.dumps(spec, indent=2))
            except Exception:  # noqa: BLE001
                spec_path.write_text(json.dumps(spec, indent=2))
    if not spec_path.exists() and not spec:
        raise ProtoUnavailable("Proto unavailable: missing spec.json for design.")

    live = bool(kwargs.get("live", True))
    if live_design_requested():
        live = True

    # 1) Real Proto binder program (RFdiffusion3 + MPNN + ipTM)
    if live and spec:
        result = _run_real_proto(spec, out_dir)
        if result and result.get("designs"):
            result.setdefault("meta", {})["design_engine"] = "proto_language"
            return result

    # 2) Interim local sequence_design (honest: not Proto)
    if live and spec:
        result = _run_sequence_design(spec, out_dir)
        if result and result.get("designs"):
            result.setdefault("meta", {})["design_engine"] = "sequence_design"
            return result

    # 3) CLI orchestrator fallback (fixtures / edge cases)
    if spec_path.exists():
        result = run_proto_design(spec_path, out_dir, live=live)
        if result and result.get("designs"):
            gens = {
                d.get("generator")
                for d in result["designs"]
                if isinstance(d, dict) and d.get("generator")
            }
            if any(g and "proto" in str(g) for g in gens):
                engine = "proto_language"
            elif any(d.get("provenance") == "live" for d in result["designs"]):
                engine = "sequence_design"
            else:
                engine = "fixture"
            result.setdefault("meta", {})["design_engine"] = engine
            return result

    raise ProtoUnavailable(
        "Design unavailable: Proto not installed/configured and sequence_design returned no designs. "
        "Use fixtures, or install Proto (spec/runbooks/proto.md) and set USE_PROTO=1 + Modal tokens."
    )
