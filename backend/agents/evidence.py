"""Evidence agent — LangGraph + Paperclip MCP tools, else CLI/Europe PMC harvest."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from backend.agents.llm import call_llm_with_tools, extract_json
from backend.config import FAST_DEV, FIXTURES_DIR
from backend.contracts.validate import validate_spec
from backend.tools import literature, paperclip


AGENT_NAME = "evidence"
AGENT_DISPLAY = "Literature & databases (Paperclip MCP)"

_EVIDENCE_TOOLS = [
    {
        "name": "paperclip_search",
        "description": (
            "Search Paperclip (papers, preprints, trials) for KRAS G12C sotorasib/"
            "adagrasib resistance. Returns document ids, titles, snippets. "
            "Never invent ids — only cite ids this tool returns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. KRAS G12C sotorasib resistance Y96D",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "europepmc_search",
        "description": (
            "Search Europe PMC when Paperclip errors or returns nothing. "
            "Returns pmid/pmcid, title, abstract snippet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]

_AGENT_PROMPT = """You are the evidence agent for iDoctor Design (re:AGENT Track A).

Goal: gather how sotorasib fails on KRAS G12C resistance mutations and write a spec.

You MUST call paperclip_search at least once. If it errors, call europepmc_search.
Useful queries mention Y96D, H95D, R68S, Y96C, sotorasib, adagrasib.

After tools return, output ONLY JSON (no markdown) with this shape:
{
  "hypothesis": "one falsifiable sentence about Switch II drugs vs a larger binder on Y96D",
  "mutations": [
    {
      "id": "Y96D",
      "effect_on_sotorasib": "loss" | "reduced" | "unclear",
      "notes": "plain language",
      "sources": [
        {"kind": "paper"|"trial", "id": "<id from a tool result>", "title": "...", "quote": "short excerpt from the snippet"}
      ]
    }
  ]
}

Rules:
- Only use source ids that appeared in tool results. Never invent PMID/PMC/NCT/PDB ids.
- Prefer the frozen set Y96D, H95D, R68S, Y96C when they appear in hits.
- If a mutation is not in any hit, omit it.
"""


def _fixture_spec() -> dict:
    src = FIXTURES_DIR / "spec.example.json"
    return json.loads(src.read_text())


def _run_tool(name: str, args: dict[str, Any], raw_dump: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required", "n_results": 0, "results": []}

    if name == "paperclip_search":
        try:
            payload = paperclip.search(query, limit=12)
            raw_dump.setdefault("queries", []).append(query)
            raw_dump["paperclip"] = payload
            hits = paperclip.compact_search_hits(payload)
            raw_dump.setdefault("agent_hits", []).extend(hits)
            return {
                "source": "paperclip",
                "query": query,
                "n_results": len(hits),
                "results": hits,
            }
        except paperclip.PaperclipUnavailable as exc:
            raw_dump["paperclip_error"] = str(exc)
            return {"error": str(exc), "n_results": 0, "results": []}

    if name == "europepmc_search":
        papers = literature.search_europepmc(query, page_size=12)
        hits = paperclip.compact_epmc_hits(papers)
        raw_dump.setdefault("queries", []).append(query)
        raw_dump.setdefault("europepmc", []).extend(papers)
        raw_dump.setdefault("agent_hits", []).extend(hits)
        return {
            "source": "europepmc",
            "query": query,
            "n_results": len(hits),
            "results": hits,
        }

    return {"error": f"unknown tool {name}", "n_results": 0, "results": []}


def _sanitize_agent_spec(partial: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any] | None:
    allowed = paperclip.allowlist_from_hits(hits)
    if not allowed:
        return None
    base = _fixture_spec()
    hypothesis = str(partial.get("hypothesis") or "").strip()
    if hypothesis:
        base["hypothesis"] = hypothesis
    mutations: list[dict[str, Any]] = []
    for raw in partial.get("mutations") or []:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip()
        if not mid:
            continue
        effect = raw.get("effect_on_sotorasib")
        if effect not in {"loss", "reduced", "unclear"}:
            effect = "unclear"
        sources = []
        for src in raw.get("sources") or []:
            if not isinstance(src, dict):
                continue
            doc_id = str(src.get("id") or "").strip()
            if not paperclip.source_id_allowed(doc_id, allowed):
                continue
            kind = src.get("kind") if src.get("kind") in {"paper", "trial", "pdb", "chembl"} else "paper"
            if doc_id.upper().startswith("NCT"):
                kind = "trial"
            sources.append(
                {
                    "kind": kind,
                    "id": doc_id,
                    "title": str(src.get("title") or doc_id)[:300],
                    "quote": str(src.get("quote") or "")[:280],
                    "origin": "live",
                }
            )
        if not sources:
            continue
        mutations.append(
            {
                "id": mid,
                "effect_on_sotorasib": effect,
                "notes": str(raw.get("notes") or "Extracted by evidence agent from tool hits."),
                "sources": sources,
            }
        )
    if not mutations:
        return None
    base["mutations"] = mutations
    base["provenance"] = "live"
    base["evidence_quality"] = {
        "live_mutations_with_sources": len(mutations),
        "harvested_hits": len(hits),
        "source": "evidence_agent",
    }
    return base


def _run_evidence_agent(
    raw_dump: dict[str, Any], progress_cb=None
) -> tuple[dict | None, dict | None]:
    """Claude chooses Paperclip/Europe PMC queries, then we sanitize ids."""
    from backend.agents.lab_log import emit

    def execute(name: str, args: dict[str, Any]):
        query = str(args.get("query") or "")
        emit(progress_cb, AGENT_NAME, "tool", f"{name} {query}", tool=name)
        out = _run_tool(name, args, raw_dump)
        n = out.get("n_results") if isinstance(out, dict) else None
        emit(
            progress_cb,
            AGENT_NAME,
            "output",
            f"{name}: {n} hits" if n is not None else str(out)[:200],
            tool=name,
        )
        return out

    trace = call_llm_with_tools(_AGENT_PROMPT, _EVIDENCE_TOOLS, execute, max_tokens=1400, max_rounds=5)
    hits = list(raw_dump.get("agent_hits") or [])
    if not trace.get("success"):
        return None, trace
    try:
        partial = extract_json(trace.get("response") or "")
    except (json.JSONDecodeError, TypeError, ValueError):
        return paperclip.spec_from_search_hits(hits, origin="paperclip" if hits else "europepmc"), trace
    if not isinstance(partial, dict):
        return paperclip.spec_from_search_hits(hits, origin="paperclip"), trace
    spec = _sanitize_agent_spec(partial, hits)
    if spec is None:
        spec = paperclip.spec_from_search_hits(hits, origin="paperclip")
    return spec, trace


def _spec_from_agent_response(
    response: str, hits: list[dict[str, Any]], origin: str
) -> dict[str, Any] | None:
    try:
        partial = extract_json(response or "")
    except (json.JSONDecodeError, TypeError, ValueError):
        return paperclip.spec_from_search_hits(hits, origin=origin)
    if not isinstance(partial, dict):
        return paperclip.spec_from_search_hits(hits, origin=origin)
    spec = _sanitize_agent_spec(partial, hits)
    if spec is None:
        spec = paperclip.spec_from_search_hits(hits, origin=origin)
    if spec and isinstance(spec.get("evidence_quality"), dict):
        spec["evidence_quality"]["source"] = origin
    return spec


def _run_mcp_evidence_agent(
    raw_dump: dict[str, Any], progress_cb=None
) -> tuple[dict | None, dict | None]:
    """Bind Paperclip MCP tools onto a LangGraph ReAct agent, then sanitize ids."""
    from backend.tools.paperclip_mcp import hits_from_tool_texts, run_paperclip_mcp_agent

    trace = run_paperclip_mcp_agent(progress_cb)
    texts = list(trace.get("tool_texts") or [])
    hits = hits_from_tool_texts(texts)
    raw_dump.setdefault("agent_hits", []).extend(hits)
    raw_dump["mcp_tool_names"] = trace.get("mcp_tool_names")
    raw_dump["mcp_tool_texts"] = [str(t)[:8000] for t in texts[:20]]
    spec = _spec_from_agent_response(trace.get("response") or "", hits, "paperclip_mcp")
    ui_trace = {k: v for k, v in trace.items() if k != "tool_texts"}
    return spec, ui_trace


def run_evidence(state: dict, progress_cb=None) -> dict:
    start = time.perf_counter()
    run_dir = Path(state["run_dir"])
    mode = state.get("mode", "fixture")
    provenance_nodes = dict(state.get("provenance_nodes") or {})
    tool_calls: list[dict] = []
    steps: list[dict] = []
    scientific_spec: dict | None = None
    node_source = "fixture"
    llm_trace = None

    if progress_cb:
        progress_cb(AGENT_NAME, "running", step="Evidence agent searching literature...")

    if mode == "replay":
        spec_path = run_dir / "spec.json"
        if not spec_path.exists():
            raise FileNotFoundError(f"Replay missing {spec_path}")
        scientific_spec = json.loads(spec_path.read_text())
        node_source = "cached"
        steps.append({"action": "Load cached spec", "detail": str(spec_path)})
    elif mode == "live":
        raw_dump: dict[str, Any] = {
            "europepmc": [],
            "clinicaltrials": [],
            "queries": [],
            "paperclip": None,
            "agent_hits": [],
        }
        if not FAST_DEV:
            from backend.tools.paperclip_mcp import (
                PaperclipMcpUnavailable,
                mcp_configured,
            )

            if mcp_configured():
                if progress_cb:
                    progress_cb(
                        AGENT_NAME,
                        "running",
                        step="LangGraph evidence agent calling Paperclip MCP tools...",
                    )
                try:
                    scientific_spec, llm_trace = _run_mcp_evidence_agent(raw_dump, progress_cb)
                    tool_calls.extend(llm_trace.get("tool_calls") or [] if llm_trace else [])
                    if scientific_spec:
                        node_source = "live"
                        steps.append(
                            {
                                "action": "Evidence agent (LangGraph + Paperclip MCP)",
                                "detail": (
                                    f"mcp_tools={len((llm_trace or {}).get('mcp_tool_names') or [])}; "
                                    f"calls={len(tool_calls)}; "
                                    f"mutations={len(scientific_spec.get('mutations') or [])}"
                                ),
                            }
                        )
                    else:
                        steps.append(
                            {
                                "action": "Paperclip MCP agent produced no spec",
                                "detail": (llm_trace or {}).get("error")
                                or "falling back to CLI / harvest",
                            }
                        )
                except PaperclipMcpUnavailable as exc:
                    raw_dump["mcp_error"] = str(exc)
                    steps.append(
                        {
                            "action": "Paperclip MCP unavailable",
                            "detail": str(exc)[:400],
                        }
                    )

            if scientific_spec is None:
                if progress_cb:
                    progress_cb(AGENT_NAME, "running", step="Claude choosing Paperclip CLI queries...")
                scientific_spec, llm_trace = _run_evidence_agent(raw_dump, progress_cb)
                tool_calls.extend(llm_trace.get("tool_calls") or [] if llm_trace else [])
                if scientific_spec:
                    node_source = "live"
                    steps.append(
                        {
                            "action": "Evidence agent (Claude + CLI tools)",
                            "detail": (
                                f"tools={len(tool_calls)}; "
                                f"mutations={len(scientific_spec.get('mutations') or [])}"
                            ),
                        }
                    )
                else:
                    steps.append(
                        {
                            "action": "Evidence agent produced no spec",
                            "detail": (llm_trace or {}).get("anthropic_error")
                            or (llm_trace or {}).get("error")
                            or "falling back to deterministic harvest",
                        }
                    )

        if scientific_spec is None:
            tool_calls.append(
                {
                    "tool": "paperclip.gather_kras_resistance_evidence",
                    "detail": "Paperclip hits mapped to mutations, else Europe PMC",
                }
            )
            try:
                spec, raw = paperclip.gather_kras_resistance_evidence()
                raw_dump.update(raw)
                if spec is not None:
                    scientific_spec = spec
                    node_source = (
                        "live" if scientific_spec.get("provenance") == "live" else "fixture"
                    )
                    steps.append(
                        {
                            "action": "Deterministic evidence harvest",
                            "detail": (
                                f"provenance={scientific_spec.get('provenance')}; "
                                f"mutations={len(scientific_spec.get('mutations') or [])}"
                            ),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                steps.append({"action": "Live evidence failed", "detail": str(e)})

        (run_dir / "paperclip_raw.json").write_text(json.dumps(raw_dump, indent=2, default=str))

    if scientific_spec is None:
        src = FIXTURES_DIR / "spec.example.json"
        dest = run_dir / "spec.json"
        shutil.copy2(src, dest)
        scientific_spec = json.loads(dest.read_text())
        scientific_spec["provenance"] = "fixture"
        dest.write_text(json.dumps(scientific_spec, indent=2))
        raw_path = run_dir / "paperclip_raw.json"
        if not raw_path.exists():
            raw_path.write_text(
                json.dumps(
                    {
                        "source": "fixture",
                        "note": "Paperclip/literature not used; copied spec.example.json",
                        "europepmc": [],
                        "clinicaltrials": [],
                        "queries": [],
                    },
                    indent=2,
                )
            )
        node_source = "fixture"
        steps.append({"action": "Load fixture spec", "detail": str(src)})

    validate_spec(scientific_spec)
    (run_dir / "spec.json").write_text(json.dumps(scientific_spec, indent=2))
    provenance_nodes[AGENT_NAME] = node_source

    elapsed = time.perf_counter() - start
    trace = {
        "agent": AGENT_NAME,
        "agent_name": AGENT_DISPLAY,
        "duration_seconds": round(elapsed, 2),
        "model": (llm_trace or {}).get("model"),
        "input_summary": f"mode={mode}",
        "output_summary": (
            f"spec with {len(scientific_spec.get('mutations', []))} mutations; "
            f"hypothesis set; provenance={scientific_spec.get('provenance')}"
        ),
        "steps": steps,
        "tool_calls": tool_calls,
        "llm_calls": [llm_trace] if llm_trace else [],
    }

    traces = list(state.get("agent_traces") or [])
    traces.append(trace)
    return {
        "scientific_spec": scientific_spec,
        "hypothesis": scientific_spec.get("hypothesis", ""),
        "provenance_nodes": provenance_nodes,
        "agent_traces": traces,
    }
