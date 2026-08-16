#!/usr/bin/env python3
"""iDoctor Design entrypoint (Workstream 4).

Reads an iDoctor Design `spec.json`, writes `designs.json` + `designs.fasta`.

Priority when `--live` / IDOCTOR_DESIGN_LIVE_DESIGN / live pipeline:
1. **Proto** (proto_language binder program) when packages available or USE_PROTO=1
2. Local `sequence_design` interim generator (`provenance: live`)
3. Fixture designs (`provenance: fixture`) — never claim these as inventions
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = REPO_ROOT / "spec" / "fixtures" / "spec.example.json"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "runs" / "local-design"
FIXTURE_DESIGNS_JSON = REPO_ROOT / "spec" / "fixtures" / "designs.example.json"
FIXTURE_DESIGNS_FASTA = REPO_ROOT / "spec" / "fixtures" / "designs.example.fasta"


def proto_available() -> bool:
    """True when Proto packages can be imported, or USE_PROTO forces an attempt."""
    sys.path.insert(0, str(REPO_ROOT))
    from design.proto_binder import proto_packages_available, use_proto_requested

    return proto_packages_available() or use_proto_requested()


def live_design_requested(cli_live: bool = False) -> bool:
    if cli_live:
        return True
    if os.environ.get("IDOCTOR_DESIGN_LIVE_DESIGN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    return False


def load_spec(spec_path: Path) -> dict[str, Any]:
    with spec_path.open() as f:
        return json.load(f)


def designs_to_fasta(designs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for d in designs:
        lines.append(f">{d['id']}")
        lines.append(d["sequence"])
    return "\n".join(lines) + ("\n" if lines else "")


def write_outputs(out_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "designs.json"
    fasta_path = out_dir / "designs.fasta"
    with json_path.open("w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    fasta_path.write_text(designs_to_fasta(payload.get("designs", [])))
    return json_path, fasta_path


def write_fixture_designs(out_dir: Path, reason: str | None = None) -> dict[str, Any]:
    """Copy example designs/fasta; force provenance=fixture on every design."""
    with FIXTURE_DESIGNS_JSON.open() as f:
        payload = json.load(f)

    for design in payload.get("designs", []):
        design["provenance"] = "fixture"

    json_path, fasta_path = write_outputs(out_dir, payload)

    if FIXTURE_DESIGNS_FASTA.is_file():
        shutil.copy2(FIXTURE_DESIGNS_FASTA, fasta_path)

    msg = reason or (
        "Proto/sequence_design unavailable. "
        "Wrote fixture designs with provenance=fixture — do not present these as live inventions."
    )
    print(msg)
    print(f"  designs.json → {json_path}")
    print(f"  designs.fasta → {fasta_path}")
    return payload


def write_live_designs(spec: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Interim live path: local sequence_design generator (not Proto Modal)."""
    sys.path.insert(0, str(REPO_ROOT))
    from backend.tools.sequence_design import generate_designs

    payload = generate_designs(spec, n=8)
    json_path, fasta_path = write_outputs(out_dir, payload)
    print(
        "Live local sequence_design wrote designs with provenance=live "
        "(not Proto/Modal — do not claim Modal Proto)."
    )
    print(f"  designs.json → {json_path}")
    print(f"  designs.fasta → {fasta_path}")
    return payload


def run_proto_design(spec: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    """Run the real Proto binder program. Returns payload or None to allow fallback."""
    sys.path.insert(0, str(REPO_ROOT))
    from design.proto_binder import (
        ProtoNotInstalled,
        ProtoRunFailed,
        build_and_run_binder_program,
        should_attempt_proto,
    )

    if not should_attempt_proto():
        print(
            "Proto skipped (packages not installed and USE_PROTO unset). "
            "Install Proto + set USE_PROTO=1 to use the real binder program.",
            file=sys.stderr,
        )
        return None

    try:
        payload = build_and_run_binder_program(spec, out_dir)
        json_path, fasta_path = write_outputs(out_dir, payload)
        print(
            f"Proto binder program wrote {len(payload.get('designs') or [])} live designs "
            f"(engine=proto_language)."
        )
        print(f"  designs.json → {json_path}")
        print(f"  designs.fasta → {fasta_path}")
        return payload
    except ProtoNotInstalled as exc:
        print(f"Proto not installed: {exc}", file=sys.stderr)
        return None
    except ProtoRunFailed as exc:
        print(f"Proto run failed: {exc}", file=sys.stderr)
        return None


def run(spec_path: Path, out_dir: Path, live: bool = False) -> dict[str, Any]:
    spec = load_spec(spec_path)
    want_live = live_design_requested(live)

    if want_live:
        # 1) Real Proto first
        live_proto = run_proto_design(spec, out_dir)
        if live_proto is not None:
            return live_proto

        # 2) Interim local sequence_design
        try:
            return write_live_designs(spec, out_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"sequence_design live path failed ({exc}); continuing…", file=sys.stderr)

        return write_fixture_designs(
            out_dir,
            reason=(
                "Live Proto and sequence_design unavailable; wrote fixture designs with "
                "provenance=fixture — do not present these as live inventions."
            ),
        )

    # Non-live: try Proto only if explicitly available & requested, else fixtures
    if proto_available() and os.environ.get("USE_PROTO", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        live_proto = run_proto_design(spec, out_dir)
        if live_proto is not None:
            return live_proto

    return write_fixture_designs(out_dir)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="iDoctor Design KRAS G12C binder loop (Proto → sequence_design → fixture)."
    )
    p.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help=f"Path to spec.json (default: {DEFAULT_SPEC})",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory for designs.json + designs.fasta (default: {DEFAULT_OUT_DIR})",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Attempt Proto, then local sequence_design (provenance=live). "
        "Also enabled by IDOCTOR_DESIGN_LIVE_DESIGN=1.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec_path = args.spec if args.spec.is_absolute() else (REPO_ROOT / args.spec)
    out_dir = args.out_dir if args.out_dir.is_absolute() else (REPO_ROOT / args.out_dir)

    if not spec_path.is_file():
        print(f"error: spec not found: {spec_path}", file=sys.stderr)
        return 1
    if not FIXTURE_DESIGNS_JSON.is_file():
        print(f"error: missing fixture {FIXTURE_DESIGNS_JSON}", file=sys.stderr)
        return 1

    run(spec_path, out_dir, live=args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
