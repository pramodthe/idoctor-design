"""Shared LLM helper — Claude (Anthropic) only."""

from __future__ import annotations

import time

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL


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
        model_l = (ANTHROPIC_MODEL or "").lower()
        if "sonnet-5" in model_l or model_l.startswith("claude-opus-5"):
            # Adaptive thinking is default; keep call simple for critic JSON.
            pass
        else:
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
