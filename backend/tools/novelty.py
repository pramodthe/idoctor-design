"""Database-backed protein novelty checks using the RCSB PDB MMseqs2 API."""

from __future__ import annotations

import time
from typing import Any

import requests


RCSB_SEQUENCE_URL = "https://search.rcsb.org/rcsbsearch/v2/query"


class NoveltyUnavailable(RuntimeError):
    """Raised when the PDB sequence search cannot produce a trustworthy result."""


def _protein_sequence(raw: str) -> str:
    sequence = "".join(c for c in (raw or "").upper() if c.isalpha())
    invalid = sorted(set(sequence) - set("ACDEFGHIKLMNPQRSTVWY"))
    if invalid:
        raise NoveltyUnavailable(f"Unsupported amino acid(s): {', '.join(invalid)}")
    if len(sequence) < 20:
        raise NoveltyUnavailable("RCSB sequence search requires a protein of at least 20 aa")
    return sequence


def _match_contexts(hit: dict[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for service in hit.get("services") or []:
        for node in service.get("nodes") or []:
            for context in node.get("match_context") or []:
                if isinstance(context, dict):
                    contexts.append(context)
    return contexts


def search_pdb_sequence(
    sequence: str,
    *,
    identity_cutoff: float = 0.30,
    evalue_cutoff: float = 1.0,
    rows: int = 5,
    timeout: float = 30.0,
    attempts: int = 3,
) -> dict[str, Any]:
    """Return the highest PDB sequence identity reported by RCSB's MMseqs2 search.

    HTTP 204 is a successful search with no hits at the requested cutoff. Because
    the exact maximum is unknown, return the cutoff as a conservative upper bound.
    Network or schema failures never become novelty evidence.
    """
    query_sequence = _protein_sequence(sequence)
    payload = {
        "query": {
            "type": "terminal",
            "service": "sequence",
            "parameters": {
                "evalue_cutoff": float(evalue_cutoff),
                "identity_cutoff": float(identity_cutoff),
                "sequence_type": "protein",
                "value": query_sequence,
            },
        },
        "request_options": {
            "results_verbosity": "verbose",
            "paginate": {"start": 0, "rows": max(1, int(rows))},
            "scoring_strategy": "sequence",
        },
        "return_type": "polymer_entity",
    }

    last_error = "unknown error"
    for attempt in range(max(1, int(attempts))):
        try:
            response = requests.post(RCSB_SEQUENCE_URL, json=payload, timeout=timeout)
            if response.status_code == 204:
                return {
                    # No hit at the cutoff means the true maximum is below it;
                    # report the conservative upper bound, never a fabricated zero.
                    "identity": float(identity_cutoff),
                    "identity_is_upper_bound": True,
                    "method": "rcsb_mmseqs2",
                    "database": "PDB",
                    "query_id": None,
                    "hits": [],
                    "identity_cutoff": float(identity_cutoff),
                }
            response.raise_for_status()
            data = response.json()
            hits: list[dict[str, Any]] = []
            for hit in data.get("result_set") or []:
                contexts = _match_contexts(hit)
                identities = [
                    float(c["sequence_identity"])
                    for c in contexts
                    if c.get("sequence_identity") is not None
                ]
                if not identities:
                    continue
                best_context = max(
                    contexts,
                    key=lambda c: float(c.get("sequence_identity") or -1.0),
                )
                hits.append(
                    {
                        "id": hit.get("identifier"),
                        "identity": max(identities),
                        "evalue": best_context.get("evalue"),
                        "alignment_length": best_context.get("alignment_length"),
                        "query_coverage": (
                            float(best_context.get("alignment_length") or 0)
                            / max(float(best_context.get("query_length") or len(query_sequence)), 1.0)
                        ),
                    }
                )
            hits.sort(key=lambda row: float(row["identity"]), reverse=True)
            return {
                "identity": round(
                    max(
                        (float(h["identity"]) for h in hits),
                        default=float(identity_cutoff),
                    ),
                    4,
                ),
                "identity_is_upper_bound": not bool(hits),
                "method": "rcsb_mmseqs2",
                "database": "PDB",
                "query_id": data.get("query_id"),
                "hits": hits,
                "identity_cutoff": float(identity_cutoff),
            }
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = str(exc)
            if attempt + 1 < max(1, int(attempts)):
                time.sleep(1.5 * (attempt + 1))
    raise NoveltyUnavailable(f"RCSB MMseqs2 search failed: {last_error}")
