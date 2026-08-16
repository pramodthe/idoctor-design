# Proto + Modal runbook (leftover — not the live designer)

The live design node is Tamarind BindCraft via `backend/agents/designer.py`.
This runbook remains only for the unused Proto/Modal stack. `USE_PROTO` stays `0`.
Do not present Proto output as the Sunday demo.

Hackathon install: https://proto.evodesign.org/docs/hackathon

Binder design guide (what iDoctor Design uses):
https://proto.evodesign.org/docs/language/guides/examples/binder-design

## Install

```bash
pip install modal
modal setup
pip install git+https://github.com/evo-design/proto-tools.git
git clone https://github.com/evo-design/proto-language.git
pip install -e ./proto-language
```

Modal credits are for **Proto / folding models**, not for AutoDock Vina.

## Configure iDoctor Design

```bash
cp backend/.env.example backend/.env
# edit backend/.env:
USE_PROTO=1
MODAL_TOKEN_ID=...
MODAL_TOKEN_SECRET=...
PROTO_BINDER_LENGTH=48
PROTO_NUM_SAMPLES=4
PROTO_NUM_RESULTS=4
PROTO_DEVICE=cuda
```

`backend/.env` is **gitignored** (never committed). Use `backend/.env.example` as the template in the repo.

## Program path

- Entry: `design/kras_g12c.py` (CLI + pipeline)
- Proto binder: `design/proto_binder.py` — RFdiffusion3 + ProteinMPNN + Boltz2 ipTM
  against `data/pdb_cache/6OIM.pdb`, hotspots from `pocket_residues` (Cys12 → A12, …)

Live pipeline order:

1. **Proto** (`USE_PROTO=1` + packages) → `provenance: live`, `meta.engine=proto_language`
2. Else **local sequence_design** → `provenance: live` but **not** Proto
3. Else **fixtures** → `provenance: fixture`

If Modal or gated models fail, fall back honestly. Do **not** present fixture or
sequence_design sequences as Modal Proto inventions. The designer agent trace records
`engine=…` so the UI/run JSON stays honest.
