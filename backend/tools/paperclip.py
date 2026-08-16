"""Paperclip literature search — CLI/SDK fallback; live evidence prefers MCP.

Paperclip (https://paperclip.gxl.ai/docs) is used via:
  - MCP: https://paperclip.gxl.ai/mcp (X-API-Key) bound as LangGraph tools
    in backend/tools/paperclip_mcp.py — this is the live evidence path
  - CLI: `paperclip search …` with PAPERCLIP_API_KEY (fallback)
  - Optional PAPERCLIP_BASE_URL for non-default server (local/dev)

There is no first-class public “PAPERCLIP_API_URL/search” REST surface we own —
do not invent one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Any

from backend.config import PAPERCLIP_API_KEY, PAPERCLIP_BASE_URL
from backend.tools import literature



class PaperclipUnavailable(RuntimeError):
    """Raised when Paperclip cannot be reached or is not configured."""


def is_configured() -> bool:
    return bool(PAPERCLIP_API_KEY)


def _paperclip_bin() -> str | None:
    """Resolve paperclip binary (PATH or common installer locations)."""
    found = shutil.which("paperclip")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "paperclip",
        Path.home() / ".paperclip" / "bin" / "paperclip",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _cli_available() -> bool:
    return _paperclip_bin() is not None


def _parse_paperclip_cli_text(out: str, query: str) -> dict[str, Any]:
    """Parse human-readable `paperclip search` stdout into a structured payload."""
    results: list[dict[str, Any]] = []
    search_id = None
    m_sid = re.search(r"\[(s_[a-f0-9]+)\]", out)
    if m_sid:
        search_id = m_sid.group(1)

    # Blocks like:
    #   1. Title...
    #      Authors...
    #      PMC9170150 · Journal · 2022-04-26
    #      https://...
    #      "snippet"
    block_re = re.compile(
        r"^\s*(\d+)\.\s+(.*?)\n"
        r"\s+([^\n]+)\n"
        r"\s+((?:PMC|PMID|NCT)[^\n·]*?)\s*·\s*([^\n]+?)\s*·\s*([^\n]+)\n"
        r"(?:\s+(https?://[^\n]+)\n)?"
        r"(?:\s+\"([^\"]*)\")?",
        re.MULTILINE,
    )
    for m in block_re.finditer(out):
        doc_id = m.group(4).strip()
        results.append(
            {
                "rank": int(m.group(1)),
                "title": re.sub(r"\s+", " ", m.group(2)).strip(),
                "authors": m.group(3).strip(),
                "id": doc_id,
                "venue": m.group(5).strip(),
                "date": m.group(6).strip(),
                "url": (m.group(7) or "").strip() or None,
                "snippet": (m.group(8) or "").strip() or None,
            }
        )

    # Fallback: scoop any PMC/PMID/NCT tokens if block parse missed
    if not results:
        for doc_id in re.findall(r"\b(PMC\d+|PMID:?\s*\d+|NCT\d+)\b", out, flags=re.I):
            results.append({"id": doc_id.replace(" ", ""), "title": None})

    return {
        "query": query,
        "search_id": search_id,
        "source": "paperclip_cli",
        "n_results": len(results),
        "results": results,
        "raw_text": out if not results else None,
    }


def search(query: str, **kwargs: Any) -> dict[str, Any] | None:
    """Live Paperclip search via official CLI.

    Requires `paperclip` on PATH and either PAPERCLIP_API_KEY or prior `paperclip login`.
    """
    if not is_configured() and not _cli_available():
        raise PaperclipUnavailable(
            "Paperclip unavailable: PAPERCLIP_API_KEY not set and CLI not found. "
            "Install from https://paperclip.gxl.ai/docs or use literature fallback."
        )

    paperclip_bin = _paperclip_bin()
    if not paperclip_bin:
        raise PaperclipUnavailable(
            "Paperclip CLI not installed. "
            "Run: curl -fsSL https://paperclip.gxl.ai/install.sh | bash "
            "Then set PAPERCLIP_API_KEY. (There is no custom REST API URL to fill in.)"
        )

    timeout = kwargs.get("timeout", 90)
    # Current CLI requires -s/--source (pmc, trials/us, …).
    sources = kwargs.get("sources") or os.environ.get(
        "PAPERCLIP_SOURCES", "pmc,biorxiv,medrxiv,trials/us"
    )
    limit = int(kwargs.get("limit") or os.environ.get("PAPERCLIP_SEARCH_LIMIT", "20"))
    # The installed launcher is `#!/usr/bin/env python3`, which resolves to whatever
    # python3 is first on PATH — on macOS that is usually a Homebrew interpreter
    # without `requests`, and the CLI dies with ModuleNotFoundError before it ever
    # authenticates. Running it under our own interpreter, which has requests, fixes
    # it without touching the install or needing --break-system-packages.
    cmd = [sys.executable, paperclip_bin]
    if PAPERCLIP_API_KEY:
        cmd.extend(["--api-key", PAPERCLIP_API_KEY])
    cmd.extend(["search", "-s", str(sources), "-n", str(limit), query])

    env = os.environ.copy()
    # Ensure installer path stays visible to any child tools.
    local_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
    if PAPERCLIP_API_KEY:
        env["PAPERCLIP_API_KEY"] = PAPERCLIP_API_KEY
    if PAPERCLIP_BASE_URL:
        env["PAPERCLIP_BASE_URL"] = PAPERCLIP_BASE_URL.rstrip("/")

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except Exception as e:
        raise PaperclipUnavailable(f"Paperclip CLI failed to start: {e}") from e

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "")[:400]
        raise PaperclipUnavailable(f"Paperclip CLI failed (rc={completed.returncode}): {err}")

    out = (completed.stdout or "").strip()
    if not out:
        raise PaperclipUnavailable("Paperclip CLI returned empty stdout.")

    # The CLI has been observed printing a failure message and still exiting 0, so a
    # zero return code is not proof of a search. A real one always emits an
    # `s_<hex>` handle; without it, treat this as unavailable and fall back rather
    # than parsing an error page into an empty, confident-looking result.
    if not re.search(r"\bs_[A-Za-z0-9]+\b", out) and not out.lstrip().startswith("{"):
        raise PaperclipUnavailable(
            f"Paperclip CLI exited 0 with no search handle: {out[:200]}"
        )

    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict):
            parsed.setdefault("query", query)
            parsed.setdefault("source", "paperclip_cli_json")
            return parsed
    except json.JSONDecodeError:
        pass
    return _parse_paperclip_cli_text(out, query)


def fetch_spec_candidate(query: str = "KRAS G12C sotorasib resistance") -> dict[str, Any] | None:
    """Return a raw Paperclip payload if live, else None."""
    try:
        return search(query)
    except PaperclipUnavailable:
        return None


FROZEN_MUTATIONS = ("Y96D", "H95D", "R68S", "Y96C")
_LOSS_KW = ("loss", "abolished", "resistant", "resistance", "escape", "abrogate")
_REDUCED_KW = ("reduced", "attenuated", "decreased", "weaker", "partial")


def compact_search_hits(payload: dict[str, Any] | None, *, limit: int = 12) -> list[dict[str, Any]]:
    """Flatten Paperclip CLI / JSON search payloads into {id, title, snippet} hits."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results") or payload.get("hits") or payload.get("documents") or []
    out: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            doc_id = row.get("id") or row.get("pmid") or row.get("pmcid") or row.get("nctId")
            if not doc_id:
                continue
            snippet = row.get("snippet") or row.get("abstractText") or row.get("abstract") or ""
            out.append(
                {
                    "id": str(doc_id).strip(),
                    "title": (row.get("title") or "")[:300],
                    "snippet": str(snippet)[:400],
                    "url": row.get("url"),
                    "source": payload.get("source") or "paperclip",
                }
            )
    return out


def compact_epmc_hits(papers: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in papers[:limit]:
        if not isinstance(row, dict):
            continue
        doc_id = row.get("pmid") or row.get("pmcid") or row.get("id")
        if not doc_id:
            continue
        snippet = row.get("abstractText") or ""
        out.append(
            {
                "id": str(doc_id).strip(),
                "title": (row.get("title") or "")[:300],
                "snippet": str(snippet)[:400],
                "source": "europepmc",
            }
        )
    return out


def allowlist_from_hits(hits: list[dict[str, Any]]) -> set[str]:
    """Document IDs the critic/spec is allowed to cite. Never invent outside this set."""
    allowed: set[str] = set()
    for hit in hits:
        raw = str(hit.get("id") or "").strip()
        if not raw:
            continue
        allowed.add(raw)
        allowed.add(raw.upper())
        compact = re.sub(r"^(PMID:?\s*|PMC)", "", raw, flags=re.I).strip()
        if compact:
            allowed.add(compact)
            allowed.add(compact.upper())
        digits = re.sub(r"\D", "", raw)
        if digits:
            allowed.add(digits)
    return allowed


def source_id_allowed(doc_id: str, allowed: set[str]) -> bool:
    raw = str(doc_id or "").strip()
    if not raw:
        return False
    if raw in allowed or raw.upper() in allowed:
        return True
    compact = re.sub(r"^(PMID:?\s*|PMC)", "", raw, flags=re.I).strip()
    return compact in allowed or compact.upper() in allowed


def _effect_from_blob(blob: str) -> str:
    low = blob.lower()
    if any(k in low for k in _LOSS_KW):
        return "loss"
    if any(k in low for k in _REDUCED_KW):
        return "reduced"
    return "unclear"


def spec_from_search_hits(
    hits: list[dict[str, Any]],
    *,
    origin: str = "paperclip",
) -> dict[str, Any] | None:
    """Build a contract spec from search hits. Only mutations with a real document id."""
    fixture_path = Path(__file__).resolve().parents[2] / "spec" / "fixtures" / "spec.example.json"
    fixture: dict[str, Any] = {}
    if fixture_path.is_file():
        fixture = json.loads(fixture_path.read_text())

    by_mut: dict[str, dict[str, Any]] = {
        mid: {"id": mid, "effect_on_sotorasib": "unclear", "sources": []}
        for mid in FROZEN_MUTATIONS
    }
    for hit in hits:
        doc_id = str(hit.get("id") or "").strip()
        if not doc_id:
            continue
        title = hit.get("title") or ""
        snippet = hit.get("snippet") or ""
        blob = f"{title} {snippet}"
        kind = "trial" if doc_id.upper().startswith("NCT") else "paper"
        for mid in FROZEN_MUTATIONS:
            if mid not in blob:
                continue
            sources = by_mut[mid]["sources"]
            if any(s.get("id") == doc_id for s in sources):
                continue
            if len(sources) >= 3:
                continue
            quote = snippet.strip() or title
            if mid in quote:
                # Keep a short window around the mutation token when possible.
                idx = quote.find(mid)
                start = max(0, idx - 80)
                quote = quote[start : start + 240]
            sources.append(
                {
                    "kind": kind,
                    "id": doc_id,
                    "title": title or doc_id,
                    "quote": quote[:280],
                    "origin": origin if origin in {"paperclip", "europepmc", "paperclip_mcp"} else "live",
                }
            )
            if by_mut[mid]["effect_on_sotorasib"] == "unclear":
                by_mut[mid]["effect_on_sotorasib"] = _effect_from_blob(blob)

    mutations = []
    for mid in FROZEN_MUTATIONS:
        row = by_mut[mid]
        if not row["sources"]:
            continue
        mutations.append(
            {
                "id": mid,
                "effect_on_sotorasib": row["effect_on_sotorasib"],
                "notes": (
                    f"Live harvest ({origin}). Effect inferred from nearby keywords; "
                    "confirm before clinical claims."
                ),
                "sources": row["sources"],
            }
        )
    if not mutations:
        return None

    spec = dict(fixture) if fixture else {}
    spec["schema_version"] = fixture.get("schema_version", "1.0")
    spec["provenance"] = "live"
    spec["hypothesis"] = fixture.get("hypothesis") or (
        "Switch II small-molecule drugs that work on KRAS G12C lose binding when pocket "
        "residues such as Y96 change; a designed miniprotein that uses a larger surface "
        "can keep contacts outside the sotorasib epitope and should be tested on Y96D, "
        "not only on wild-type G12C."
    )
    spec["target"] = fixture.get("target") or {
        "name": "KRAS G12C",
        "gene": "KRAS",
        "pdb_id": "6OIM",
        "uniprot_id": "P01116",
        "clinical_hook": "Sotorasib resistance in the Switch II pocket.",
    }
    spec["pocket_residues"] = fixture.get("pocket_residues") or ["Cys12", "Asp69", "His95", "Tyr96"]
    spec["success_bars"] = fixture.get("success_bars") or {
        "max_pdb_identity": 0.7,
        "min_plddt": 70,
        "require_mutant_score": True,
    }
    spec["structures"] = fixture.get("structures") or [
        {"pdb_id": "6OIM", "role": "wt", "notes": "Default receptor for the control docking arm."}
    ]
    spec["failed_small_molecules"] = fixture.get("failed_small_molecules") or []
    spec["mutations"] = mutations
    spec["evidence_quality"] = {
        "live_mutations_with_sources": len(mutations),
        "harvested_hits": len(hits),
        "source": origin,
    }
    return spec


def _paperclip_payload_to_spec(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Accept a contract-shaped spec, else map search hits into mutations."""
    if isinstance(raw, dict) and "hypothesis" in raw and "mutations" in raw:
        out = dict(raw)
        out.setdefault("provenance", "live")
        return out
    hits = compact_search_hits(raw)
    return spec_from_search_hits(hits, origin="paperclip") if hits else None


def gather_kras_resistance_evidence() -> tuple[dict | None, dict]:
    """Gather KRAS G12C resistance evidence.

    Returns (spec_or_None, raw_dump).

    Order:
    1. Try Paperclip CLI when key/CLI present and map hits → spec.json mutations.
    2. Europe PMC + ClinicalTrials.gov (still live PMIDs / NCT ids).
    """
    raw_dump: dict[str, Any] = {
        "europepmc": [],
        "clinicaltrials": [],
        "queries": [],
        "paperclip": None,
    }

    pc_hits: list[dict[str, Any]] = []
    if is_configured() or _cli_available():
        try:
            pc = search("KRAS G12C sotorasib resistance Y96D H95D R68S")
            raw_dump["paperclip"] = pc
            pc_hits = compact_search_hits(pc)
        except PaperclipUnavailable as e:
            raw_dump["paperclip_error"] = str(e)

    try:
        papers, trials, queries = literature.harvest_raw()
        raw_dump.update(literature.dump_paperclip_raw(papers, trials, queries))
        epmc_hits = compact_epmc_hits(papers)
        trial_hits = [
            {
                "id": str(t.get("nctId") or ""),
                "title": t.get("briefTitle") or "",
                "snippet": (t.get("briefSummary") or "")[:400],
                "source": "clinicaltrials",
            }
            for t in trials
            if t.get("nctId")
        ]
        combined = pc_hits + epmc_hits + trial_hits
        origin = "paperclip" if pc_hits else "europepmc"
        spec = spec_from_search_hits(combined, origin=origin)
        if spec is None:
            spec = literature.build_live_spec(papers, trials)
        return spec, raw_dump
    except Exception as e:  # noqa: BLE001
        raw_dump["literature_error"] = str(e)
        if pc_hits:
            return spec_from_search_hits(pc_hits, origin="paperclip"), raw_dump
        return None, raw_dump
