# Data contracts

**Every workstream reads and writes these files.** If you need a new field, add it here first, then to the fixtures, then to code.

Validation: treat additional properties as allowed (forward compatible). Required properties must be present. Use `null` for unknown numbers. Do not omit keys that the UI expects.

String enumerations are closed. Do not invent a new `verdict` string.

---

## `provenance.json`

```json
{
  "run_id": "2026-08-15-demo",
  "mode": "fixture",
  "nodes": {
    "evidence": "fixture",
    "designer": "fixture",
    "structure": "fixture",
    "physics": "cached",
    "evaluate": "live",
    "critic": "live",
    "experiment": "live"
  },
  "created_at": "2026-08-15T18:00:00Z"
}
```

| Field | Values |
|---|---|
| `mode` | `live` \| `replay` \| `fixture` |
| each node | `live` \| `cached` \| `fixture` \| `skipped` |

If **any** node is `fixture`, the UI shows the demo-data banner.

---

## `spec.json`

Produced by Paperclip evidence (or copied from fixture). Source of truth for mutations and hypothesis.

See [`fixtures/spec.example.json`](./fixtures/spec.example.json).

Required top-level keys:

| Key | Type | Notes |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `target` | object | KRAS G12C identity |
| `hypothesis` | string | Falsifiable, one or two sentences |
| `mutations` | array | At least one |
| `failed_small_molecules` | array | May be empty |
| `structures` | array | At least WT PDB |
| `pocket_residues` | array of strings | e.g. `"Tyr96"` |
| `success_bars` | object | Numeric rules for critic |
| `provenance` | string | `live` \| `fixture` |

### `target`

| Key | Type |
|---|---|
| `name` | string |
| `gene` | string |
| `pdb_id` | string |
| `uniprot_id` | string or null |
| `clinical_hook` | string |

### `mutations[]`

| Key | Type | Notes |
|---|---|---|
| `id` | string | `"Y96D"` |
| `effect_on_sotorasib` | string | `loss` \| `reduced` \| `unclear` |
| `notes` | string | Plain language |
| `sources` | array | `{ "kind": "paper"\|"trial"\|"pdb"\|"chembl", "id": "...", "title": "...", "quote": "..." }` |

### `success_bars`

| Key | Type | Default meaning |
|---|---|---|
| `max_pdb_identity` | number | Reject above this (e.g. 0.70) |
| `min_plddt` | number or null | Hold/reject below |
| `require_mutant_score` | boolean | If true, missing mutant → `hold` |

---

## `designs.json`

Produced by the designer (`backend/agents/designer.py`): BindCraft campaign on disk if present, else local `sequence_design`, else fixtures. Structure agent may patch metrics onto the same file.

`meta.design_engine` is required for honesty: `bindcraft` | `sequence_design` | `fixture` | `cached`. The UI Engine column reads this. Do not omit it.

See [`fixtures/designs.example.json`](./fixtures/designs.example.json).

Each `designs[]` item:

| Key | Type |
|---|---|
| `id` | string (`des_001`) |
| `sequence` | string (amino acids) |
| `length` | number |
| `molecule_type` | `miniprotein` \| `peptide` |
| `constraint_scores` | object (name → number; higher or lower documented in `score_direction`) |
| `score_direction` | `lower_is_better` \| `higher_is_better` |
| `plddt` | number or null |
| `iptm` | number or null |
| `pdb_path` | string or null |
| `novelty` | object or null |
| `provenance` | `live` \| `fixture` |
| `fold_method` | optional string (`bindcraft:af2`, `heuristic_v1`, Tamarind tool name) |
| `generator` | optional string (`tamarind:bindcraft`, `sequence_design.local`) |

Top-level `meta.design_engine` stamps which generator actually ran.

`designs.fasta` is the same sequences in FASTA, headers `>des_001`.

---

## `smallmol.json`

Physics control arm.

See [`fixtures/smallmol.example.json`](./fixtures/smallmol.example.json).

Each `compounds[]` item:

| Key | Type |
|---|---|
| `id` | string |
| `name` | string |
| `smiles` | string |
| `known_ki_nm` | number or null |
| `vina_wt` | number or null |
| `vina_mutants` | object, mutation id → score or null |
| `pains_flags` | array of strings |
| `lipinski_violations` | number or null |

---

## `eval.json`

See [`fixtures/eval.example.json`](./fixtures/eval.example.json).

| Key | Type |
|---|---|
| `smallmol_spearman_rho` | number or null |
| `smallmol_n` | number |
| `smallmol_note` | string |
| `disagreements` | array of `{ id, vina_rank, ki_rank, residual, note }` |
| `design_deltas` | array of `{ id, wt_score, mutant_scores, note }` |

---

## `verdicts.json`

Critic output. **This is what the UI treats as the answer.**

See [`fixtures/verdicts.example.json`](./fixtures/verdicts.example.json).

Each `items[]` entry:

| Key | Type | Notes |
|---|---|---|
| `subject_kind` | `design` \| `smallmol` | |
| `subject_id` | string | `des_001` or compound id |
| `verdict` | `promote` \| `hold` \| `reject` | closed enum |
| `reasons` | array of reason codes | see below |
| `summary` | string | ≤ 80 words, no invented numbers |
| `evidence_ids` | array of strings | mutation ids, paper ids |
| `metrics_used` | array of strings | e.g. `"vina_Y96D"`, `"plddt"` |
| `remaining_risk` | string | required if `promote` |

Reason codes (CR-4):

- `wt_only_signal`
- `too_similar_to_pdb`
- `low_structure_confidence`
- `contradicts_literature`
- `promiscuous_or_pains`
- `weak_or_missing_metric`
- `passes_spec`
- `other`

---

## `experiment.md`

Markdown is enough. Suggested headings:

```markdown
# Monday experiment — <design id>
## Construct
## Sequence
## Production
## Binding assay
## Comparators (WT G12C vs Y96D)
## Number that would change our mind
## What would falsify the computational story
```

---

## `traces.json`

Array of agent traces. Reuse the spirit of the old `AgentTrace` type:

```json
{
  "agent": "evidence",
  "agent_name": "Literature & databases (Paperclip)",
  "duration_seconds": 12.4,
  "model": null,
  "input_summary": "...",
  "output_summary": "...",
  "steps": [{ "action": "...", "detail": "..." }],
  "tool_calls": [{ "tool": "paperclip.search", "detail": "..." }]
}
```

---

## `novel_designs.json` (Ryan / `TherapeuticPlan` seam)

Hand-off into `idoctor-engine` therapy rung 3. Additive keys only; `proto_run_id` is kept even when the job ran on Tamarind BindCraft (do not rename it).

See [`fixtures/novel_designs.example.json`](./fixtures/novel_designs.example.json). Built by `backend/contracts/novel_designs.py` from `designs.json` + `verdicts.json` + `experiment.md`.

Each `novel_designs[]` item:

| Key | Type | Notes |
|---|---|---|
| `modality` | string | `miniprotein` or `peptide` |
| `target` | string | Gene + PDB + pocket from `spec.json` |
| `sequence` | string | |
| `metrics` | object | `ipTM`, `pLDDT`, `boltz2_affinity` (null if unmeasured — never invented) |
| `proto_run_id` | string | Tamarind job name, or `idoctor-design:<run_id>:<design_id>` |
| `wetlab_protocol` | string or null | Path to `experiment.md` in the run folder |
| `caveat` | string | Always includes `in-silico only; predicted, not measured` |

Only critic `promote` / `hold` designs are exported. Rejects stay in `verdicts.json`. If `bridge.py` sends a splice/HBB or HFE/ferroportin brief, `refused[]` is filled and `novel_designs` is empty.

```bash
PYTHONPATH=. python -m backend.contracts.novel_designs --fixtures
PYTHONPATH=. python -m backend.contracts.novel_designs --run-dir data/runs/<id>
PYTHONPATH=. python -m backend.contracts.novel_designs --brief brief.json --fixtures
```

---

## Versioning

`schema_version`: `"1.0"` on all JSON files above. If you break a required field, bump to `"1.1"` and update fixtures in the same PR.
