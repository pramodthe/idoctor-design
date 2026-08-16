# iDoctor Design frontend (Next.js)

Trust UI for the KRAS G12C resistance scientist.

```bash
# from repo root — backend must be on :8080
cd frontend
npm install
npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

On boot the page loads `GET /api/runs/latest`. Overrides: `?run=live`, `?run=fixture`, `?run=none`.

See the root [README.md](../README.md) and [`spec/`](../spec/).
