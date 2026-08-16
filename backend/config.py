import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / "backend" / ".env")
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
PDB_CACHE_DIR = DATA_DIR / "pdb_cache"
_SPEC_FIXTURES_DIR = BASE_DIR / "spec" / "fixtures"
_FRONTEND_FIXTURES_DIR = BASE_DIR / "frontend" / "public" / "fixtures"
FIXTURES_DIR = (
    _SPEC_FIXTURES_DIR if _SPEC_FIXTURES_DIR.is_dir() else _FRONTEND_FIXTURES_DIR
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

PAPERCLIP_API_KEY = os.getenv("PAPERCLIP_API_KEY", "")
PAPERCLIP_BASE_URL = os.getenv("PAPERCLIP_BASE_URL", "")
PAPERCLIP_MCP_URL = os.getenv("PAPERCLIP_MCP_URL", "https://paperclip.gxl.ai/mcp").rstrip("/")
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

# Dev loop switch. With IDOCTOR_FAST=1 a live run skips expensive/network-bound
# verification such as Tamarind folds and complexes, RCSB novelty, literature
# search, and critic prose polishing. Every skip is recorded in provenance and
# prevents promotion, so a fast run is honest about being degraded.
FAST_DEV = os.getenv("IDOCTOR_FAST", "0").strip().lower() in {"1", "true", "yes", "on"}


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _positive_float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


# Loop-engineering budgets. The initial design is iteration 1, so three
# iterations means at most two critic-requested redesigns.
MAX_DESIGN_ITERATIONS = _positive_int_env("IDOCTOR_MAX_DESIGN_ITERATIONS", 3)
MAX_NO_IMPROVEMENT_ROUNDS = _positive_int_env(
    "IDOCTOR_MAX_NO_IMPROVEMENT_ROUNDS", 2
)
DEFAULT_MIN_IPTM = _positive_float_env("IDOCTOR_MIN_IPTM", 0.75)
MAX_COMPLEX_DESIGNS = _positive_int_env("IDOCTOR_MAX_COMPLEX_DESIGNS", 1)
MAX_COMPLEX_MUTANTS = _positive_int_env("IDOCTOR_MAX_COMPLEX_MUTANTS", 2)
COMPLEX_EVALUATION_TIMEOUT = _positive_int_env(
    "IDOCTOR_COMPLEX_EVALUATION_TIMEOUT", 1800
)

KNOWN_TARGETS = {
    "6OIM": {
        "name": "KRAS G12C (Lung Cancer)",
        # Sotorasib (AMG 510) is deposited as MOV in 6OIM.
        "ligand_id": "MOV",
        "reference_drug_id": "sotorasib",
        "reference_drug_name": "Sotorasib (Lumakras)",
        "binding_site_residues": ["Cys12", "His95", "Tyr96", "Asp69"],
        # Centroid of the 41 MOV (sotorasib) atoms in 6OIM — the Switch II pocket
        # as actually occupied by the drug. Recompute if the target PDB changes.
        "binding_site_center": [1.87, -8.26, -1.36],
        # Ligand extent is 13.9 x 11.7 x 5.9 A; box adds room for rotatable bonds.
        "binding_site_box": [22.0, 20.0, 16.0],
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
