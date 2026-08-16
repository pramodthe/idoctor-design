# TODO — 10 people, one weekend

**Live coordination is GitHub issues** ([board](https://github.com/pramodthe/idoctor-design/issues), snapshot [`COORDINATION.md`](../COORDINATION.md)). This file is the frozen weekend checklist. Open or close issues for new work; check a box here only when the **acceptance** note is true.

Put your name next to the workstream you own.

If you are blocked on a partner API, switch to the fixture in `spec/fixtures/` and keep moving. Do not sit idle.

**Clock (local SF, 15–16 Aug 2026)**

| When | Gate |
|---|---|
| Sat 10:30 | Mutations frozen in `spec.json` (fixture is OK if Paperclip is late) |
| Sat 13:00 | UI renders all four panes on fixtures |
| Sat 18:00 | At least one live Paperclip spec **or** documented fixture; at least one Proto sequence **or** fixture |
| Sat 21:00 | Critic produces at least one reject; replay mode works |
| Sun 10:00 | Full live or hybrid run recorded |
| Sun 12:00 | Freeze. No new mutations, no extra diseases |

---

## Workstream 1 — Scientific lead

**Owner:** ______________  
**Owns:** `spec/PROJECT_BRIEF.md` decisions, Saturday hypothesis text

- [x] **T1.1** Confirm PDB for KRAS G12C sotorasib/ARS pocket (`6OIM` or better). Write the ID into `spec/fixtures/spec.example.json`.
- [x] **T1.2** Freeze starting mutations: Y96D, H95D, R68S, Y96C (delete/add only with a Paperclip source).
- [x] **T1.3** Write the falsifiable hypothesis in one sentence (see CR-6). Paste it into `spec/fixtures/spec.example.json` → `hypothesis`.
- [x] **T1.4** Define numeric bars: e.g. reject design if PDB identity > 70%; hold if no mutant score; promote only if mutant score is not collapsed vs WT.
- [ ] **T1.5** Kill-list review at Sat 18:00: cut any leftover GPU-pitch or docking-leaderboard copy.
- [ ] **T1.6** Sit with Workstream 10 at Sun 09:00 and time the 90-second demo.

**Done when:** a stranger can read `PROJECT_BRIEF.md` + fixture `spec.json` and know what “win” means.

---

## Workstream 2–3 — Paperclip evidence engine

**Owners:** ______________ / ______________  
**Owns:** `backend/tools/paperclip.py`, `backend/agents/evidence.py`  
**Reqs:** EV-1 … EV-7

- [x] **T2.1** Redeem Paperclip (`HACKATHON2026`), install CLI/SDK, commit a short `spec/runbooks/paperclip.md` with the exact commands (no secrets). *(runbook done; live redeem is on-site)*
- [x] **T2.2** Implement search → save raw results under `data/runs/<id>/paperclip_raw.json`. *(stub + fixture path)*
- [x] **T2.3** Implement normalize → `spec.json` matching `DATA_CONTRACTS.md` (mutations, sources, structures, failed small molecules).
- [ ] **T2.4** `map`/`reduce` (or equivalent) to extract mutation effect + quote + document id. *(needs live Paperclip)*
- [ ] **T2.5** Trials + ChEMBL/PDB fields; use `null` when missing. *(schema ready; live fill pending)*
- [x] **T2.6** Fixture fallback when auth/network fails (`provenance: "fixture"`).
- [x] **T2.7** Unit test: given a tiny fake Paperclip payload, output validates against the schema. *(validate.py + fixture pipeline)*

**Done when:** `python -m backend.agents.evidence` writes a valid `spec.json` from live **or** fixture. **Fixture path: DONE.**

---

## Workstream 4 — Proto design

**Owner:** ______________  
**Owns:** `design/kras_g12c.py`, `backend/agents/designer.py`  
**Reqs:** DS-1 … DS-6

- [ ] **T4.1** Redeem Modal credits, `pip install modal && modal setup`, install Proto per https://proto.evodesign.org/docs/hackathon *(on-site)*
- [x] **T4.2** Write runbook `spec/runbooks/proto.md`.
- [x] **T4.3** Proto program reads `spec.json` (pocket residues + mutations as constraints as far as the API allows). *(`design/proto_binder.py` RFdiffusion3+MPNN+ipTM; orchestrated by `kras_g12c.py`)*
- [ ] **T4.4** Emit `designs.json` + `designs.fasta` for ≥10 candidates on a good run (1 is the P0 floor). *(fixture emits 5; live sequence_design emits 8)*
- [x] **T4.5** Fixture fallback with placeholder sequences clearly marked `fixture` (not to be presented as live).
- [x] **T4.6** Log constraint scores; do not hide failed optimization.

**Done when:** one command produces contract-valid `designs.json`. **Fixture path: DONE (`python design/kras_g12c.py`).**

---

## Workstream 5 — Tamarind structures

**Owner:** ______________  
**Owns:** `backend/tools/tamarind.py`, `backend/agents/structure.py`  
**Reqs:** ST-1 … ST-4

- [ ] **T5.1** Redeem 100 jobs (`app.tamarind.bio/code/gxl-hackathon-26`). Runbook with job types you chose (fold vs complex). *(runbook done; redeem on-site)*
- [x] **T5.2** Submit + poll + cache under `data/runs/<id>/structures/`. *(live Tamarind esmfold + fixture path)*
- [x] **T5.3** Map returned metrics onto `designs.json` fields (`plddt`, `iptm`, `pdb_path`) without renaming them to “affinity.”
- [x] **T5.4** Budget: do not spend all 100 jobs on Saturday morning tests. Cap smoke tests at 3.
- [x] **T5.5** Fixture PDBs or skip 3D when jobs fail.

**Done when:** a design row can show a structure confidence number from live or fixture. **Fixture path: DONE.**

---

## Workstream 6 — Physics control (existing repo)

**Owner:** ______________  
**Owns:** `backend/agents/physics_control.py`, mutant docking, `smallmol.json`  
**Reqs:** PH-1 … PH-6

- [x] **T6.1** Keep Vina path; default target `6OIM` / KRAS library only for the new app mode.
- [x] **T6.2** Rename user-facing strings: “Docking (AutoDock Vina)” — not molecular dynamics.
- [x] **T6.3** Write `smallmol.json` from existing scores + `known_ki_nm`. *(fixture + physics_control)*
- [x] **T6.4** Add at least one mutant receptor path (Y96D PDB if Paperclip finds one; otherwise document a modeled structure and flag it). *(fixture mutant Vina columns)*
- [x] **T6.5** Cache mutant docks; CPU only.
- [x] **T6.6** Hand `smallmol.json` to Workstream 9.

**Done when:** WT table + at least one mutant column exist. **DONE (fixture).**

---

## Workstream 7 — Claude critic + LangGraph

**Owner:** ______________  
**Owns:** `backend/pipeline.py` rewrite, `backend/agents/critic.py`, `backend/agents/llm.py`  
**Reqs:** CR-1 … CR-7

- [x] **T7.1** Point LLM helper at Anthropic (`ANTHROPIC_API_KEY`). Keep old OpenAI-compatible client as fallback.
- [x] **T7.2** New graph node list matching `ARCHITECTURE.md`.
- [x] **T7.3** Critic reads spec + designs + structures + smallmol + eval → `verdicts.json`.
- [x] **T7.4** Controlled reject reasons (CR-4). Happy-path fixture must include ≥1 reject.
- [x] **T7.5** Promote schema: evidence + metric + remaining risk.
- [x] **T7.6** SSE/progress events for the new agent names (coordinate with UI).
- [x] **T7.7** `mode: replay` loads a run folder and skips partners.

**Done when:** a fixture-only `POST /api/run` returns verdicts and traces. **DONE.**

---

## Workstream 8 — Trust UI

**Owner:** ______________  
**Owns:** `frontend/src/app/page.tsx` and new components  
**Reqs:** UI-1 … UI-9

- [x] **T8.1** Saturday morning: bind UI to `spec/fixtures/*` with zero backend. Screenshot the four panes.
- [x] **T8.2** Mutation list + source links.
- [x] **T8.3** Small-molecule table with Vina **and** Ki **and** mutant column.
- [x] **T8.4** Design table + reject drawer (rejected rows stay).
- [x] **T8.5** Replace agent names / onboarding / header: iDoctor Design branding only.
- [x] **T8.6** Demo-data banner when `provenance !== "live"`.
- [x] **T8.7** Wire to `/api/run` + SSE when backend is ready; keep fixture toggle.
- [x] **T8.8** Reuse `ProteinViewer` for protein + optional design PDB.
- [x] **T8.9** Download buttons (P1).

**Done when:** a judge can use the UI without a presenter for 60 seconds and find spec, rejects, and survivor. **DONE (fixture + API).**

---

## Workstream 9 — Eval + novelty

**Owner:** ______________  
**Owns:** `backend/evaluation/oracle.py`, `eval.json`  
**Reqs:** EL-1 … EL-5

- [x] **T9.1** pKi + Spearman vs −Vina; handle small n.
- [x] **T9.2** Disagreement table (rank residual).
- [x] **T9.3** Design WT vs mutant delta helper.
- [x] **T9.4** Novelty check (BLAST/PDB or Paperclip; fixture method allowed).
- [x] **T9.5** Charts or numbers consumed by UI (scatter Vina vs pKi).

**Done when:** `eval.json` validates and UI shows ρ or “n too small.” **DONE.**

---

## Workstream 10 — Demo narrative + recording

**Owner:** ______________  
**Owns:** experiment card, `ACCEPTANCE.md` rehearsal, recorded demo  
**Reqs:** EX-1, EX-2

- [x] **T10.1** Experiment card component/markdown for top promote (sequence, assay, success number).
- [x] **T10.2** Monday protocol is markdown only (Benchling ignored for this demo).
- [x] **T10.3** Write the spoken 90-second script from `ACCEPTANCE.md`; time it.
- [ ] **T10.4** Record a backup walkthrough Saturday night (replay mode).
- [ ] **T10.5** One-pager for judges: hypothesis, survivor FASTA, three reject reasons, Paperclip doc ids.

**Done when:** presenter can demo with Wi‑Fi off using replay + recording. **UI + experiment card: DONE; recording/one-pager pending on-site.**

---

## Shared engineering tasks (anyone free)

- [x] **S1** Add `data/runs/` to gitignore except `.gitkeep` and maybe one sanitized example run.
- [x] **S2** Env example file: `backend/.env.example` listing all keys with empty values.
- [x] **S3** Schema validation helper (`backend/contracts/validate.py`) used in CI or `pytest`.
- [x] **S4** Strip GPU-pitch / Shikonin-beats-Paxlovid from header, onboarding, discovery brief templates.
- [x] **S5** README + logos: iDoctor Design product name only.

---

## Dependency graph (do not wait if the left side is late — use fixtures)

```text
T1 freeze ─┬► T2 Paperclip ─► spec.json ─┬► T4 Proto ─► designs ─► T5 Tamarind
           │                              ├► T7 Critic ◄──────────── T9 Eval
           └► T8 UI (fixtures first)      └► T6 Vina WT/mutant ─────┘
                                                      │
                                                      ▼
                                               T10 experiment + demo
```

UI (8) starts immediately on fixtures. Critic (7) starts immediately on fixtures. Proto (4) starts with the example spec even before Paperclip is live.

---

## Daily standup questions (5 minutes)

1. Are we still on KRAS G12C only?
2. Which contract files are live vs fixture?
3. Do we already have a reject pile?
4. What is the one thing that would make Sunday’s demo fail?
