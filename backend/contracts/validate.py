"""Light contract validation for iDoctor Design JSON artifacts."""

from __future__ import annotations

from typing import Any


def _require(obj: dict, keys: list[str], label: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f"{label} missing required key(s): {', '.join(missing)}")


def validate_spec(data: dict[str, Any]) -> dict[str, Any]:
    _require(
        data,
        [
            "schema_version",
            "target",
            "hypothesis",
            "mutations",
            "failed_small_molecules",
            "structures",
            "pocket_residues",
            "success_bars",
            "provenance",
        ],
        "spec.json",
    )
    if not isinstance(data["target"], dict):
        raise ValueError("spec.json target must be an object")
    _require(
        data["target"],
        ["name", "gene", "pdb_id", "uniprot_id", "clinical_hook"],
        "spec.json target",
    )
    if not isinstance(data["mutations"], list) or len(data["mutations"]) < 1:
        raise ValueError("spec.json mutations must be a non-empty array")
    for i, mut in enumerate(data["mutations"]):
        _require(mut, ["id", "effect_on_sotorasib", "notes", "sources"], f"spec.json mutations[{i}]")
    _require(
        data["success_bars"],
        ["max_pdb_identity", "min_plddt", "require_mutant_score"],
        "spec.json success_bars",
    )
    return data


def validate_designs(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, ["schema_version", "designs"], "designs.json")
    if not isinstance(data["designs"], list):
        raise ValueError("designs.json designs must be an array")
    for i, design in enumerate(data["designs"]):
        _require(
            design,
            [
                "id",
                "sequence",
                "length",
                "molecule_type",
                "constraint_scores",
                "plddt",
                "iptm",
                "pdb_path",
                "novelty",
                "provenance",
            ],
            f"designs.json designs[{i}]",
        )
    return data


def validate_smallmol(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, ["schema_version", "compounds"], "smallmol.json")
    if not isinstance(data["compounds"], list):
        raise ValueError("smallmol.json compounds must be an array")
    for i, c in enumerate(data["compounds"]):
        _require(
            c,
            [
                "id",
                "name",
                "smiles",
                "known_ki_nm",
                "vina_wt",
                "vina_mutants",
                "pains_flags",
                "lipinski_violations",
            ],
            f"smallmol.json compounds[{i}]",
        )
    return data


def validate_eval(data: dict[str, Any]) -> dict[str, Any]:
    _require(
        data,
        [
            "schema_version",
            "smallmol_spearman_rho",
            "smallmol_n",
            "smallmol_note",
            "disagreements",
            "design_deltas",
        ],
        "eval.json",
    )
    return data


def validate_verdicts(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, ["schema_version", "hypothesis", "items"], "verdicts.json")
    allowed = {"promote", "hold", "reject"}
    reason_codes = {
        "wt_only_signal",
        "too_similar_to_pdb",
        "low_structure_confidence",
        "contradicts_literature",
        "promiscuous_or_pains",
        "weak_or_missing_metric",
        "passes_spec",
        "other",
    }
    if not isinstance(data["items"], list):
        raise ValueError("verdicts.json items must be an array")
    for i, item in enumerate(data["items"]):
        _require(
            item,
            [
                "subject_kind",
                "subject_id",
                "verdict",
                "reasons",
                "summary",
                "evidence_ids",
                "metrics_used",
                "remaining_risk",
            ],
            f"verdicts.json items[{i}]",
        )
        if item["verdict"] not in allowed:
            raise ValueError(f"verdicts.json items[{i}] invalid verdict: {item['verdict']}")
        if item["subject_kind"] not in {"design", "smallmol"}:
            raise ValueError(f"verdicts.json items[{i}] invalid subject_kind")
        for code in item.get("reasons") or []:
            if code not in reason_codes:
                raise ValueError(f"verdicts.json items[{i}] unknown reason code: {code}")
    return data


def validate_provenance(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, ["run_id", "mode", "nodes", "created_at"], "provenance.json")
    if data["mode"] not in {"live", "replay", "fixture"}:
        raise ValueError(f"provenance.json invalid mode: {data['mode']}")
    node_vals = {"live", "cached", "fixture", "skipped"}
    for name, val in (data.get("nodes") or {}).items():
        if val not in node_vals:
            raise ValueError(f"provenance.json nodes.{name} invalid value: {val}")
    return data
