"""Lab-log events streamed to the UI (not a chatbot)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

LogCallback = Callable[..., Any]


def emit(
    cb: LogCallback | None,
    agent: str,
    kind: str,
    text: str,
    *,
    tool: str | None = None,
    status: str = "running",
) -> None:
    """kind: step | tool | thought | output | route"""
    if cb is None:
        return
    log: dict[str, Any] = {"kind": kind, "text": (text or "")[:800]}
    if tool:
        log["tool"] = tool
    kwargs: dict[str, Any] = {"log": log}
    if kind == "step":
        kwargs["step"] = (text or "")[:160]
    cb(agent, status, **kwargs)


def _tool_text(tc: dict[str, Any]) -> str:
    name = str(tc.get("tool") or "tool")
    inp = tc.get("input")
    if inp is None:
        inp = tc.get("detail") or ""
    if isinstance(inp, dict):
        if "command" in inp:
            return f"{name} {inp.get('command')}"
        if "query" in inp:
            return f"{name} {inp.get('query')}"
        inp = json.dumps(inp, default=str)
    return f"{name} {inp}".strip()[:400]


def events_from_trace(trace: dict[str, Any]) -> list[dict[str, Any]]:
    agent = str(trace.get("agent") or "agent")
    events: list[dict[str, Any]] = []
    for step in trace.get("steps") or []:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip()
        detail = str(step.get("detail") or "").strip()
        text = f"{action}: {detail}" if detail else action
        if text:
            events.append({"agent": agent, "kind": "step", "text": text[:800]})
    for tc in trace.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        events.append(
            {
                "agent": agent,
                "kind": "tool",
                "tool": str(tc.get("tool") or "tool"),
                "text": _tool_text(tc),
            }
        )
    summary = str(trace.get("output_summary") or "").strip()
    if summary:
        events.append({"agent": agent, "kind": "output", "text": summary[:800]})
    route = str(trace.get("critic_route") or "").strip()
    if route:
        events.append({"agent": agent, "kind": "route", "text": f"next → {route}"})
    return events


def flatten_traces(traces: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for trace in traces or []:
        if isinstance(trace, dict):
            out.extend(events_from_trace(trace))
    return out
