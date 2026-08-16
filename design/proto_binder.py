"""KRAS G12C Proto binder program (RFdiffusion3 + ProteinMPNN + ipTM).

Follows the official Proto binder-design pattern:
https://proto.evodesign.org/docs/language/guides/examples/binder-design

Requires:
  pip install git+https://github.com/evo-design/proto-tools.git
  git clone https://github.com/evo-design/proto-language.git && pip install -e ./proto-language
  pip install modal && modal setup   # GPU via Modal credits at re:AGENT

When Proto/Modal is unavailable, callers must fall back to sequence_design / fixtures
and must not claim Modal Proto succeeded.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDB = REPO_ROOT / "data" / "pdb_cache" / "6OIM.pdb"


class ProtoNotInstalled(RuntimeError):
    """proto_language / proto_tools missing."""


class ProtoRunFailed(RuntimeError):
    """Proto program started but failed (Modal, GPU, weights, etc.)."""


def proto_packages_available() -> bool:
    try:
        import proto_language  # noqa: F401
        import proto_tools  # noqa: F401

        return True
    except ImportError:
        return False


def use_proto_requested() -> bool:
    return os.environ.get("USE_PROTO", "").strip().lower() in {"1", "true", "yes", "on"}


def should_attempt_proto() -> bool:
    """Attempt Proto when packages are importable, or when USE_PROTO=1 (then fail loudly)."""
    if proto_packages_available():
        return True
    return use_proto_requested()


def _pocket_to_hotspots(pocket_residues: list[Any], chain: str = "A") -> list[str]:
    """Map iDoctor Design pocket labels (Cys12, Tyr96) → Proto hotspots (A12, A96)."""
    hotspots: list[str] = []
    for raw in pocket_residues or []:
        text = str(raw).strip()
        m = re.search(r"(\d+)", text)
        if not m:
            continue
        hotspots.append(f"{chain}{m.group(1)}")
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for h in hotspots:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _resolve_pdb(spec: dict[str, Any]) -> Path:
    target = spec.get("target") or {}
    pdb_id = str(target.get("pdb_id") or os.environ.get("DEFAULT_PDB_ID") or "6OIM").upper()
    cached = REPO_ROOT / "data" / "pdb_cache" / f"{pdb_id}.pdb"
    if cached.is_file():
        return cached
    if DEFAULT_PDB.is_file():
        return DEFAULT_PDB
    raise ProtoRunFailed(f"No target PDB found for {pdb_id} under data/pdb_cache/")


def build_and_run_binder_program(
    spec: dict[str, Any],
    out_dir: Path,
    *,
    binder_length: int | None = None,
    num_samples: int | None = None,
    num_results: int | None = None,
    device: str | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Run the Proto binder program; return iDoctor Design designs.json payload.

    Raises ProtoNotInstalled or ProtoRunFailed — never silently returns fixtures.
    """
    if not proto_packages_available():
        raise ProtoNotInstalled(
            "Proto packages not installed. "
            "Install proto-tools + proto-language (see spec/runbooks/proto.md), "
            "set USE_PROTO=1 and Modal tokens, then re-run live."
        )

    # Imports only after availability check so fixture path stays light.
    from proto_tools import ProteinMPNNSampleConfig, RFdiffusion3Config
    from proto_tools.entities.structures import Structure

    from proto_language import StructureBasedConstraintConfig, structure_iptm_constraint
    from proto_language.core import Constraint, Construct, Program, Segment
    from proto_language.generator import (
        RFdiffusionMPNNBinderGenerator,
        RFdiffusionMPNNBinderGeneratorConfig,
    )
    from proto_language.optimizer import RejectionSamplingOptimizer, RejectionSamplingOptimizerConfig

    binder_length = binder_length or int(os.environ.get("PROTO_BINDER_LENGTH", "48"))
    num_samples = num_samples or int(os.environ.get("PROTO_NUM_SAMPLES", "4"))
    num_results = num_results or int(os.environ.get("PROTO_NUM_RESULTS", "4"))
    device = device or os.environ.get("PROTO_DEVICE", "cuda")

    pdb_path = _resolve_pdb(spec)
    chain = "A"
    hotspots = _pocket_to_hotspots(list(spec.get("pocket_residues") or []), chain=chain)
    mutations = [
        m.get("id") for m in (spec.get("mutations") or []) if isinstance(m, dict) and m.get("id")
    ]

    print(
        f"proto_binder: target PDB={pdb_path.name} chain={chain} "
        f"hotspots={hotspots} mutations={mutations} "
        f"binder_length={binder_length} samples={num_samples} device={device}",
        file=sys.stderr,
    )

    try:
        target_structure = Structure(structure=pdb_path.read_text())
        target_sequence = target_structure.get_chain_sequence(chain, remove_non_standard=True)

        binder = Segment(length=binder_length, sequence_type="protein", label="binder")
        target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
        construct = Construct([binder, target])

        generator = RFdiffusionMPNNBinderGenerator(
            RFdiffusionMPNNBinderGeneratorConfig(
                target_structure=target_structure,
                target_chains=[chain],
                hotspots=hotspots or None,
                inverse_folding="proteinmpnn",
                rfdiffusion3_config=RFdiffusion3Config(device=device),
                proteinmpnn_config=ProteinMPNNSampleConfig(
                    num_sequences_per_structure=1,
                    device=device,
                ),
            )
        )
        generator.assign(binder)

        iptm_constraint = Constraint(
            inputs=[binder, target],
            function=structure_iptm_constraint,
            function_config=StructureBasedConstraintConfig(structure_tool="boltz2"),
            label="iptm",
            weight=1.0,
        )

        optimizer = RejectionSamplingOptimizer(
            constructs=[construct],
            generators=[generator],
            constraints=[iptm_constraint],
            config=RejectionSamplingOptimizerConfig(
                num_samples=num_samples,
                num_results=num_results,
            ),
        )

        program = Program(optimizers=[optimizer], num_results=num_results, seed=seed)
        program.run()
    except ProtoNotInstalled:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProtoRunFailed(
            f"Proto binder program failed ({type(exc).__name__}: {exc}). "
            "Check Modal credits, USE_PROTO, and GPU/device. "
            "Falling back must use sequence_design/fixtures — do not claim Proto succeeded."
        ) from exc

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    designs: list[dict[str, Any]] = []

    for rank, result in enumerate(binder.result_sequences or []):
        seq = getattr(result, "sequence", None) or ""
        if not seq:
            continue
        design_id = f"proto_{rank + 1:03d}"
        pdb_out = None
        structure = getattr(result, "structure", None)
        if structure is not None:
            try:
                pdb_name = f"{design_id}_complex.pdb"
                structure.write_pdb(out_dir / pdb_name)
                pdb_out = str(out_dir / pdb_name)
            except Exception as exc:  # noqa: BLE001
                print(f"proto_binder: could not write PDB for {design_id}: {exc}", file=sys.stderr)

        # Proto iptm constraint returns 1 - iptm as energy; recover approximate iptm if present
        energy = getattr(result, "energy", None)
        iptm_val = None
        if isinstance(energy, (int, float)):
            iptm_val = round(max(0.0, min(1.0, 1.0 - float(energy))), 3)

        designs.append(
            {
                "id": design_id,
                "sequence": seq,
                "length": len(seq),
                "molecule_type": "miniprotein" if len(seq) >= 40 else "peptide",
                "constraint_scores": {
                    "spec_match": 0.0,
                    "fold_plausibility": float(energy) if isinstance(energy, (int, float)) else 0.5,
                    "proto_iptm_energy": float(energy) if isinstance(energy, (int, float)) else None,
                },
                "plddt": None,
                "iptm": iptm_val,
                "pdb_path": pdb_out,
                "novelty": {"identity": None, "method": "proto_rfdiffusion_mpnn"},
                "provenance": "live",
                "generator": "proto_language.rfdiffusion_mpnn_binder",
                "hotspots": hotspots,
                "resistance_mutations": mutations,
            }
        )

    if not designs:
        raise ProtoRunFailed(
            "Proto program finished but returned zero binder sequences. "
            "Do not claim Proto designs; use sequence_design/fixtures."
        )

    payload = {
        "schema_version": "1.0",
        "score_direction": "lower_is_better",
        "designs": designs,
        "meta": {
            "engine": "proto_language",
            "generator": "rfdiffusion-mpnn-binder",
            "target_pdb": pdb_path.name,
            "hotspots": hotspots,
            "mutations": mutations,
        },
    }
    return payload
