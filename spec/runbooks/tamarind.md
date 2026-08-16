# Tamarind runbook

Redeem: https://app.tamarind.bio/code/gxl-hackathon-26  
API docs: https://app.tamarind.bio/api-docs  
Key: from https://app.tamarind.bio/app/results — store as `TAMARIND_API_KEY`.

Budget: **100 jobs**. Smoke-test ≤ 3 jobs. Cache everything under `data/runs/<run_id>/structures/`.

`is_configured()` is true only when `TAMARIND_API_KEY` is set. `/api/health` returns `tamarind_configured` as a boolean (never the key).

## Jobs we use

| type | When | Inline in a UI click? |
|---|---|---|
| fold tools (`esmfold`, `alphafold`, …) | Structure agent | Yes, with poll timeout |
| `bindcraft` | Designer, **only** from a finished campaign on disk | **No** — hours-long. Submit separately, pick up `data/bindcraft_designs/designs.json` |
| `autodock-vina` | Optional Tamarind Vina | Separate from local CPU Vina |

Prefer: one fold per serious design, then complex/dock only for the critic’s shortlist.

Map tool metrics to `plddt` / `iptm` / `pdb_path` without renaming them to binding affinity. `boltz2_affinity` stays `null` unless measured.

## `{type, settings}` seam (Ryan `designspec.py`)

Same body as Tamarind `POST /validate-job`. Validation only — does not submit.

Python:

```python
from backend.tools.tamarind import validate_job_spec
normalized = validate_job_spec("bindcraft", settings)
```

HTTP:

```http
POST /api/tamarind/validate-job
{"type": "bindcraft", "settings": { ... }}
```

Returns `{ "valid": true, "type": "...", "normalized": { ... } }`.
