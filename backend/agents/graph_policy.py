"""LangGraph routing policy for the bounded design-verification loop."""

from __future__ import annotations

from backend.config import MAX_DESIGN_ITERATIONS


# Compatibility name used by the critic/tests. Iteration 1 is the initial
# design, so retries are the remaining iterations in the compute budget.
MAX_DESIGN_RETRIES = max(0, MAX_DESIGN_ITERATIONS - 1)


def route_after_critic(state: dict) -> str:
    """Return the next node name: designer | experiment."""
    if (state.get("mode") or "") != "live":
        return "experiment"
    max_iterations = max(
        1, int(state.get("max_design_iterations") or MAX_DESIGN_ITERATIONS)
    )
    iteration = int(
        state.get("loop_iteration")
        or (int(state.get("design_retry_count") or 0) + 1)
    )
    if iteration >= max_iterations:
        return "experiment"
    if state.get("critic_route") == "redesign":
        return "designer"
    return "experiment"
