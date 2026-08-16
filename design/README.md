# Design (leftover Proto path)

**Live designer is `backend/agents/designer.py`**, not this folder.

Priority on a live pipeline run:

1. Finished Tamarind BindCraft campaign at `data/bindcraft_designs/designs.json`
2. Local `backend/tools/sequence_design.py` (heuristic — not RFdiffusion)
3. `spec/fixtures/designs.example.json`

This folder is the Proto-era CLI. `USE_PROTO` stays off. Do not present output from these scripts as the Sunday demo unless you also stamp `meta.design_engine` honestly.

```bash
# Fixture / offline (leftover CLI)
PYTHONPATH=. python design/kras_g12c.py --spec spec/fixtures/spec.example.json --out-dir /tmp/rl-design
```

| File | Role |
|------|------|
| `kras_g12c.py` | Leftover orchestrator: Proto → sequence_design → fixtures |
| `proto_binder.py` | Leftover Proto program (RFdiffusion3 + MPNN + ipTM) |

See [`spec/runbooks/live_mode.md`](../spec/runbooks/live_mode.md) for the live BindCraft / replay path.
