# Live mode runbook

iDoctor Design `live` mode is prize-ready **without** Paperclip / Tamarind / Anthropic keys when public literature endpoints are reachable.

**Stage walkthrough default is `replay`**, not `live`. Replay reuses `data/runs/<id>` with no partner calls and turns the demo-data banner on.

## What works without keys

| Node | Live behavior |
|---|---|
| **Evidence** | Europe PMC + ClinicalTrials.gov via `backend/tools/literature.py`. Real PMIDs / NCT ids only — never invented. Falls back / merges fixture carefully if harvest is thin; `provenance` is `live` when any real paper/trial id is attached. |
| **Designer** | If `data/bindcraft_designs/designs.json` exists → BindCraft (RFdiffusion + ProteinMPNN + AF2), `meta.design_engine=bindcraft`. Else local `sequence_design` (≥8 novel sequences, pocket-biased motifs) with `design_engine=sequence_design`. **Not** RFdiffusion unless BindCraft is on disk. |
| **Structure** | If `TAMARIND_API_KEY` missing: `heuristic_v1` fold metrics. README under `structures/` states heuristic vs Tamarind. |
| **Physics** | Enriches `smallmol.json` with all `KRAS_COMPOUNDS` + known Ki; Vina scores reused from fixture where ids match → node `cached` (honest). |

Raw harvest is written to `data/runs/<run_id>/paperclip_raw.json` as:

```json
{ "europepmc": [...], "clinicaltrials": [...], "queries": [...] }
```

## Optional keys (upgrade path)

Set when available (see sibling runbooks):

| Variable | Effect |
|---|---|
| `PAPERCLIP_API_KEY` + `paperclip` CLI (optional `PAPERCLIP_BASE_URL`) | Preferred literature path before Europe PMC fallback |
| `TAMARIND_API_KEY` | Real fold/complex jobs **and** BindCraft `validate-job` / submit. `is_configured()` gates the client. |
| `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL=claude-sonnet-5` | Critic / experiment LLM prose |
| Benchling | **Ignored** — Monday card is markdown only |

`USE_PROTO` stays `0`. `design/proto_binder.py` is leftover and is not on the live designer path.

Also: `IDOCTOR_DESIGN_DEFAULT_MODE=replay` for stage. `IDOCTOR_DESIGN_LIVE_DESIGN=1` only if you intend a live design node.

## Honesty rules

- **Never claim BindCraft / RFdiffusion** if `meta.design_engine` is `sequence_design` or `fixture`.
- **Never claim Tamarind / AlphaFold** if `fold_method` is `heuristic_v1`.
- **Never invent PMIDs** — only IDs returned by Europe PMC, ClinicalTrials.gov, or Paperclip.
- `boltz2_affinity` stays `null` unless measured.

## Tamarind `{type, settings}` seam (Ryan / designspec.py)

```python
from backend.tools.tamarind import validate_job_spec
normalized = validate_job_spec("bindcraft", settings)
```

HTTP: `POST /api/tamarind/validate-job` with body `{"type": "...", "settings": {...}}`. Validation only — does not submit a job.

## Smoke test

```bash
PYTHONPATH=/workspace python -c "from backend.pipeline import run_idoctor_design; r=run_idoctor_design('live'); print(r['provenance']); print(r['designs'].get('meta')); print([(m['id'], m['sources'][0]['id']) for m in r['scientific_spec']['mutations'][:4]]); print(r['designs']['designs'][0]['provenance'], r['designs']['designs'][0]['sequence'][:20]); print('fixture_seq_collision', r['designs']['designs'][0]['sequence'] in open('spec/fixtures/designs.example.fasta').read())"
```

Expect: `nodes` mostly `live` (physics may be `cached`), real PMIDs, `meta.design_engine` is `sequence_design` unless a BindCraft campaign is on disk, at least one **promote** and one **reject**, Monday experiment card for the top promote.

Fixture mode stays unchanged: `run_idoctor_design('fixture')`. Replay: `run_idoctor_design('replay')`.

## Honesty labels in the UI

- Literature quotes must contain the mutation token (enforced in harvest).
- Design table Engine column must match `meta.design_engine`.
- Structure/interface scores may be `heuristic_v1` until Tamarind keys are set — say so in the demo.
- `frontend/src/components/AgentStatusPanel.tsx` and `frontend/src/app/page.tsx` show a `demo-banner` when mode is fixture/replay or any node is fixture.
