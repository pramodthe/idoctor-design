"""Paperclip MCP → LangGraph tools.

Paperclip docs expose the same corpus three ways. For this backend the live
evidence *agent* should bind the hosted MCP server as tools:

    https://paperclip.gxl.ai/mcp
    header X-API-Key: PAPERCLIP_API_KEY

langchain-mcp-adapters turns those MCP tools into LangChain tools; LangGraph's
ReAct agent (create_react_agent) then calls search / grep / map / … itself.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from backend.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    PAPERCLIP_API_KEY,
    PAPERCLIP_MCP_URL,
)


class PaperclipMcpUnavailable(RuntimeError):
    """Raised when the Paperclip MCP server cannot be bound as tools."""


_DOC_ID_RE = re.compile(
    r"\b(PMC\d+|PMID:?\s*\d+|NCT\d{8}|s_[A-Za-z0-9]+|[1-9]\d{6,8})\b",
    re.I,
)


def mcp_configured() -> bool:
    return bool(PAPERCLIP_API_KEY and PAPERCLIP_MCP_URL)


def _mcp_server_config(transport: str) -> dict[str, Any]:
    return {
        "paperclip": {
            "transport": transport,
            "url": PAPERCLIP_MCP_URL,
            "headers": {"X-API-Key": PAPERCLIP_API_KEY},
        }
    }


# Read/search tools only — skip write/admin MCP methods if the server exposes them.
_ALLOWED_MCP_TOOLS = {
    "paperclip",
    "search",
    "searches",
    "grep",
    "scan",
    "lookup",
    "sql",
    "map",
    "reduce",
    "filter",
    "cat",
    "ls",
    "find",
    "head",
    "wc",
    "ask-image",
    "ask_image",
}


def _tool_basename(name: str) -> str:
    n = (name or "").strip()
    for sep in ("__", ":", "/", "."):
        if sep in n:
            n = n.split(sep)[-1]
    if n.lower().startswith("paperclip_"):
        n = n.split("_", 1)[-1]
    if n.lower().startswith("paperclip-"):
        n = n.split("-", 1)[-1]
    return n


def _select_mcp_tools(tools: list) -> list:
    allowed = {a.replace("_", "-").lower() for a in _ALLOWED_MCP_TOOLS}
    selected = [
        t
        for t in tools
        if _tool_basename(getattr(t, "name", "")).lower().replace("_", "-") in allowed
    ]
    return selected or list(tools)


def _europepmc_tool(progress_cb=None):
    from langchain_core.tools import StructuredTool

    from backend.agents.lab_log import emit
    from backend.tools import paperclip
    from backend.tools.literature import search_europepmc

    def europepmc_search(query: str) -> str:
        """Search Europe PMC if Paperclip MCP errors. Returns JSON hits with real PMIDs."""
        emit(progress_cb, "evidence", "tool", f"europepmc_search {query}", tool="europepmc_search")
        papers = search_europepmc(query, page_size=12)
        hits = paperclip.compact_epmc_hits(papers)
        emit(
            progress_cb,
            "evidence",
            "output",
            f"{len(hits)} Europe PMC hits",
            tool="europepmc_search",
        )
        return json.dumps({"source": "europepmc", "n_results": len(hits), "results": hits})

    return StructuredTool.from_function(
        europepmc_search,
        name="europepmc_search",
        description=(
            "Fallback literature search on Europe PMC when Paperclip MCP is down "
            "or returns nothing. Use a KRAS G12C / sotorasib / Y96D query."
        ),
    )


def _create_agent(model, tools, system_prompt: str | None = None):
    # checkpointer=False: the pipeline compiles with a sync SqliteSaver, and this
    # subgraph is driven with ainvoke. Inheriting the parent saver raises
    # NotImplementedError on aget_tuple, so opt out instead of inheriting.
    try:
        from langchain.agents import create_agent

        kwargs = {}
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
        return create_agent(model, tools, checkpointer=False, **kwargs)
    except Exception:  # noqa: BLE001
        from langgraph.prebuilt import create_react_agent

        if system_prompt:
            return create_react_agent(
                model, tools, prompt=system_prompt, checkpointer=False
            )
        return create_react_agent(model, tools, checkpointer=False)


def _preview_mcp_result(result: Any) -> str:
    text = ""
    content = getattr(result, "content", None)
    if content is None:
        content = result
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
            elif hasattr(block, "text"):
                parts.append(str(block.text))
        text = " ".join(parts)
    else:
        text = str(content)
    return " ".join(text.split())[:500]


def _mcp_interceptor(progress_cb):
    async def interceptor(request, handler):
        from backend.agents.lab_log import emit

        args = request.args if isinstance(request.args, dict) else {}
        cmd = args.get("command") or json.dumps(args, default=str)[:240]
        emit(
            progress_cb,
            "evidence",
            "tool",
            f"{request.name} {cmd}",
            tool=request.name,
        )
        result = await handler(request)
        emit(
            progress_cb,
            "evidence",
            "output",
            _preview_mcp_result(result) or f"{request.name} returned",
            tool=request.name,
        )
        return result

    return interceptor


async def _load_mcp_tools(progress_cb=None):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    if not mcp_configured():
        raise PaperclipMcpUnavailable(
            "Paperclip MCP needs PAPERCLIP_API_KEY and PAPERCLIP_MCP_URL "
            "(default https://paperclip.gxl.ai/mcp)."
        )

    interceptors = [_mcp_interceptor(progress_cb)] if progress_cb else None
    errors: list[str] = []
    for transport in ("http", "streamable_http", "sse"):
        kwargs: dict[str, Any] = {}
        if interceptors:
            kwargs["tool_interceptors"] = interceptors
        client = MultiServerMCPClient(_mcp_server_config(transport), **kwargs)
        try:
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{transport}: {exc}")
            continue
        if tools:
            return client, list(tools)
        errors.append(f"{transport}: zero tools")
    raise PaperclipMcpUnavailable(
        "Paperclip MCP get_tools failed: " + " | ".join(errors)
    )


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif hasattr(block, "text"):
                parts.append(str(block.text))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _walk_messages(result: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Return (final assistant text, tool_call traces, raw tool texts)."""
    messages = result.get("messages") or []
    tool_calls: list[dict[str, Any]] = []
    tool_texts: list[str] = []
    last_text = ""
    for msg in messages:
        name = type(msg).__name__
        for tc in getattr(msg, "tool_calls", None) or []:
            if isinstance(tc, dict):
                tool_calls.append(
                    {
                        "tool": tc.get("name") or "mcp",
                        "input": tc.get("args") or {},
                        "ok": True,
                        "source": "paperclip_mcp",
                    }
                )
            else:
                tool_calls.append(
                    {
                        "tool": getattr(tc, "name", "mcp"),
                        "input": getattr(tc, "args", {}) or {},
                        "ok": True,
                        "source": "paperclip_mcp",
                    }
                )
        text = _message_text(msg)
        if name in {"ToolMessage", "Tool"} or getattr(msg, "type", None) == "tool":
            tool_texts.append(text)
            if not any(c.get("tool") == getattr(msg, "name", None) for c in tool_calls[-1:]):
                tool_calls.append(
                    {
                        "tool": getattr(msg, "name", None) or "mcp",
                        "ok": True,
                        "source": "paperclip_mcp",
                        "n_results": None,
                    }
                )
        if name in {"AIMessage", "AIMessageChunk"} and text.strip():
            last_text = text
    return last_text, tool_calls, tool_texts


def _hits_from_json_blob(blob: str) -> list[dict[str, Any]]:
    from backend.tools.paperclip import compact_epmc_hits, compact_search_hits

    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        data = {"results": data}
    if not isinstance(data, dict):
        return []
    hits = compact_search_hits(data)
    if hits:
        for h in hits:
            h["source"] = h.get("source") or "paperclip_mcp"
        return hits
    rows = data.get("europepmc") or []
    if isinstance(rows, list) and rows:
        return compact_epmc_hits(rows)
    return []


def hits_from_tool_texts(texts: list[str]) -> list[dict[str, Any]]:
    """Collect citable document ids from MCP tool stdout (never invent)."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(doc_id: str, title: str, snippet: str, source: str) -> None:
        doc_id = re.sub(r"^PMID:?\s*", "", str(doc_id).strip(), flags=re.I)
        key = doc_id.upper()
        if not doc_id or key in seen or key.startswith("S_"):
            return
        if doc_id.isdigit():
            n = int(doc_id)
            if n < 10000 or 1900 <= n <= 2099:
                return
        seen.add(key)
        hits.append(
            {
                "id": doc_id,
                "title": (title or "")[:300],
                "snippet": (snippet or "")[:400],
                "source": source or "paperclip_mcp",
            }
        )

    for blob in texts:
        for row in _hits_from_json_blob(blob or ""):
            _add(row.get("id") or "", row.get("title") or "", row.get("snippet") or "", row.get("source") or "paperclip_mcp")
        for raw in _DOC_ID_RE.findall(blob or ""):
            snippet = ""
            idx = (blob or "").find(str(raw))
            if idx >= 0:
                snippet = blob[max(0, idx - 80) : idx + 200]
            _add(str(raw), "", snippet, "paperclip_mcp")
    return hits


_AGENT_PROMPT = """You are the iDoctor Design evidence agent (re:AGENT Track A).

Tools:
- `paperclip`: hosted Paperclip MCP. Argument is `command`, a CLI string (no `paperclip` prefix).
  Examples:
    search -s pmc "KRAS G12C sotorasib resistance Y96D" -n 12
    search -s pmc "KRAS G12C H95D R68S adagrasib" -n 12
    search -s trials "KRAS G12C sotorasib" -n 8
    map --from s_XXXX "Quote how Y96D/H95D/R68S/Y96C affect sotorasib. Include PMIDs/PMCs."
    grep -i "Y96D" /papers/
- `europepmc_search`: only if `paperclip` errors or returns nothing.

Do NOT call `skill` (too long). Do NOT invent document ids.

Task: how sotorasib fails on KRAS G12C resistance (Y96D, H95D, R68S, Y96C).

1. Call `paperclip` with a search command first.
2. If you get a result set id (s_…), optionally map/grep it.
3. Then output ONLY JSON (no markdown):

{
  "hypothesis": "one falsifiable sentence: Switch II drugs lose Y96D; a larger binder should be tested on the mutant",
  "mutations": [
    {
      "id": "Y96D",
      "effect_on_sotorasib": "loss" | "reduced" | "unclear",
      "notes": "plain language",
      "sources": [
        {"kind": "paper"|"trial", "id": "<id from a tool result>", "title": "...", "quote": "short excerpt"}
      ]
    }
  ]
}

Only cite PMID/PMC/NCT ids that appeared in tool results. Omit a mutation if no tool hit mentions it.
"""


async def _ainvoke_evidence_agent(progress_cb=None) -> dict[str, Any]:
    from langchain_anthropic import ChatAnthropic

    if not ANTHROPIC_API_KEY:
        raise PaperclipMcpUnavailable("ANTHROPIC_API_KEY required to drive Paperclip MCP tools.")

    client, mcp_tools = await _load_mcp_tools(progress_cb)
    tools = _select_mcp_tools(mcp_tools) + [_europepmc_tool(progress_cb)]
    model = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=1600,
    )
    agent = _create_agent(
        model,
        tools,
        system_prompt=(
            "You are iDoctor Design's evidence agent. Use the `paperclip` MCP tool "
            "with CLI commands like `search -s pmc \"KRAS G12C sotorasib Y96D\" -n 12`. "
            "Never invent PMID/PMC/NCT ids. When finished, output JSON only."
        ),
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": _AGENT_PROMPT}]},
        config={"recursion_limit": 15},
    )
    # Keep the MCP client alive until tools finish (stateless per-call sessions).
    _ = client
    last_text, tool_calls, tool_texts = _walk_messages(result if isinstance(result, dict) else {})
    return {
        "success": True,
        "model": ANTHROPIC_MODEL,
        "response": last_text,
        "tool_calls": tool_calls,
        "tool_texts": tool_texts,
        "mcp_tool_names": [getattr(t, "name", "") for t in mcp_tools],
        "source": "paperclip_mcp",
    }


def run_paperclip_mcp_agent(progress_cb=None) -> dict[str, Any]:
    """Sync entry for the evidence node (pipeline runs in a worker thread)."""

    async def _run():
        return await _ainvoke_evidence_agent(progress_cb)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())

    # Already inside a loop (shouldn't be the FastAPI to_thread path).
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result(timeout=180)
