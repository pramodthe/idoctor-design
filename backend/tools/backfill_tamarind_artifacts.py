"""Backfill rich Tamarind artifacts for a completed iDoctor run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.config import RUNS_DIR
from backend.tools.tamarind import _complex_metrics_from_zip


def backfill_run(run_id: str) -> dict[str, list[dict[str, str]]]:
    run_dir = RUNS_DIR / run_id
    designs_path = run_dir / "designs.json"
    if not designs_path.is_file():
        raise FileNotFoundError(f"designs.json not found for {run_id}")

    designs_doc = json.loads(designs_path.read_text())
    manifest: dict[str, list[dict[str, str]]] = {}
    for design in designs_doc.get("designs") or []:
        design_id = str(design.get("id") or "design")
        for variant, current in (design.get("complex_metrics") or {}).items():
            job_name = str((current or {}).get("job_name") or "")
            if not job_name:
                continue
            refreshed = _complex_metrics_from_zip(
                job_name,
                str(run_dir / "structures" / "complexes"),
                artifact_label=f"{design_id}-{variant}-complex",
            )
            current.update(refreshed)
            manifest[f"{design_id}:{variant}"] = refreshed.get("artifacts") or []

    designs_path.write_text(json.dumps(designs_doc, indent=2) + "\n")
    manifest_path = run_dir / "tamarind_artifacts.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    manifest = backfill_run(args.run_id)
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "variants": len(manifest),
                "artifacts": sum(len(rows) for rows in manifest.values()),
            }
        )
    )


if __name__ == "__main__":
    main()
