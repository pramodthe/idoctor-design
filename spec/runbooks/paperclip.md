# Paperclip runbook

Redeem: https://paperclip.gxl.ai/redeem?code=HACKATHON2026  
Docs: https://paperclip.gxl.ai/docs  

Paperclip is **CLI / SDK / MCP** — not a custom REST base URL you invent in `.env`.

```bash
curl -fsSL https://paperclip.gxl.ai/install.sh | bash
paperclip config
# or non-interactive:
export PAPERCLIP_API_KEY='gxl_...'   # from Paperclip web app → API keys
```

Optional (only for local/dev servers):

```bash
export PAPERCLIP_BASE_URL=http://localhost:8002   # Paperclip's own env name
```

MCP (optional, for Cursor agents): `https://paperclip.gxl.ai/mcp` with header `X-API-Key`.

## Suggested first queries

```bash
paperclip search "KRAS G12C sotorasib resistance Y96D"
paperclip search "KRAS G12C H95 R68 resistance mutation"
```

Then `map` / `reduce` (or SDK) to fill `mutations[].sources` in `spec.json`.

Never invent a PMID/PMC/trial ID. If extraction is unsure, set `effect_on_sotorasib` to `unclear`.

## iDoctor Design wiring

`backend/tools/paperclip.py` shells out to `paperclip search` when the CLI + key are present.
If not, evidence falls back to Europe PMC + ClinicalTrials.gov (still live PMIDs/NCTs).

## Output

Write `data/runs/<run_id>/paperclip_raw.json` and normalized `spec.json` per `DATA_CONTRACTS.md`.
