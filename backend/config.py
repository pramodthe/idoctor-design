import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / "backend" / ".env")
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
PDB_CACHE_DIR = DATA_DIR / "pdb_cache"
FIXTURES_DIR = BASE_DIR / "spec" / "fixtures"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

PAPERCLIP_API_KEY = os.getenv("PAPERCLIP_API_KEY", "")
PAPERCLIP_BASE_URL = os.getenv("PAPERCLIP_BASE_URL", "")
TAMARIND_API_KEY = os.getenv("TAMARIND_API_KEY", "")
MODAL_TOKEN_ID = os.getenv("MODAL_TOKEN_ID", "")
MODAL_TOKEN_SECRET = os.getenv("MODAL_TOKEN_SECRET", "")

USE_PROTO = os.getenv("USE_PROTO", "0").strip().lower() in {"1", "true", "yes", "on"}
PROTO_BINDER_LENGTH = int(os.getenv("PROTO_BINDER_LENGTH", "48"))
PROTO_NUM_SAMPLES = int(os.getenv("PROTO_NUM_SAMPLES", "4"))
PROTO_NUM_RESULTS = int(os.getenv("PROTO_NUM_RESULTS", "4"))
PROTO_DEVICE = os.getenv("PROTO_DEVICE", "cuda")


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        val = os.getenv(name)
        if val is not None and str(val).strip() != "":
            return val
    return default


def env_flag(*names: str) -> bool:
    for name in names:
        if os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


IDOCTOR_DESIGN_DEFAULT_MODE = _first_env(
    "IDOCTOR_DESIGN_DEFAULT_MODE", default="fixture"
)
DEFAULT_PDB_ID = os.getenv("DEFAULT_PDB_ID", "6OIM")


def live_design_requested() -> bool:
    return env_flag("IDOCTOR_DESIGN_LIVE_DESIGN")

SCORING_METHOD = os.getenv("SCORING_METHOD", "vina")
SCORING_VERSION = "vina_v1"

RCSB_BASE_URL = "https://files.rcsb.org/download"

KNOWN_TARGETS = {
    "6OIM": {
        "name": "KRAS G12C (Lung Cancer)",
        "ligand_id": "ARS",
        "reference_drug_id": "sotorasib",
        "reference_drug_name": "Sotorasib (Lumakras)",
        "binding_site_residues": ["Cys12", "His95", "Tyr96", "Asp69"],
        "binding_site_center": [-2.5, -1.8, 12.3],
        "pocket_volume_A3": 530.0,
        "resolution_angstroms": 1.65,
        "biological_context": (
            "KRAS is the most frequently mutated oncogene in human cancer. The G12C mutation "
            "locks KRAS in its active GTP-bound state, driving uncontrolled cell growth."
        ),
        "therapeutic_relevance": (
            "Sotorasib (Lumakras) targets KRAS G12C via the Switch II pocket, but resistance "
            "mutations such as Y96D cause clinical relapse — the problem iDoctor Design addresses."
        ),
    },
}

for d in [DATA_DIR, RUNS_DIR, PRECOMPUTED_DIR, PDB_CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)
