"""Adapter: iDoctor Design run → Ryan's TherapeuticPlan.novel_designs[].

Ryan's engine (`idoctor-engine/idoctor/therapy.py`) is tolerant of this shape and
treats missing affinity as a prediction, not a measurement. Additive keys are
allowed; do not rename `proto_run_id`.

Usage:
  PYTHONPATH=. python -m backend.contracts.novel_designs --fixtures
  PYTHONPATH=. python -m backend.contracts.novel_designs --run-dir data/runs/<id>
  PYTHONPATH=. python -m backend.contracts.novel_designs --brief brief.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "spec" / "fixtures"

CAVEAT = "in-silico only; predicted, not measured"
NO_SURFACE = "no_protein_surface"
WRONG_TARGET = "wrong_target_protein"


def refuse_brief(brief: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a refusal payload if this loop cannot design for the brief.

    KRAS/missense → protein binder is in scope.
    Splice/nonsense → no protein surface (HBB IVS-I-1 class).
    HFE C282Y diagnosed, ferroportin designed → two proteins, not a PDB swap.
    """
    if not brief:
        return None
    gene = str(brief.get("gene") or "").upper()
    mechanism = str(brief.get("mechanism") or "").strip().lower()
    modality = str(brief.get("modality") or "").strip().lower()
    target = str(brief.get("target") or brief.get("design_target") or "")
    target_l = target.lower()

    if mechanism in {"splice", "splice_donor", "splice-donor", "nonsense"}:
        return {
            "reason": NO_SURFACE,
            "gene": gene or None,
            "mechanism": mechanism,
            "detail": (
                "A splice or nonsense variant does not produce a folded protein "
                "surface this binder loop can target."
            ),
        }
    if gene == "HBB" and mechanism in {"", "splice"} and "binder" in modality:
        return {
            "reason": NO_SURFACE,
            "gene": "HBB",
            "mechanism": mechanism or "splice",
            "detail": "HBB splice-donor: no protein surface to bind.",
        }
    if gene == "HFE" or "ferroportin" in target_l or "slc40a1" in target_l:
        return {
            "reason": WRONG_TARGET,
            "gene": gene or "HFE",
            "mechanism": mechanism or "missense",
            "detail": (
                "This loop binds the mutated protein (KRAS G12C). HFE C282Y "
                "is diagnosed on HFE; a hepcidin-mimetic would bind ferroportin. "
                "That is two proteins, not a spec.json swap."
            ),
        }
    return None


def _metrics(design: dict[str, Any]) -> dict[str, Any]:
    """Ryan's metrics object. Nulls stay null — never invent boltz2_affinity."""
    raw = design.get("raw_metrics") if isinstance(design.get("raw_metrics"), dict) else {}
    affinity = design.get("boltz2_affinity")
    if affinity is None:
        affinity = raw.get("boltz2_affinity")
    scores = design.get("constraint_scores") if isinstance(design.get("constraint_scores"), dict) else {}
    i_pae = scores.get("i_pae")
    return {
        "ipTM": design.get("iptm"),
        "pLDDT": design.get("plddt"),
        "boltz2_affinity": affinity,
        "i_pAE": i_pae,
    }


def _job_id(design: dict[str, Any], designs_doc: dict[str, Any], run_id: str | None) -> str:
    meta = designs_doc.get("meta") if isinstance(designs_doc.get("meta"), dict) else {}
    job = (
        design.get("tamarind_job")
        or meta.get("job_name")
        or meta.get("tamarind_job")
    )
    if job:
        return str(job)
    if run_id and design.get("id"):
        return f"idoctor-design:{run_id}:{design['id']}"
    return str(design.get("id") or "unknown")


def _target_label(spec: dict[str, Any] | None) -> str:
    target = (spec or {}).get("target") or {}
    gene = target.get("gene") or "KRAS"
    name = target.get("name") or "KRAS G12C"
    pdb_id = target.get("pdb_id") or "6OIM"
    pocket = spec.get("pocket_residues") if spec else None
    pocket_s = ",".join(str(p) for p in (pocket or [])) or "Switch II"
    return f"{name} ({gene}, {pdb_id}, {pocket_s})"


def _pick_designs(
    designs_doc: dict[str, Any],
    verdicts: dict[str, Any] | None,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Promote first, then hold. Never emit critic rejects as novel_designs."""
    by_id = {d["id"]: d for d in (designs_doc.get("designs") or []) if d.get("id")}
    items = [
        item
        for item in (verdicts or {}).get("items") or []
        if item.get("subject_kind") == "design"
    ]
    picked: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    seen: set[str] = set()
    for wanted in ("promote", "hold"):
        for item in items:
            if item.get("verdict") != wanted:
                continue
            design = by_id.get(item.get("subject_id"))
            if not design or design["id"] in seen:
                continue
            seen.add(design["id"])
            picked.append((design, item))
    if picked:
        return picked
    # No critic yet: pass through live BindCraft survivors only.
    live = [
        (d, None)
        for d in (designs_doc.get("designs") or [])
        if d.get("provenance") == "live" and d.get("sequence")
    ]
    return live


def design_to_novel(
    design: dict[str, Any],
    *,
    spec: dict[str, Any] | None,
    designs_doc: dict[str, Any],
    verdict: dict[str, Any] | None,
    experiment_md: str,
    run_id: str | None,
) -> dict[str, Any]:
    modality = design.get("molecule_type") or "miniprotein"
    meta = designs_doc.get("meta") if isinstance(designs_doc.get("meta"), dict) else {}
    generator = (
        design.get("generator")
        or meta.get("design_engine")
        or ("fixture" if design.get("provenance") == "fixture" else "unknown")
    )
    job = _job_id(design, designs_doc, run_id)
    remaining = (verdict or {}).get("remaining_risk") or ""
    caveat = CAVEAT
    if remaining:
        caveat = f"{CAVEAT}. {remaining}"
    if design.get("provenance") == "fixture":
        caveat = f"{CAVEAT}. Fixture sequence — do not present as a live invention."

    payload = {
        "name": design.get("id"),
        "modality": modality,
        "target": _target_label(spec),
        "sequence": design.get("sequence"),
        "metrics": _metrics(design),
        "proto_run_id": job,
        "tamarind_job_id": job if "tamarind" in str(generator) or design.get("tamarind_job") else None,
        "generator": generator,
        "wetlab_protocol": "experiment.md" if experiment_md.strip() else None,
        "caveat": caveat,
        "verdict": (verdict or {}).get("verdict"),
        "provenance": design.get("provenance"),
    }
    if payload["tamarind_job_id"] is None:
        payload.pop("tamarind_job_id")
    return payload


def build_payload(
    *,
    spec: dict[str, Any] | None,
    designs_doc: dict[str, Any] | None,
    verdicts: dict[str, Any] | None = None,
    experiment_md: str = "",
    run_id: str | None = None,
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refused = refuse_brief(brief)
    if refused:
        return {
            "schema_version": "1.0",
            "case_id": (brief or {}).get("case_id"),
            "source": "idoctor-design",
            "generator": "tamarind:bindcraft",
            "refused": [refused],
            "novel_designs": [],
        }

    designs_doc = designs_doc or {"designs": []}
    rows = _pick_designs(designs_doc, verdicts)
    novel = [
        design_to_novel(
            design,
            spec=spec,
            designs_doc=designs_doc,
            verdict=verdict,
            experiment_md=experiment_md,
            run_id=run_id,
        )
        for design, verdict in rows
    ]
    return {
        "schema_version": "1.0",
        "case_id": (brief or {}).get("case_id"),
        "source": "idoctor-design",
        "generator": (designs_doc.get("meta") or {}).get("design_engine") or "unknown",
        "refused": [],
        "novel_designs": novel,
        "therapy": {"novel_designs": novel},
    }


def export_from_run(run_dir: Path, brief: dict[str, Any] | None = None) -> dict[str, Any]:
    def _json(name: str) -> dict[str, Any] | None:
        path = run_dir / name
        if not path.is_file():
            return None
        return json.loads(path.read_text())

    experiment = ""
    exp = run_dir / "experiment.md"
    if exp.is_file():
        experiment = exp.read_text()
    provenance = _json("provenance.json") or {}
    payload = build_payload(
        spec=_json("spec.json"),
        designs_doc=_json("designs.json"),
        verdicts=_json("verdicts.json"),
        experiment_md=experiment,
        run_id=str(provenance.get("run_id") or run_dir.name),
        brief=brief,
    )
    out = run_dir / "novel_designs.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def export_from_fixtures(brief: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = json.loads((FIXTURES / "spec.example.json").read_text())
    designs = json.loads((FIXTURES / "designs.example.json").read_text())
    verdicts = json.loads((FIXTURES / "verdicts.example.json").read_text())
    experiment = (FIXTURES / "experiment.example.md").read_text()
    return build_payload(
        spec=spec,
        designs_doc=designs,
        verdicts=verdicts,
        experiment_md=experiment,
        run_id="fixture",
        brief=brief,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export TherapeuticPlan.novel_designs from an iDoctor Design run.")
    parser.add_argument("--run-dir", type=Path, help="data/runs/<id> folder")
    parser.add_argument("--fixtures", action="store_true", help="Use spec/fixtures (no live BindCraft)")
    parser.add_argument("--brief", type=Path, help="Optional design-brief JSON from Ryan bridge.py")
    parser.add_argument("--out", type=Path, help="Write JSON here (default: stdout, or run-dir/novel_designs.json)")
    args = parser.parse_args(argv)

    brief = None
    if args.brief:
        brief = json.loads(args.brief.read_text())

    if args.run_dir:
        payload = export_from_run(args.run_dir, brief=brief)
        if args.out:
            args.out.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 0
    if args.fixtures:
        payload = export_from_fixtures(brief=brief)
        if args.out:
            args.out.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 0
    parser.error("pass --run-dir or --fixtures")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
