"""Public evidence harvester — Europe PMC + ClinicalTrials.gov (no API keys)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO_ROOT / "spec" / "fixtures" / "spec.example.json"

EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CLINICALTRIALS_STUDIES = "https://clinicaltrials.gov/api/v2/studies"
REQUEST_TIMEOUT = 30

FROZEN_MUTATIONS = frozenset({"Y96D", "H95D", "R68S", "Y96C"})
AA_LETTERS = set("ACDEFGHIKLMNPQRSTVWY")
MUTATION_RE = re.compile(r"\b([A-Z]\d{2,4}[A-Z])\b")
# Prefer Switch-II / pocket-style mutations; still allow any AA#AA near KRAS context.
POCKETISH_RE = re.compile(
    r"\b((?:Y96|H95|R68|G12|Q61|A59|D69)[A-Z]|[A-Z]\d{2,3}[A-Z])\b"
)
PDB_RE = re.compile(r"\b([1-9][A-Za-z0-9]{3})\b")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

DRIVER_ALLELES = frozenset({"G12C", "G12D", "G12V", "G12R", "G12A", "G13D", "Q61H", "Q61L", "Q61R"})


def _valid_mutation_token(mut: str) -> bool:
    """True for canonical AA-position-AA tokens (e.g. Y96D), not DOI fragments."""
    if not mut or not MUTATION_RE.fullmatch(mut):
        return False
    if mut[0] not in AA_LETTERS or mut[-1] not in AA_LETTERS:
        return False
    if mut in DRIVER_ALLELES:
        return False
    return True

DEFAULT_QUERIES = [
    'KRAS G12C sotorasib resistance Y96D',
    'KRAS G12C "Y96D" OR "H95D" OR "R68S" OR "Y96C"',
    'KRAS G12C adagrasib resistance mutation',
    'KRAS Switch II pocket resistance sotorasib',
    '"Y96D" KRAS (sotorasib OR adagrasib)',
    '"H95D" KRAS resistance',
    '"R68S" KRAS sotorasib',
    '"Y96C" KRAS resistance',
]

LOSS_KEYWORDS = ("loss", "abolished", "resistant", "resistance", "escape", "abrogate")
REDUCED_KEYWORDS = ("reduced", "attenuated", "decreased", "weaker", "partial")


def _get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 — public APIs may flake
        print(f"literature: GET failed {url}: {exc}")
        return None


def search_europepmc(query: str, page_size: int = 20) -> list[dict]:
    """Search Europe PMC (format=json, resultType=core). No API key required."""
    data = _get_json(
        EUROPEPMC_SEARCH,
        {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": page_size,
        },
    )
    if not data:
        return []
    results = data.get("resultList", {}).get("result") or []
    out: list[dict] = []
    for hit in results:
        if not isinstance(hit, dict):
            continue
        row = {
            "pmid": hit.get("pmid"),
            "title": hit.get("title"),
            "abstractText": hit.get("abstractText"),
            "doi": hit.get("doi"),
            "journalTitle": hit.get("journalTitle"),
            "pmcid": hit.get("pmcid"),
            "id": hit.get("id"),
            "source": hit.get("source"),
        }
        # Drop empty shells
        if row.get("pmid") or row.get("title") or row.get("pmcid") or row.get("id"):
            out.append(row)
    return out


def search_clinicaltrials(query: str, page_size: int = 10) -> list[dict]:
    """Search ClinicalTrials.gov API v2. No API key required."""
    data = _get_json(
        CLINICALTRIALS_STUDIES,
        {
            "query.term": query,
            "pageSize": page_size,
            "format": "json",
        },
    )
    if not data:
        return []
    out: list[dict] = []
    for study in data.get("studies") or []:
        if not isinstance(study, dict):
            continue
        proto = study.get("protocolSection") or {}
        ident = proto.get("identificationModule") or {}
        desc = proto.get("descriptionModule") or {}
        nct = ident.get("nctId")
        title = ident.get("briefTitle")
        summary = desc.get("briefSummary")
        if nct or title:
            out.append(
                {
                    "nctId": nct,
                    "briefTitle": title,
                    "briefSummary": summary,
                }
            )
    return out


def _strip_xml(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_europepmc_fulltext(pmcid: str | None) -> str:
    if not pmcid:
        return ""
    try:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            return ""
        return _strip_xml(resp.text)
    except Exception:  # noqa: BLE001
        return ""


def extract_mutations(text: str) -> list[str]:
    """Regex for AA mutations (Y96D, H95D, …). Prefer KRAS/sotorasib neighborhood.

    Always includes members of FROZEN_MUTATIONS when mentioned anywhere in text.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()

    # Frozen set: include whenever mentioned (case-sensitive canonical tokens)
    for mut in sorted(FROZEN_MUTATIONS):
        if mut in text and mut not in seen:
            seen.add(mut)
            found.append(mut)

    # Prefer matches near KRAS / sotorasib / adagrasib / resistance context
    # Do NOT use IGNORECASE on the mutation token itself (avoids DOI fragments like 0b013e).
    for m in re.finditer(
        r"(?:KRAS|sotorasib|adagrasib|resistance|Switch\s*II).{0,80}"
        r"([A-Z]\d{2,4}[A-Z])"
        r"|([A-Z]\d{2,4}[A-Z]).{0,80}"
        r"(?:KRAS|sotorasib|adagrasib|resistance|Switch\s*II)",
        text,
    ):
        mut = m.group(1) or m.group(2)
        if not mut or mut in seen or not _valid_mutation_token(mut):
            continue
        seen.add(mut)
        found.append(mut)

    # Pocket-ish fallback scan
    for mut in POCKETISH_RE.findall(text):
        if mut in seen or not _valid_mutation_token(mut):
            continue
        seen.add(mut)
        found.append(mut)

    return found


def _effect_from_text(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in LOSS_KEYWORDS):
        return "loss"
    if any(k in low for k in REDUCED_KEYWORDS):
        return "reduced"
    return "unclear"


def _first_sentence_mentioning(text: str, needle: str) -> str | None:
    if not text or not needle:
        return None
    for sent in SENTENCE_SPLIT.split(text.replace("\n", " ")):
        if needle in sent:
            quote = sent.strip()
            if len(quote) > 280:
                quote = quote[:277] + "..."
            return quote
    return None


def _title_slice(title: str | None, max_len: int = 160) -> str:
    t = (title or "").strip() or "Untitled"
    return t if len(t) <= max_len else t[: max_len - 3] + "..."


def _paper_blob(paper: dict, fulltext: str = "") -> str:
    parts = [
        paper.get("title") or "",
        paper.get("abstractText") or "",
        fulltext,
    ]
    return "\n".join(p for p in parts if p)


def _paper_source(paper: dict, mutation: str, fulltext: str = "") -> dict | None:
    """Build a source dict from a real Europe PMC hit. Never invents PMIDs."""
    pmid = paper.get("pmid")
    if not pmid:
        return None  # Prefer real PMIDs only for paper sources
    blob = _paper_blob(paper, fulltext)
    quote = _first_sentence_mentioning(blob, mutation)
    if not quote:
        # Only attribute if mutation appears somewhere, or use title slice when
        # the hit was returned for a mutation-specific harvest and title exists.
        if mutation not in blob:
            return None
        quote = _title_slice(paper.get("title"))
    return {
        "kind": "paper",
        "id": str(pmid),
        "title": paper.get("title") or f"PMID {pmid}",
        "quote": quote,
        "origin": "live",
    }


def _trial_source(trial: dict, mutation: str) -> dict | None:
    nct = trial.get("nctId")
    if not nct:
        return None
    blob = "\n".join(
        filter(None, [trial.get("briefTitle") or "", trial.get("briefSummary") or ""])
    )
    quote = _first_sentence_mentioning(blob, mutation)
    if mutation not in blob and not quote:
        # Allow title slice only if mutation string appears (strict)
        return None
    if not quote:
        quote = _title_slice(trial.get("briefTitle"))
    return {
        "kind": "trial",
        "id": str(nct),
        "title": trial.get("briefTitle") or nct,
        "quote": quote,
        "origin": "live",
    }


def _find_pdb_in_text(text: str) -> str | None:
    # Avoid matching common short words; require known KRAS-ish or explicit PDB mention
    for m in re.finditer(r"(?:PDB(?:\s*ID)?[:\s#]*)([1-9][A-Za-z0-9]{3})\b", text, re.I):
        return m.group(1).upper()
    return None


def dump_paperclip_raw(
    europepmc: list[dict],
    clinicaltrials: list[dict],
    queries: list[str],
) -> dict[str, Any]:
    """Return a paperclip_raw.json-shaped dump."""
    return {
        "europepmc": europepmc,
        "clinicaltrials": clinicaltrials,
        "queries": queries,
    }


def harvest_raw(
    queries: list[str] | None = None,
    epmc_page_size: int = 20,
    ct_page_size: int = 10,
) -> tuple[list[dict], list[dict], list[str]]:
    """Run public searches; dedupe papers by pmid/id and trials by nctId."""
    queries = list(queries or DEFAULT_QUERIES)
    papers: list[dict] = []
    trials: list[dict] = []
    seen_papers: set[str] = set()
    seen_trials: set[str] = set()

    for q in queries:
        for p in search_europepmc(q, page_size=epmc_page_size):
            key = str(p.get("pmid") or p.get("pmcid") or p.get("id") or "")
            if not key or key in seen_papers:
                continue
            seen_papers.add(key)
            papers.append(p)
        for t in search_clinicaltrials(q, page_size=ct_page_size):
            key = str(t.get("nctId") or "")
            if not key or key in seen_trials:
                continue
            seen_trials.add(key)
            trials.append(t)
    return papers, trials, queries


def build_live_spec(
    raw_papers: list[dict],
    raw_trials: list[dict],
    base_fixture_path: str | Path | None = None,
) -> dict:
    """Normalize public harvest into a spec.json matching DATA_CONTRACTS / fixture schema."""
    fixture_path = Path(base_fixture_path) if base_fixture_path else DEFAULT_FIXTURE
    fixture: dict[str, Any] = {}
    if fixture_path.is_file():
        with fixture_path.open() as f:
            fixture = json.load(f)

    # Optionally pull full text for a bounded number of PMC papers to recover quotes
    fulltexts: dict[str, str] = {}
    fetch_attempts = 0
    max_fetches = 20
    store_budget = 16

    def _want_fulltext(paper: dict) -> bool:
        abs_blob = _paper_blob(paper)
        if any(m in abs_blob for m in FROZEN_MUTATIONS):
            return True
        title = (paper.get("title") or "").lower()
        if any(x in title for x in ("resistance", "y96", "h95", "r68", "sotorasib", "adagrasib")):
            return True
        return bool(paper.get("pmcid"))

    prioritized = sorted(
        raw_papers,
        key=lambda p: (0 if _want_fulltext(p) else 1, 0 if p.get("pmid") else 1),
    )
    for paper in prioritized:
        if store_budget <= 0 or fetch_attempts >= max_fetches:
            break
        pmcid = paper.get("pmcid")
        pmid = paper.get("pmid")
        if not pmcid or not pmid:
            continue
        fetch_attempts += 1
        ft = _fetch_europepmc_fulltext(pmcid)
        if not ft:
            continue
        if any(m in ft for m in FROZEN_MUTATIONS) or any(
            m in _paper_blob(paper) for m in FROZEN_MUTATIONS
        ):
            fulltexts[str(pmid)] = ft
            store_budget -= 1
        elif store_budget > 12:
            fulltexts[str(pmid)] = ft
            store_budget -= 1

    # mutation_id -> list of live sources
    mut_sources: dict[str, list[dict]] = {}
    mut_contexts: dict[str, list[str]] = {}

    for paper in raw_papers:
        pmid = paper.get("pmid")
        ft = fulltexts.get(str(pmid), "") if pmid else ""
        blob = _paper_blob(paper, ft)
        muts = extract_mutations(blob)
        # Also allow frozen mutations if present in fulltext only
        for mut in muts:
            src = _paper_source(paper, mut, ft)
            if not src:
                continue
            mut_sources.setdefault(mut, [])
            if not any(s["id"] == src["id"] and s["kind"] == src["kind"] for s in mut_sources[mut]):
                mut_sources[mut].append(src)
                mut_contexts.setdefault(mut, []).append(src.get("quote") or "")

    for trial in raw_trials:
        blob = "\n".join(
            filter(None, [trial.get("briefTitle") or "", trial.get("briefSummary") or ""])
        )
        for mut in extract_mutations(blob):
            src = _trial_source(trial, mut)
            if not src:
                continue
            mut_sources.setdefault(mut, [])
            if not any(s["id"] == src["id"] and s["kind"] == src["kind"] for s in mut_sources[mut]):
                mut_sources[mut].append(src)
                mut_contexts.setdefault(mut, []).append(src.get("quote") or "")

    # Prefer frozen mutations that actually have live mentions; then other found muts
    ordered_ids: list[str] = []
    for mut in ["Y96D", "H95D", "R68S", "Y96C"]:
        if mut in mut_sources:
            ordered_ids.append(mut)
    for mut in sorted(mut_sources.keys()):
        if mut not in ordered_ids:
            ordered_ids.append(mut)
    # Cap secondary mutations so the spec stays focused
    ordered_ids = ordered_ids[:8]

    live_mutation_count = sum(1 for m in ordered_ids if mut_sources.get(m))

    # If thin, merge carefully with fixture mutations (mark origin)
    fixture_muts = {
        m["id"]: m for m in (fixture.get("mutations") or []) if isinstance(m, dict) and m.get("id")
    }

    mutations_out: list[dict] = []
    used_ids: set[str] = set()

    def _add_live_mutation(mid: str) -> None:
        if mid in used_ids:
            return
        sources = mut_sources.get(mid) or []
        if not sources:
            return
        ctx = " ".join(mut_contexts.get(mid) or [])
        effect = _effect_from_text(ctx)
        # Clean origin field for contract consumers (keep as extra; also mirror in notes)
        clean_sources = []
        for s in sources[:3]:
            clean_sources.append(
                {
                    "kind": s["kind"],
                    "id": s["id"],
                    "title": s["title"],
                    "quote": s["quote"],
                    "origin": "live",
                }
            )
        mutations_out.append(
            {
                "id": mid,
                "effect_on_sotorasib": effect,
                "notes": (
                    f"Live harvest from Europe PMC / ClinicalTrials.gov. "
                    f"Effect inferred as '{effect}' from nearby keywords; confirm before clinical claims."
                ),
                "sources": clean_sources,
            }
        )
        used_ids.add(mid)

    for mid in ordered_ids:
        _add_live_mutation(mid)

    # If still thinner than the classic four, merge fixture entries that were
    # actually mentioned in harvested text OR keep fixture fill-ins marked as fixture.
    combined_corpus = "\n".join(
        _paper_blob(p, fulltexts.get(str(p.get("pmid") or ""), "")) for p in raw_papers
    )
    combined_corpus += "\n" + "\n".join(
        (t.get("briefTitle") or "") + "\n" + (t.get("briefSummary") or "") for t in raw_trials
    )

    if len(mutations_out) < 2:
        for mid in ["Y96D", "H95D", "R68S", "Y96C"]:
            if mid in used_ids:
                continue
            if mid not in combined_corpus:
                # Only include fixture fill when text does not mention it — last resort
                fm = fixture_muts.get(mid)
                if not fm:
                    continue
                sources = []
                for s in fm.get("sources") or []:
                    sources.append(
                        {
                            "kind": s.get("kind", "paper"),
                            "id": s.get("id", f"FIXTURE-{mid}"),
                            "title": s.get("title", "Fixture placeholder"),
                            "quote": s.get("quote", ""),
                            "origin": "fixture",
                        }
                    )
                mutations_out.append(
                    {
                        "id": mid,
                        "effect_on_sotorasib": fm.get("effect_on_sotorasib", "unclear"),
                        "notes": (
                            (fm.get("notes") or "")
                            + " [Merged from fixture — not confirmed in this live harvest.]"
                        ).strip(),
                        "sources": sources,
                    }
                )
                used_ids.add(mid)
            else:
                # Mentioned in corpus but no PMID source built — try harder with title-only papers skipped
                pass

    # Ensure at least one mutation
    if not mutations_out and fixture_muts:
        for mid, fm in fixture_muts.items():
            sources = []
            for s in fm.get("sources") or []:
                sources.append({**s, "origin": "fixture"})
            mutations_out.append(
                {
                    "id": mid,
                    "effect_on_sotorasib": fm.get("effect_on_sotorasib", "unclear"),
                    "notes": (fm.get("notes") or "") + " [Fixture fallback.]",
                    "sources": sources,
                }
            )

    live_with_real_id = 0
    for m in mutations_out:
        for s in m.get("sources") or []:
            sid = str(s.get("id") or "")
            origin = s.get("origin")
            if origin == "live" and sid and not sid.startswith("FIXTURE"):
                live_with_real_id += 1
                break

    # Prefer: provenance live when any real pmid/NCT attached
    if live_with_real_id >= 1:
        provenance = "live"
    elif live_mutation_count >= 2:
        provenance = "live"
    else:
        provenance = "fixture"

    evidence_quality = {
        "live_mutations_with_sources": live_with_real_id,
        "harvested_papers": len(raw_papers),
        "harvested_trials": len(raw_trials),
    }

    # failed small molecules — attach real paper sources when present
    failed = []
    for drug_id, drug_name, why in [
        (
            "sotorasib",
            "Sotorasib (Lumakras)",
            "Approved and active on G12C, but resistance mutations in the Switch II pocket limit durability.",
        ),
        (
            "adagrasib",
            "Adagrasib (Krazati)",
            "Second approved covalent G12C inhibitor; overlapping resistance liabilities.",
        ),
    ]:
        sources = []
        for paper in raw_papers:
            blob = _paper_blob(paper, fulltexts.get(str(paper.get("pmid") or ""), ""))
            if drug_id.lower() not in blob.lower() and drug_name.split()[0].lower() not in blob.lower():
                continue
            pmid = paper.get("pmid")
            if not pmid:
                continue
            quote = _first_sentence_mentioning(blob, drug_name.split()[0]) or _title_slice(
                paper.get("title")
            )
            sources.append(
                {
                    "kind": "paper",
                    "id": str(pmid),
                    "title": paper.get("title") or f"PMID {pmid}",
                    "quote": quote,
                    "origin": "live",
                }
            )
            if len(sources) >= 2:
                break
        if not sources:
            # Fall back to fixture sources marked fixture
            for fm in fixture.get("failed_small_molecules") or []:
                if fm.get("id") == drug_id:
                    for s in fm.get("sources") or []:
                        sources.append({**s, "origin": "fixture"})
        failed.append(
            {
                "id": drug_id,
                "name": drug_name,
                "why_not_enough": why,
                "sources": sources[:2],
            }
        )

    # Structures
    structures = [
        {
            "pdb_id": "6OIM",
            "label": "KRAS G12C with ARS-1620 (Switch II pocket)",
            "kind": "wt_g12c",
            "notes": "Default receptor for the control docking arm.",
        }
    ]
    for mid in [m["id"] for m in mutations_out[:4]]:
        found_pdb = None
        for paper in raw_papers:
            blob = _paper_blob(paper, fulltexts.get(str(paper.get("pmid") or ""), ""))
            if mid not in blob:
                continue
            found_pdb = _find_pdb_in_text(blob)
            if found_pdb and found_pdb.upper() != "6OIM":
                found_pdb = found_pdb.upper()
                break
            found_pdb = None
        structures.append(
            {
                "pdb_id": found_pdb,
                "label": f"{mid} complex",
                "kind": "mutant",
                "mutation_id": mid,
                "notes": (
                    f"PDB {found_pdb} mentioned near {mid}."
                    if found_pdb
                    else "modeled_or_missing — no mutant PDB id found in harvested text."
                ),
            }
        )

    hypothesis = fixture.get("hypothesis") or (
        "Switch II small-molecule drugs that work on KRAS G12C lose binding when pocket "
        "residues such as Y96 change; a designed miniprotein that uses a larger surface can "
        "keep contacts outside the sotorasib epitope and should be tested on Y96D, not only "
        "on wild-type G12C."
    )

    spec = {
        "schema_version": "1.0",
        "provenance": provenance,
        "evidence_quality": evidence_quality,
        "hypothesis": hypothesis,
        "target": fixture.get("target")
        or {
            "name": "KRAS G12C",
            "gene": "KRAS",
            "pdb_id": "6OIM",
            "uniprot_id": "P01116",
            "clinical_hook": (
                "Sotorasib (Lumakras) is approved for KRAS G12C, but resistance mutations "
                "in the pocket cause relapse within months for many patients."
            ),
        },
        "pocket_residues": fixture.get("pocket_residues")
        or ["Cys12", "Asp69", "His95", "Tyr96"],
        "success_bars": fixture.get("success_bars")
        or {
            "max_pdb_identity": 0.7,
            "min_plddt": 70,
            "require_mutant_score": True,
        },
        "mutations": mutations_out,
        "failed_small_molecules": failed,
        "structures": structures,
    }
    return spec


def gather_live_evidence(
    queries: list[str] | None = None,
) -> tuple[dict, dict]:
    """Convenience: harvest + build spec + raw dump."""
    papers, trials, qs = harvest_raw(queries)
    spec = build_live_spec(papers, trials)
    raw = dump_paperclip_raw(papers, trials, qs)
    return spec, raw
