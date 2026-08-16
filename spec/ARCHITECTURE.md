# Architecture — iDoctor Design

This is the implementer view of the brief. If a diagram and `REQUIREMENTS.md` disagree, the requirement wins.

---

## Old system (legacy)

```text
Target ID → Vina + OpenMM → Rank vs FDA drug → Lipinski/PAINS → LLM brief
```

Linear. Hardcoded biology. Docking is the answer. Four diseases.

Keep the Vina/RDKit/viewer code. Do not keep this as the user-facing story.

---

## New system

```text
                    ┌────────────┐
                    │  Question  │  frozen hypothesis (Workstream 1)
                    └─────┬──────┘
                          ▼
                    ┌────────────┐
         Paperclip  │  Evidence  │  → spec.json
                    └─────┬──────┘
                          ▼
              ┌───────────┴───────────┐
              ▼                       ▼
       ┌────────────┐          ┌────────────┐
BindCraft│   Design  │          │  Physics   │  existing Vina
Tamarind └─────┬─────┘          │  control   │  WT + mutant
              ▼                └─────┬──────┘
       ┌────────────┐                │
Tamarind│ Structure │                │
       └─────┬──────┘                │
              └──────────┬───────────┘
                         ▼
                  ┌────────────┐
                  │    Eval    │  → eval.json
                  └─────┬──────┘
                         ▼
                  ┌────────────┐
           Claude │   Critic   │  → verdicts.json
                  └─────┬──────┘
                         ▼
                  ┌────────────┐
                  │  Report +  │  UI four panes + Monday markdown card
                  │ experiment │
                  └────────────┘
```

Any node may read a fixture and set `provenance` accordingly. Downstream nodes must still run.

---

## Code layout (proposed)

Do not bikeshed names. If you add a file, put it here.

```text
backend/
  main.py                 # FastAPI: /api/run, /api/runs/latest, SSE
  pipeline.py             # LangGraph of the new nodes
  config.py               # KRAS-first; legacy targets behind flag
  compounds.py            # keep KRAS_COMPOUNDS
  contracts/validate.py   # jsonschema for spec/designs/verdicts/eval
  tools/
    paperclip.py
    tamarind.py
    sequence_design.py   # heuristic fallback — not RFdiffusion
    proto_runner.py      # leftover; not the live designer
  agents/
    evidence.py
    designer.py
    structure.py
    physics_control.py    # Vina docking control (not MD)
    evaluator.py
    critic.py
    experiment.py         # Monday markdown card (Benchling unused)
    llm.py                # Claude primary
  evaluation/
    oracle.py             # Spearman, residuals, WT-mutant delta
  simulation/             # Vina + PDB download cache
frontend/
  src/app/page.tsx        # four-pane Trust UI (loads /api/runs/latest on boot)
  src/components/         # MutationMap, DesignTable, RejectDrawer, ExperimentCard, EvalPanel
design/
  kras_g12c.py            # leftover Proto-era orchestrator — not the live path
  proto_binder.py         # leftover Proto program — designer.py does not call this
data/
  runs/<run_id>/          # contract files + caches (gitignored)
spec/                     # this folder — source of truth
```

---

## API (minimum)

| Method | Path | Body / query | Result |
|---|---|---|---|
| POST | `/api/run` | `{ "mode": "live" \| "replay" \| "fixture", "run_id": optional }` | `{ "job_id" }` |
| GET | `/api/run/{id}/status` | SSE or poll | agent statuses + current step |
| GET | `/api/runs/latest` | | folder contents as JSON |
| GET | `/api/runs/{id}/file/{name}` | `spec.json` etc. | raw file |
| GET | `/api/protein/{pdb_id}` | | existing PDB fetch |

`mode: fixture` copies `spec/fixtures/` into a new run folder and runs critic+UI path only.  
`mode: replay` reuses `data/runs/<id>` with no partner calls.

---

## Agent display names (UI must use these)

| Graph node | Show the user | Never show |
|---|---|---|
| evidence | Literature & databases (Paperclip) | Target Analyst magic |
| designer | Sequence design (BindCraft) | BindCraft only if `data/bindcraft_designs/designs.json` exists; else heuristic / fixture. Never show “RFdiffusion” for those fallbacks. |
| structure | Fold & complex (Tamarind) | — |
| physics | Docking control (AutoDock Vina) | Molecular dynamics as the pitch |
| evaluate | Score vs experiment | — |
| critic | Scientist critic (Claude) | Generic LLM brief as the hero |
| experiment | Monday lab card | — |

---

## Run folder

```text
data/runs/<run_id>/
  spec.json
  designs.json
  designs.fasta
  smallmol.json
  eval.json
  verdicts.json
  experiment.md
  traces.json
  paperclip_raw.json
  structures/
  docked/
  provenance.json          # which nodes were live vs fixture
```

The UI’s source of truth is this folder, not React state invented during the run.

---

## LLM policy

1. Claude for critic, hypothesis restatement, experiment card prose.
2. Temperature low (≤ 0.3) for verdicts.
3. Verdict JSON must parse. If it does not, retry once, then mark designs `hold` with reason `other`.
4. Never let the LLM invent Ki values or PDB IDs. Those fields come from tools or stay `null`.

---

## Security / secrets

Environment only. Document keys in `backend/.env.example`. Paperclip, Anthropic, Tamarind. Modal/Proto leftover (`USE_PROTO=0`). Benchling unused.

Do not log full API keys. Do not paste secrets into `spec/` or GitHub issues.

---

## What “inspectable” means

A judge clicks a promoted design and sees:

1. Hypothesis string
2. Mutations + Paperclip document IDs
3. Sequence
4. Structure metric (named correctly)
5. WT vs mutant number (or “missing → hold”)
6. Novelty method + value
7. Critic paragraph
8. Remaining risk

If any of 1–7 is only in the presenter’s head, it is not inspectable yet.
