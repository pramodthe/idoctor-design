# Live mode runbook

iDoctor Design `live` mode is prize-ready **without** Paperclip / Tamarind / Anthropic / Modal keys when public literature endpoints are reachable.

## What works without keys

| Node | Live behavior |
|---|---|
| **Evidence** | Europe PMC + ClinicalTrials.gov via `backend/tools/literature.py`. Real PMIDs / NCT ids only — never invented. Falls back / merges fixture carefully if harvest is thin; `provenance` is `live` when any real paper/trial id is attached. |
| **Designer** | Local `sequence_design` generator (≥8 novel sequences, pocket-biased motifs). **Not** Proto-on-Modal. |
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
| `TAMARIND_API_KEY` | Real structure fold/complex jobs (not docking) via Tamarind |
| `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL=claude-sonnet-5` | Critic / experiment LLM prose |
| Benchling | **Ignored** — Monday card is markdown only |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` + Proto | Real Proto binder when packages installed and `USE_PROTO=1` (`design/proto_binder.py`) |

Also: `--live` on `design/kras_g12c.py` or `IDOCTOR_DESIGN_LIVE_DESIGN=1`.

## Honesty rules

- **Never claim Proto Modal** if designs came from `live_local_generator` / sequence_design.
- **Never claim Tamarind / AlphaFold** if `fold_method` is `heuristic_v1`.
- **Never invent PMIDs** — only IDs returned by Europe PMC, ClinicalTrials.gov, or Paperclip.

## Smoke test

```bash
PYTHONPATH=/workspace python -c "from backend.pipeline import run_idoctor_design; r=run_idoctor_design('live'); print(r['provenance']); print([(m['id'], m['sources'][0]['id']) for m in r['scientific_spec']['mutations'][:4]]); print(r['designs']['designs'][0]['provenance'], r['designs']['designs'][0]['sequence'][:20]); print('fixture_seq_collision', r['designs']['designs'][0]['sequence'] in open('spec/fixtures/designs.example.fasta').read())"
```

Expect: `nodes` mostly `live` (physics may be `cached`), real PMIDs, `provenance=live` designs, at least one **promote** and one **reject**, Monday experiment card for the top promote.

Fixture mode stays unchanged: `run_idoctor_design('fixture')`.

## Honesty labels in the UI

- Literature quotes must contain the mutation token (enforced in harvest).
- Designs from `live_local_generator` are not Proto-on-Modal.
- Structure/interface scores may be `heuristic_v1` until Tamarind keys are set — say so in the demo.
