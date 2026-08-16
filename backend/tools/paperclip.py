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
import shutil
import subprocess
from typing import Any

from backend.config import PAPERCLIP_API_KEY, PAPERCLIP_BASE_URL
from backend.tools import literature


class PaperclipUnavailable(RuntimeError):
    """Raised when Paperclip cannot be reached or is not configured."""


def is_configured() -> bool:
    return bool(PAPERCLIP_API_KEY)


def _cli_available() -> bool:
    return shutil.which("paperclip") is not None


def search(query: str, **kwargs: Any) -> dict[str, Any] | None:
    """Live Paperclip search via official CLI.

    Requires `paperclip` on PATH and either PAPERCLIP_API_KEY or prior `paperclip login`.
    """
    if not is_configured() and not _cli_available():
        raise PaperclipUnavailable(
            "Paperclip unavailable: PAPERCLIP_API_KEY not set and CLI not found. "
            "Install from https://paperclip.gxl.ai/docs or use literature fallback."
        )

    if not _cli_available():
        raise PaperclipUnavailable(
            "Paperclip CLI not installed. "
            "Run: curl -fsSL https://paperclip.gxl.ai/install.sh | bash "
            "Then set PAPERCLIP_API_KEY. (There is no custom REST API URL to fill in.)"
        )

    timeout = kwargs.get("timeout", 60)
    cmd = ["paperclip"]
    if PAPERCLIP_API_KEY:
        cmd.extend(["--api-key", PAPERCLIP_API_KEY])
    cmd.extend(["search", query])

    env = os.environ.copy()
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

    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw_text": out, "query": query}


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
