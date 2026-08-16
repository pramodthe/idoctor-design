# Merge into kenjoy84-png/re-agent

This repo is the **iDoctor Design** app (Next.js + FastAPI). Kenji's harness is Vite + Express.
Do not merge frontends. Add this package as a sibling directory.

From `re-agent` (after it has at least one commit on `main`):

```bash
git subtree add --prefix=idoctor-design https://github.com/pramodthe/idoctor-design.git main
```

Result:

```
re-agent/
  cost-aware-next-test-agent/   # Kenji
  idoctor-design/               # this package
  docs/ schemas/ fixtures/
```

Or: add `pramodthe` as a collaborator and open a PR that only adds `idoctor-design/`.
