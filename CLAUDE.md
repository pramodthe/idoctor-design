# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

iDoctor Design is a closed-loop computational-biology pipeline for sotorasib-resistant KRAS G12C
(Y96D / H95D / R68S / Y96C): it gathers resistance evidence, generates miniprotein binder candidates,
folds/scores them, docks small-molecule controls, and runs an adversarial critic that prunes candidates.
Rejections are a first-class deliverable — the critic's "reject pile" is rendered in the UI on purpose.

FastAPI + LangGraph backend (`backend/`), Next.js trust UI (`frontend/`). Target PDB is `6OIM`
(KRAS G12C + sotorasib, ligand `MOV`); pocket geometry lives in `KNOWN_TARGETS` in `backend/config.py`.

## Commands

Python 3.12 venv at `.venv` (backend deps already installed). `PYTHONPATH=.` is required from the repo
root — `backend` is imported as a package and `backend/config.py` resolves paths from the repo root.

```bash
# API server on :8080
PYTHONPATH=. .venv/bin/python -m uvicorn backend.main:app --port 8080 --reload

# One pipeline run, no server (mode: fixture | replay | live)
PYTHONPATH=. .venv/bin/python -c \
  "from backend.pipeline import run_idoctor_design; print(run_idoctor_design('fixture')['run_id'])"

# Unit tests — pytest is NOT in backend/requirements.txt, install it first
PYTHONPATH=. .venv/bin/python -m pytest backend/tests -q
PYTHONPATH=. .venv/bin/python -m pytest \
  backend/tests/test_agent_loop.py::test_route_live_redesign_within_iteration_budget -q

# End-to-end smoke: runs the pipeline and asserts every JSON contract
PYTHONPATH=. .venv/bin/python scripts/e2e_smoke.py          # fixture only
PYTHONPATH=. .venv/bin/python scripts/e2e_smoke.py --api     # + HTTP API on :8080
PYTHONPATH=. .venv/bin/python scripts/e2e_smoke.py --live    # + partner APIs (needs keys)

# Frontend (:3000, talks to NEXT_PUBLIC_API_URL, default http://localhost:8080)
cd frontend && npm run dev
cd frontend && npx tsc --noEmit          # no lint script is configured
node scripts/e2e_ui_video.mjs            # Playwright walkthrough recording; needs :3000 + :8080
```

The tests in `backend/tests/` are plain pytest-style functions with no fixtures or conftest, so they
also run directly: `import backend.tests.test_agent_loop` and call the `test_*` functions.
There is no Python formatter/linter config (no pyproject/ruff/black) — match surrounding style.

## Three run modes are the central contract

Every agent branches on `state["mode"]`:

- **`fixture`** — copies `*.example.json` fixtures. Deterministic, no network, no keys.
- **`replay`** — re-reads an existing `data/runs/<run_id>/` and stays linear. No partner calls.
- **`live`** — calls Paperclip/Tamarind/Anthropic, and is the **only** mode where the critic→designer
  loop can fire (`route_after_critic` returns `experiment` immediately for non-live modes).

`provenance.json` records the mode plus a per-node verdict of `live | cached | fixture | skipped`.
`IDOCTOR_FAST=1` (`FAST_DEV`) skips the three slow network nodes in a live run (Tamarind folds,
literature search, critic LLM polish) — every skip is stamped, so a fast run is honestly degraded.

## The graph

`backend/pipeline.py` builds a `StateGraph` over seven nodes:

```
evidence → designer → structure → physics → evaluate → critic ─┬→ experiment → END
                          ▲                                     │
                          └───────── redesign (live only) ───────┘
```

Loop control lives in `backend/agents/graph_policy.py` (`route_after_critic`) and
`critic.py::_loop_decision`. It stops on promotion, an evidence gap, `MAX_NO_IMPROVEMENT_ROUNDS`
stagnation, or `MAX_DESIGN_ITERATIONS` (iteration 1 is the initial design, so the default 3 allows
two redesigns). Every round is archived to `iterations/round-NN/` plus `loop_history.json`.

Recoverable-vs-blocking is deliberate: `REDESIGNABLE_REASONS` are failures a new sequence can plausibly
fix; `EVIDENCE_BLOCKER_REASONS` (missing novelty/mutant evaluation) are *not*, because another sequence
must never substitute for a missing tool. Keep that split when adding reason codes.

## Run artifacts

`data/runs/<run_id>/` is the unit of output (gitignored, `run_id` = UTC timestamp + short uuid):
`spec.json`, `designs.json` + `designs.fasta`, `smallmol.json`, `eval.json`, `verdicts.json`,
`experiment.md`, `provenance.json`, `traces.json`, `loop_history.json`, `novel_designs.json`,
`paperclip_raw.json`, and the `structures/`, `docked/`, `iterations/` directories.

## Agent node contract

Each `backend/agents/*.py` exposes `run_<name>(state, progress_cb=None) -> dict` returning a *partial*
state update. A node must:

1. branch on `mode` and walk its fallback ladder (live tool → weaker local method → fixture);
2. write its artifact into `run_dir` and validate it via `backend/contracts/validate.py`;
3. set `provenance_nodes[AGENT_NAME]` to the honest source;
4. append a trace to `agent_traces` with the stable shape `{agent, agent_name, duration_seconds,
   model, input_summary, output_summary, steps[], tool_calls[], llm_calls[]}`.

Traces are the UI's lab log — `backend/agents/lab_log.py::flatten_traces` turns `steps`/`tool_calls`/
`output_summary` into rendered events, and `emit()` streams them live through `progress_cb`. A new node
also needs registering in `pipeline.py` (node, edge, `AGENT_DISPLAY`) and in `main.py::AGENT_NAMES`.

## Provenance honesty is a hard invariant

This is the repo's dominant rule and the reason for a lot of otherwise-odd code. Do not loosen it:

- `designer.py` reads `meta.design_engine` off the campaign file instead of assuming BindCraft, and
  `_honest_bindcraft_flags` clears `passed_bindcraft_filters` unless the engine is exactly `bindcraft`.
- `critic.py`'s `_trusted_structure_method` / `_trusted_novelty_method` / `_trusted_mutant_evaluation`
  gate promotion. Heuristic, fixture, proxy, or unknown methods can reach `hold` but never `promote`.
- `structure.py::_already_folded` refuses to let locally-estimated pLDDT/ipTM suppress a real fold job.
- `evaluator.py`'s design deltas are an explicitly-labelled sequence-composition proxy, not physics.
- The frontend shows a demo-data banner whenever any node is `fixture` (`isDemoData` in `lib/api.ts`).

When you add a metric or scoring path, decide which side of trusted/untrusted it sits on and register it
in the right helper — don't widen an existing gate to make a candidate pass.

## Contracts and fixtures

`backend/contracts/validate.py` is hand-written required-key checking, not JSON Schema. Two things bite:
new verdict reason codes must be added to its `reason_codes` allowlist or `validate_verdicts` raises,
and adding a required key to an artifact means updating the fixtures too.

`FIXTURES_DIR` (in `config.py`) prefers `spec/fixtures/` and falls back to `frontend/public/fixtures/`.
`spec/` has been deleted from the working tree (still present in git HEAD), so the frontend copy is the
live one and anything hardcoding `spec/fixtures/...` breaks — including `scripts/e2e_smoke.py --live`
and the `spec/` links in `README.md`, `frontend/README.md`, and `design/README.md`.

## LLM usage

All Claude calls go through `backend/agents/llm.py` (`call_llm`, `call_llm_with_tools`), model from
`ANTHROPIC_MODEL` (default `claude-sonnet-5`). Sonnet-5/Opus-5 reject `temperature`, so
`_sonnet5_or_opus5` strips it — keep that guard when changing models.

LLMs write prose and choose search queries; they never decide verdicts (all rule-based in `critic.py`).
Evidence ids returned by the model are re-checked against actual tool output via
`paperclip.source_id_allowed` / `allowlist_from_hits`, so a hallucinated PMID/NCT is dropped rather
than cited. Keep prompts explicit about not inventing Ki values, PDB ids, or sequences.

## External tools

- **Paperclip** (`tools/paperclip_mcp.py`, `tools/paperclip.py`): live evidence binds Paperclip MCP
  tools onto a LangGraph ReAct agent; the CLI wrapper and Europe PMC (`tools/literature.py`) are
  fallbacks. There is no REST search endpoint we own — don't invent one.
- **Tamarind** (`tools/tamarind.py`): follows `/tools → validate-job → submit-job → poll → result`.
  Tool names come from `GET /tools`; never hardcode a job type that isn't in the response. BindCraft
  campaigns run for hours, so `designer.py` picks up a finished campaign from
  `data/bindcraft_designs/designs.json` rather than calling it inline.
- **Docking**: `simulation/docking.py` lazily imports `vina`/`meeko`/`pdbfixer` and shells out to
  `obabel`. `vina` is **not** installed in `.venv`, so `GET /api/dock/...` currently 500s; the pipeline
  instead reads measured scores from `data/docking/vina_scores.json` (the one committed docking
  artifact) in `agents/physics_control.py`.
- `design/` and `tools/proto_runner.py` are the abandoned Proto/Modal path. `USE_PROTO` stays `0`.

## API and job model

`main.py` keeps runs in an in-memory `jobs` dict (no persistence, cleared on shutdown). `POST /api/run`
returns a `job_id`; the frontend polls `GET /api/results/{job_id}` every 500 ms (an SSE endpoint exists
at `/api/status/{job_id}` but `lib/api.ts` uses polling). `GET /api/runs/latest` is what the UI loads on
boot and only accepts run dirs containing `provenance.json` + `spec.json` + `designs.json`.
`/api/binder-pdb` and `/api/runs/{run_id}/file/{name}` are path-guarded to the repo root — keep those
checks if you touch them.

## Frontend notes

- Next 16 / React 19 / Tailwind v4 (`@tailwindcss/postcss`), 3Dmol + reactflow. `frontend/AGENTS.md`
  (loaded via `frontend/CLAUDE.md`) warns that this Next version is newer than training data — read
  `node_modules/next/dist/docs/` before writing Next-specific code.
- One page (`src/app/page.tsx`) driving `AppShell` sections. `src/lib/types.ts` mirrors the backend
  contracts by hand, so contract changes are always a two-file edit.
- Boot overrides: `?run=live|fixture|none`. `runWithFixtureFallback` silently falls back to
  `/fixtures/*.example.json` when the API is unreachable, so a UI run that "succeeds" may be entirely
  local fixtures — read the provenance banner before trusting a screenshot.

## Coordination and commits

GitHub issues are the coordination document. `COORDINATION.md` is generated by
`scripts/sync_coordination.py` (cron in `.github/workflows/coordination.yml`) — don't hand-edit it.
Commit subjects here are imperative sentences describing the behaviour change
("Report the real design engine instead of assuming BindCraft"), not conventional-commit prefixes.
