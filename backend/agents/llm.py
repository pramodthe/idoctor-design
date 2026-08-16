"""Shared LLM helper — Claude (Anthropic) only."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, including fenced ```json blocks."""
    blob = (text or "").strip()
    if "```" in blob:
        inner = blob.split("```", 1)[1]
        if inner.startswith("json"):
            inner = inner[4:]
        blob = inner.split("```", 1)[0].strip()
    return json.loads(blob)


def _sonnet5_or_opus5(model: str) -> bool:
    model_l = (model or "").lower()
    return "sonnet-5" in model_l or model_l.startswith("claude-opus-5")


def call_llm(prompt: str, max_tokens: int = 512, temperature: float = 0.3) -> dict:
    """Call Claude and return both the response and a trace log (stable shape)."""
    trace = {
        "prompt": prompt,
        "model": None,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response": "",
        "duration_ms": 0,
        "success": False,
    }

    start = time.perf_counter()

    if not ANTHROPIC_API_KEY:
        elapsed = (time.perf_counter() - start) * 1000
        trace["duration_ms"] = round(elapsed)
        trace["error"] = "No LLM configured (set ANTHROPIC_API_KEY)"
        return trace

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        # Sonnet 5+ rejects temperature / top_p / top_k (HTTP 400).
        create_kwargs: dict = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if not _sonnet5_or_opus5(ANTHROPIC_MODEL):
            create_kwargs["temperature"] = temperature
        resp = client.messages.create(**create_kwargs)
        text_parts = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif hasattr(block, "text"):
                text_parts.append(block.text)
        text = "".join(text_parts)
        elapsed = (time.perf_counter() - start) * 1000
        trace["model"] = ANTHROPIC_MODEL
        trace["response"] = text
        trace["duration_ms"] = round(elapsed)
        trace["success"] = True
        return trace
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        trace["duration_ms"] = round(elapsed)
        trace["anthropic_error"] = str(e)
        return trace


def call_llm_with_tools(
    prompt: str,
    tools: list[dict[str, Any]],
    execute: Callable[[str, dict[str, Any]], Any],
    *,
    max_tokens: int = 1200,
    max_rounds: int = 5,
) -> dict:
    """Claude tool-use loop. `execute(name, input)` runs each tool.

    Returns the same trace shape as call_llm plus `tool_calls`.
    """
    trace: dict[str, Any] = {
        "prompt": prompt,
        "model": None,
        "max_tokens": max_tokens,
        "temperature": None,
        "response": "",
        "duration_ms": 0,
        "success": False,
        "tool_calls": [],
    }
    start = time.perf_counter()
    if not ANTHROPIC_API_KEY:
        trace["duration_ms"] = round((time.perf_counter() - start) * 1000)
        trace["error"] = "No LLM configured (set ANTHROPIC_API_KEY)"
        return trace

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        create_kwargs: dict[str, Any] = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "tools": tools,
            "messages": messages,
        }
        if not _sonnet5_or_opus5(ANTHROPIC_MODEL):
            create_kwargs["temperature"] = 0.2

        text = ""
        for _ in range(max(1, max_rounds)):
            create_kwargs["messages"] = messages
            resp = client.messages.create(**create_kwargs)
            blocks = list(resp.content or [])
            tool_uses = [b for b in blocks if getattr(b, "type", None) == "tool_use"]
            text_parts = []
            for block in blocks:
                if getattr(block, "type", None) == "text":
                    text_parts.append(block.text)
                elif hasattr(block, "text") and getattr(block, "type", None) != "tool_use":
                    text_parts.append(block.text)
            if text_parts:
                text = "".join(text_parts)

            if not tool_uses or resp.stop_reason == "end_turn":
                break

            messages.append({"role": "assistant", "content": blocks})
            results = []
            for tu in tool_uses:
                name = str(getattr(tu, "name", "") or "")
                raw_in = getattr(tu, "input", None) or {}
                args = dict(raw_in) if isinstance(raw_in, dict) else {}
                try:
                    output = execute(name, args)
                except Exception as exc:  # noqa: BLE001
                    output = {"error": str(exc)}
                preview = json.dumps(output, default=str)
                trace["tool_calls"].append(
                    {
                        "tool": name,
                        "input": args,
                        "ok": not (isinstance(output, dict) and output.get("error")),
                        "n_results": (
                            output.get("n_results")
                            if isinstance(output, dict)
                            else None
                        ),
                    }
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": preview[:12000],
                    }
                )
            messages.append({"role": "user", "content": results})

        elapsed = (time.perf_counter() - start) * 1000
        trace["model"] = ANTHROPIC_MODEL
        trace["response"] = text
        trace["duration_ms"] = round(elapsed)
        trace["success"] = True
        return trace
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        trace["duration_ms"] = round(elapsed)
        trace["anthropic_error"] = str(e)
        return trace


def is_llm_trace(trace: Any) -> bool:
    """True when this dict is a real Anthropic round, not a Python node stamp."""
    if not isinstance(trace, dict):
        return False
    if trace.get("success") is True and (trace.get("response") or trace.get("tool_calls")):
        return True
    model = str(trace.get("model") or "").lower()
    return "claude" in model or model.startswith("anthropic")


def count_llm_calls(calls: list | None) -> int:
    return sum(1 for c in (calls or []) if is_llm_trace(c))
