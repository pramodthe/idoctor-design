"""Evaluation oracle: Spearman ρ, disagreements, design WT/mutant deltas."""

from __future__ import annotations

import math
from typing import Any


def pKi(ki_nm: float | None) -> float | None:
    """pKi = 9 - log10(Ki_nM)."""
    if ki_nm is None:
        return None
    try:
        ki = float(ki_nm)
    except (TypeError, ValueError):
        return None
    if ki <= 0:
        return None
    return 9.0 - math.log10(ki)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    try:
        from scipy.stats import spearmanr

        rho, _ = spearmanr(xs, ys)
        if rho is None or (isinstance(rho, float) and math.isnan(rho)):
            return None
        return float(rho)
    except Exception:
        # Rank-based fallback without scipy
        def ranks(vals: list[float]) -> list[float]:
            order = sorted(range(len(vals)), key=lambda i: vals[i])
            r = [0.0] * len(vals)
            for rank, idx in enumerate(order):
                r[idx] = float(rank + 1)
            return r

        rx, ry = ranks(xs), ranks(ys)
        mean_x = sum(rx) / n
        mean_y = sum(ry) / n
        num = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
        den_x = math.sqrt(sum((a - mean_x) ** 2 for a in rx))
        den_y = math.sqrt(sum((b - mean_y) ** 2 for b in ry))
        if den_x == 0 or den_y == 0:
            return None
        return num / (den_x * den_y)


def smallmol_spearman(compounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Spearman ρ of pKi vs (-vina_wt). Null + note if n < 5."""
    pairs: list[tuple[str, float, float]] = []
    for c in compounds:
        ki = c.get("known_ki_nm")
        vina = c.get("vina_wt")
        pk = pKi(ki)
        if pk is None or vina is None:
            continue
        try:
            pairs.append((c["id"], pk, -float(vina)))
        except (TypeError, ValueError, KeyError):
            continue

    n = len(pairs)
    if n < 5:
        return {
            "smallmol_spearman_rho": None,
            "smallmol_n": n,
            "smallmol_note": (
                f"n too small for Spearman (n={n}, need ≥5 compounds with both "
                "known_ki_nm and vina_wt)."
            ),
        }

    rho = _spearman([p[1] for p in pairs], [p[2] for p in pairs])
    return {
        "smallmol_spearman_rho": None if rho is None else round(rho, 4),
        "smallmol_n": n,
        "smallmol_note": (
            "Spearman ρ of experimental pKi vs (−vina_wt). "
            "More negative Vina is better, so we correlate against −vina."
        ),
    }


def disagreements(
    compounds: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Large residual between docking rank and Ki rank (1 = best)."""
    usable: list[dict[str, Any]] = []
    for c in compounds:
        ki = c.get("known_ki_nm")
        vina = c.get("vina_wt")
        if ki is None or vina is None:
            continue
        try:
            usable.append({"id": c["id"], "ki": float(ki), "vina": float(vina)})
        except (TypeError, ValueError, KeyError):
            continue

    if not usable:
        return []

    by_vina = sorted(usable, key=lambda x: x["vina"])  # more negative better
    by_ki = sorted(usable, key=lambda x: x["ki"])  # lower Ki better
    vina_rank = {row["id"]: i + 1 for i, row in enumerate(by_vina)}
    ki_rank = {row["id"]: i + 1 for i, row in enumerate(by_ki)}

    rows: list[dict[str, Any]] = []
    for row in usable:
        cid = row["id"]
        vr, kr = vina_rank[cid], ki_rank[cid]
        residual = abs(vr - kr)
        note = ""
        if vr == 1 and kr == len(usable):
            note = "Best Vina; worst Ki. Do not promote from docking rank."
        elif residual >= 2:
            note = f"Vina rank {vr} vs Ki rank {kr}."
        rows.append(
            {
                "id": cid,
                "vina_rank": vr,
                "ki_rank": kr,
                "residual": residual,
                "note": note,
            }
        )

    rows.sort(key=lambda r: r["residual"], reverse=True)
    return rows[:top_k]


def design_deltas(
    designs: list[dict[str, Any]] | dict[str, Any],
    scores: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build design WT/mutant delta rows from designs + optional score map.

    scores keyed by design id: {"wt_score": float|None, "mutant_scores": {...}, "note": "..."}
    Designs may also carry wt_score / mutant_scores / interface_scores inline.
    """
    if isinstance(designs, dict):
        design_list = designs.get("designs") or []
    else:
        design_list = designs

    scores = scores or {}
    out: list[dict[str, Any]] = []
    for d in design_list:
        did = d.get("id")
        if not did:
            continue
        extra = scores.get(did, {})
        wt = extra.get("wt_score", d.get("wt_score"))
        mutants = extra.get("mutant_scores", d.get("mutant_scores") or d.get("interface_scores") or {})
        note = extra.get("note", d.get("delta_note", ""))
        if wt is None and not mutants and did not in scores:
            # Still emit a row so critic can see missing metrics
            note = note or "No WT/mutant interface scores available."
        out.append(
            {
                "id": did,
                "wt_score": wt,
                "mutant_scores": mutants if isinstance(mutants, dict) else {},
                "note": note,
            }
        )
    return out


def evaluate_smallmol_and_designs(
    smallmol: dict[str, Any] | None,
    designs: dict[str, Any] | list | None = None,
    design_scores: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    compounds = (smallmol or {}).get("compounds") or []
    spearman = smallmol_spearman(compounds)
    result = {
        "schema_version": "1.0",
        **spearman,
        "disagreements": disagreements(compounds),
        "design_deltas": design_deltas(designs or [], design_scores),
    }
    return result
