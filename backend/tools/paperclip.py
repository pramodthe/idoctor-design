"""Paperclip literature search — CLI/SDK with API key; else Europe PMC / CT.gov live path.

Paperclip (https://paperclip.gxl.ai/docs) is used via:
  - CLI: `paperclip search …` with PAPERCLIP_API_KEY (X-API-Key) or OAuth
  - Optional PAPERCLIP_BASE_URL for non-default server (local/dev)
  - MCP: https://paperclip.gxl.ai/mcp (agent side; not this Python module)

There is no first-class public “PAPERCLIP_API_URL/search” REST surface we own —
do not invent one. Prefer the official CLI.
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


def _paperclip_payload_to_spec(raw: dict[str, Any]) -> dict[str, Any] | None:
    """If Paperclip already returned a contract-shaped spec, use it."""
    if isinstance(raw, dict) and "hypothesis" in raw and "mutations" in raw:
        out = dict(raw)
        out.setdefault("provenance", "live")
        return out
    return None


def gather_kras_resistance_evidence() -> tuple[dict | None, dict]:
    """Gather KRAS G12C resistance evidence.

    Returns (spec_or_None, raw_dump).

    Order:
    1. Try Paperclip CLI when key/CLI present.
    2. On failure or unconfigured → literature.build_live_spec (Europe PMC + CT.gov)
       so LIVE mode still gets real PMIDs / NCT ids.
    """
    raw_dump: dict[str, Any] = {
        "europepmc": [],
        "clinicaltrials": [],
        "queries": [],
        "paperclip": None,
    }

    if is_configured() or _cli_available():
        try:
            pc = search("KRAS G12C sotorasib resistance Y96D H95D R68S")
            raw_dump["paperclip"] = pc
            spec = _paperclip_payload_to_spec(pc) if isinstance(pc, dict) else None
            if spec is not None:
                return spec, raw_dump
        except PaperclipUnavailable as e:
            raw_dump["paperclip_error"] = str(e)

    try:
        papers, trials, queries = literature.harvest_raw()
        spec = literature.build_live_spec(papers, trials)
        raw_dump.update(literature.dump_paperclip_raw(papers, trials, queries))
        return spec, raw_dump
    except Exception as e:  # noqa: BLE001
        raw_dump["literature_error"] = str(e)
        return None, raw_dump
