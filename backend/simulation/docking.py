"""AutoDock Vina molecular docking — generates 3D poses for compounds in binding pocket."""

import json
import time
from pathlib import Path
from backend.config import DATA_DIR

DOCKED_DIR = DATA_DIR / "docked"
DOCKED_DIR.mkdir(parents=True, exist_ok=True)

_receptor_pdbqt_cache: dict[str, str] = {}


def _prepare_receptor_pdbqt(pdb_path: str) -> str:
    """Clean PDB with PDBFixer, convert to PDBQT with Open Babel. Cached per protein."""
    if pdb_path in _receptor_pdbqt_cache:
        return _receptor_pdbqt_cache[pdb_path]

    import subprocess
    import tempfile
    import io
    from pdbfixer import PDBFixer
    import openmm.app as app

    # Clean with PDBFixer
    fixer = PDBFixer(filename=pdb_path)
    fixer.removeHeterogens(False)
    fixer.missingResidues = {}
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(pH=7.0)

    # Write cleaned PDB
    clean_pdb = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False, mode="w")
    app.PDBFile.writeFile(fixer.topology, fixer.positions, clean_pdb)
    clean_pdb.close()

    # Convert to PDBQT with Open Babel
    pdbqt_path = clean_pdb.name.replace(".pdb", ".pdbqt")
    subprocess.run(
        ["obabel", clean_pdb.name, "-O", pdbqt_path, "-xr", "-xp"],
        capture_output=True, check=True,
    )

    _receptor_pdbqt_cache[pdb_path] = pdbqt_path
    return pdbqt_path


def dock_compound(
    protein_pdb_path: str,
    compound_smiles: str,
    compound_id: str,
    center: list[float],
    box_size: list[float] | None = None,
) -> dict:
    """
    Dock a compound into the protein binding pocket using AutoDock Vina.
    Returns the docked pose as PDB-format string + binding energy.
    """
    if box_size is None:
        box_size = [20.0, 20.0, 20.0]

    # Check for cached result
    cache_path = DOCKED_DIR / f"{compound_id}_docked.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    try:
        return _run_vina(protein_pdb_path, compound_smiles, compound_id, center, box_size, cache_path)
    except ImportError:
        return {"compound_id": compound_id, "error": "AutoDock Vina not installed", "pose_pdb": None}
    except Exception as e:
        return {"compound_id": compound_id, "error": str(e), "pose_pdb": None}


def _run_vina(
    protein_pdb_path: str,
    smiles: str,
    compound_id: str,
    center: list[float],
    box_size: list[float],
    cache_path: Path,
) -> dict:
    from vina import Vina
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    from rdkit import Chem
    from rdkit.Chem import AllChem
    import tempfile
    import os

    start = time.perf_counter()

    # 1. Prepare ligand from SMILES
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles}")

    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    AllChem.MMFFOptimizeMolecule(mol)

    preparator = MoleculePreparation()
    mol_setups = preparator.prepare(mol)
    pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
    if not is_ok:
        raise ValueError(f"PDBQT prep failed: {error_msg}")

    # 2. Get cleaned receptor PDBQT (PDBFixer + Open Babel, cached)
    receptor_pdbqt = _prepare_receptor_pdbqt(protein_pdb_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        ligand_pdbqt = os.path.join(tmpdir, "ligand.pdbqt")
        with open(ligand_pdbqt, "w") as f:
            f.write(pdbqt_string)

        # 3. Run Vina
        v = Vina(sf_name="vina")
        v.set_receptor(receptor_pdbqt)
        v.set_ligand_from_file(ligand_pdbqt)
        v.compute_vina_maps(center=center, box_size=box_size)

        v.dock(exhaustiveness=8, n_poses=1)
        energy = v.energies(n_poses=1)[0][0]  # kcal/mol

        # 4. Get docked pose as PDB
        output_pdbqt = os.path.join(tmpdir, "docked.pdbqt")
        v.write_poses(output_pdbqt, n_poses=1, overwrite=True)

        # Convert PDBQT to simple PDB (strip extra columns)
        pose_lines = []
        with open(output_pdbqt) as f:
            for line in f:
                if line.startswith("ATOM") or line.startswith("HETATM"):
                    pose_lines.append(line[:66].rstrip())
        pose_pdb = "\n".join(pose_lines)

    elapsed = time.perf_counter() - start

    result = {
        "compound_id": compound_id,
        "vina_score_kcal_mol": round(energy, 2),
        "pose_pdb": pose_pdb,
        "docking_time_seconds": round(elapsed, 2),
        "center": center,
        "box_size": box_size,
    }

    # Cache
    cache_path.write_text(json.dumps(result, indent=2))
    return result


def dock_all_compounds(
    protein_pdb_path: str,
    compounds: list[dict],
    center: list[float],
) -> list[dict]:
    """Dock all compounds and return results."""
    results = []
    for compound in compounds:
        result = dock_compound(
            protein_pdb_path,
            compound["smiles"],
            compound["id"],
            center,
        )
        results.append(result)
    return results
