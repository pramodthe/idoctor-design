# Design (Proto)

Live design entrypoint for iDoctor Design.

```bash
# Fixture / offline
PYTHONPATH=. python design/kras_g12c.py --spec spec/fixtures/spec.example.json --out-dir /tmp/rl-design

# Live: Proto if installed + USE_PROTO=1, else local sequence_design
PYTHONPATH=. python design/kras_g12c.py --live --spec path/to/spec.json --out-dir data/runs/demo
```

| File | Role |
|------|------|
| `kras_g12c.py` | Orchestrator: Proto → sequence_design → fixtures |
| `proto_binder.py` | Real Proto program (RFdiffusion3 + MPNN + ipTM) |

See [`spec/runbooks/proto.md`](../spec/runbooks/proto.md) for Modal + Proto install.
