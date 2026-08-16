"""PDB fetch helper (RCSB) with local cache.

Physics control is AutoDock Vina (CPU); no MD path in this product.
"""

from __future__ import annotations

from pathlib import Path

import requests

from backend.config import PDB_CACHE_DIR, RCSB_BASE_URL


def download_pdb(pdb_id: str) -> Path:
    pdb_id = pdb_id.upper()
    cached = PDB_CACHE_DIR / f"{pdb_id}.pdb"
    if cached.exists():
        return cached
    url = f"{RCSB_BASE_URL}/{pdb_id}.pdb"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    cached.write_text(resp.text)
    return cached
