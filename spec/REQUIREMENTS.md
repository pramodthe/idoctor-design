# Requirements — iDoctor Design

Requirements are numbered so a Cursor agent can implement and test them one by one.

Priority:

- **P0** — must ship Saturday night or we have no demo
- **P1** — must ship Sunday morning or we are not competitive
- **P2** — ship if the P0/P1 path is green

Status values for `TODO.md`: `todo` · `doing` · `done` · `blocked`.

---

## 0. Product principles (always on)

| ID | Requirement | Priority |
|---|---|---|
| PR-1 | The app answers one question: *what binder should we test next for sotorasib-resistant KRAS G12C, and why might that be wrong?* | P0 |
| PR-2 | Every promoted design and every rejected design shows a reason a scientist can check (citation, metric, or both). | P0 |
| PR-3 | The naive docking leaderboard is never the final answer. It is a control that can be disproven. | P0 |
| PR-4 | Partner APIs may fail. The app must still demo from saved fixtures and Saturday-night results. | P0 |
| PR-5 | Copy and UI must not claim “molecular dynamics” for docking, and must not claim a compound beats an FDA drug from Vina score alone. | P0 |
| PR-6 | Teams share the JSON contracts in `DATA_CONTRACTS.md`. Do not invent parallel schemas. | P0 |

---

## 1. Scientific scope

| ID | Requirement | Acceptance |
|---|---|---|
| SC-1 | **P0.** Default target is KRAS G12C, PDB `6OIM` (or a documented replacement if Paperclip/PDB says a better sotorasib-bound structure exists). | UI and pipeline default to this target. Extra disease targets are out of scope. |
| SC-2 | **P0.** Resistance set starts as Y96D, H95D, R68S, Y96C. Scientific lead may edit the list only by updating `spec.json`, not by hardcoding in five files. | Changing mutations in `spec.json` changes critic + UI without a code edit in each agent. |
| SC-3 | **P0.** Wild-type in this product means KRAS G12C **without** the extra resistance mutation. Mutant means G12C **plus** one listed mutation. | Labels in the UI say this in plain language. |
| SC-4 | **P1.** Pocket of interest is the Switch II region (residues including Cys12, His95, Tyr96, Asp69 unless Paperclip/PDB revises them). | Residues appear in `spec.json` with a source. |
| SC-5 | **P1.** Small-molecule library is the existing `KRAS_COMPOUNDS` list in `backend/compounds.py`. Do not expand it during the weekend unless eval is already shipping. | Control arm runs on that list. |

---

## 2. Evidence agent (Paperclip)

The evidence agent turns the public scientific record into `spec.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| EV-1 | **P0.** Search Paperclip for KRAS G12C sotorasib/adagrasib resistance (papers, plus trials and ChEMBL/PDB if available). | A run writes `data/runs/<run_id>/paperclip_raw.json` and a normalized `spec.json`. |
| EV-2 | **P0.** Extract a mutation table: mutation name, approximate effect on sotorasib (loss / reduced / unclear), and at least one paper or trial ID per mutation. | Each mutation in `spec.json` has `sources[]` with IDs a judge can look up. |
| EV-3 | **P1.** Extract failed or limited small molecules (sotorasib, adagrasib, and any others the papers name) with a one-line “why not enough.” | `spec.json` has `failed_small_molecules[]`. |
| EV-4 | **P1.** Pull PDB IDs for G12C and, if they exist, resistance-mutant structures. | `spec.json` has `structures[]` with PDB IDs. If none for a mutant, the row says `modeled_or_missing`. |
| EV-5 | **P1.** Pull ChEMBL or literature Ki/IC50 values when present; do not invent numbers. | Missing affinity is `null`, never a hallucinated float. |
| EV-6 | **P0.** If Paperclip is down or unauthenticated, load `spec/fixtures/spec.example.json` and mark `spec.provenance = "fixture"`. | UI shows a visible “demo data” banner. |
| EV-7 | **P1.** Store quotes or short excerpts used for extraction, with document IDs, so reasoning is inspectable. | Critic and UI can open “why this mutation is in the spec.” |

---

## 3. Design agent (Tamarind BindCraft)

| ID | Requirement | Acceptance |
|---|---|---|
| DS-1 | **P0.** Design miniprotein/peptide candidates for the Switch II / G12C pocket under resistance constraints. **Preferred live engine:** Tamarind BindCraft (RFdiffusion + ProteinMPNN + AF2 filters) from a finished campaign on disk. | `designs.json` contains ≥1 sequence after a successful run. `meta.design_engine` is `bindcraft`, `sequence_design`, or `fixture`. |
| DS-2 | **P0.** Each design records sequence, length, generator/constraint scores, and a run id. | No design is only a pretty picture. FASTA + JSON both exist. |
| DS-3 | **P1.** Constraints include (as far as BindCraft/spec allow): bind the specified region, remain plausible as a fold, and do not ignore listed resistance residues. | Constraint names and scores are in `designs.json`. |
| DS-4 | **P0.** GPU design jobs run on **Tamarind**, not Modal Proto. BindCraft is a multi-hour job and is not called inline per UI click. | README/spec notes this. No `USE_PROTO=1` required for the demo. |
| DS-5 | **P0.** If no BindCraft campaign is on disk, use local `sequence_design` (labeled heuristic) then `spec/fixtures/designs.example.json` with `provenance=fixture`. | Demo still has sequences. UI engine column must not say BindCraft for those rows. |
| DS-6 | **P1.** Designs are tagged `novel_unverified` until the eval agent checks PDB similarity. | Critic can reject on novelty. |

---

## 4. Structure agent (Tamarind)

| ID | Requirement | Acceptance |
|---|---|---|
| ST-1 | **P1.** Submit fold jobs for designs (and complex/dock jobs if the 100-job budget allows). | Each design can show a structure file or a clear `pending`/`failed` state. |
| ST-2 | **P1.** Record pLDDT / ipTM / equivalent scores the tool returns. Do not rename them into fake “binding affinity.” | UI labels the metric as the tool’s name. |
| ST-3 | **P0.** Cache all job JSON and PDBs under `data/runs/<run_id>/structures/`. | Re-demo does not re-spend jobs. |
| ST-4 | **P0.** If Tamarind is down, use fixture structures or hide the 3D for that row and keep scores from JSON. | No blank crash. |

---

## 5. Physics control arm (existing Vina / RDKit)

This is the docking control arm (legacy physics stack), pointed at KRAS, used as a **control**, not as the winner.

| ID | Requirement | Acceptance |
|---|---|---|
| PH-1 | **P0.** Dock the KRAS compound library against G12C WT (`6OIM` or spec structure). | `smallmol.json` has Vina scores + known Ki. |
| PH-2 | **P1.** Dock or score the same library against at least one resistance mutant structure (or a documented mutant model). | `smallmol.json` has `mutant_scores` for at least Y96D. |
| PH-3 | **P0.** Compute eval metrics: Spearman correlation of Vina vs experimental pKi on WT where Ki exists; list disagreements. | `eval.json` exists even if mutant docking is late. |
| PH-4 | **P0.** Never present Shikonin-style “beats FDA drug” copy. KRAS screen must show Ki next to Vina. | Rank table columns: Vina, Ki, residual, verdict. |
| PH-5 | **P1.** Toxicity remains Lipinski + PAINS for small molecules only. It is a filter, not a toxicology agent. | UI calls it “drug-likeness filters.” |
| PH-6 | **P0.** Vina runs on CPU. No GPU required for this arm. | Local or cached results work. |

---

## 6. Critic / AI scientist (Claude + LangGraph)

| ID | Requirement | Acceptance |
|---|---|---|
| CR-1 | **P0.** Pipeline is a graph, not a single LLM call: Evidence → Spec → Design → Structure → Physics → Eval → Critic → Report. Nodes may skip to fixtures. | Traces show each node. |
| CR-2 | **P0.** Critic outputs `verdicts.json`: each design and each top small molecule is `promote`, `hold`, or `reject`. | At least one reject in the happy-path demo. |
| CR-3 | **P0.** A promote requires: sequence or compound id, evidence from spec, at least one computed metric, and a remaining risk. | Schema validation fails without those fields. |
| CR-4 | **P1.** Reject reasons must be one of a controlled list plus free text: `wt_only_signal`, `too_similar_to_pdb`, `low_structure_confidence`, `contradicts_literature`, `promiscuous_or_pains`, `weak_or_missing_metric`, `other`. | UI can filter the reject pile by reason. |
| CR-5 | **P0.** LLM is Claude (Anthropic API). Template critic if the key is unset. | Model name appears in traces. |
| CR-6 | **P1.** Hypothesis is explicit and falsifiable, e.g. “small-molecule Switch II binders lose affinity on Y96D; a larger designed binder can retain contacts outside the sotorasib epitope.” | Hypothesis string is on the home screen during a run. |
| CR-7 | **P1.** Traces include tool calls (Paperclip queries, Tamarind job ids, Vina) with timing. | A judge can expand “what did you do.” |

---

## 7. Evaluation

| ID | Requirement | Acceptance |
|---|---|---|
| EL-1 | **P0.** For small molecules with `known_ki_nm`, compute pKi = 9 - log10(Ki_nM), Spearman ρ vs Vina (note Vina is more negative = better, so compare to −Vina). | Number shown; if n < 5, show “n too small” instead of a fake ρ. |
| EL-2 | **P0.** Disagreement table: large residual between docking rank and Ki rank. | At least the worst 3 shown. |
| EL-3 | **P1.** For designs: WT vs mutant score delta (Vina, Tamarind interface score, or BindCraft metric — whichever exists). Promote path should not be WT-only. | Verdict uses this when present. |
| EL-4 | **P1.** Novelty: sequence identity vs known PDB/UniProt binders if a search is available; otherwise a Paperclip/PDB text check. | `novelty.identity` or `novelty.method = "unchecked_fixture"`. |
| EL-5 | **P2.** Enrichment of true actives (Ki below a stated cutoff) in Vina top-k. | Optional chart. |

---

## 8. User interface

| ID | Requirement | Acceptance |
|---|---|---|
| UI-1 | **P0.** One primary screen after a run, four regions: (A) literature spec / mutations, (B) small-molecule control, (C) designs + reject pile, (D) Monday experiment. | A new user can find all four without a guided tour. |
| UI-2 | **P0.** Mutation map: list mutations with source links and WT vs mutant control outcome. | Click mutation → sources. |
| UI-3 | **P0.** Small-molecule table: name, Vina, Ki, WT vs mutant, eval flag. | Default sort is not “best Vina” without Ki visible. |
| UI-4 | **P0.** Design table: sequence (truncated), length, structure confidence, WT/mutant, verdict. Expand row for FASTA + critic text. | Rejected rows stay visible. |
| UI-5 | **P1.** 3D protein viewer: protein + selected ligand or designed model when a PDB is available. | No crash if pose missing. |
| UI-6 | **P0.** Agent panel shows the graph display names from `ARCHITECTURE.md`. | Display names match. |
| UI-7 | **P0.** Fixture/demo mode banner when provenance is not `live`. | Cannot miss it. |
| UI-8 | **P1.** Onboarding copy is the KRAS resistance story. | First modal ≤ 5 sentences. |
| UI-9 | **P2.** Download buttons: `spec.json`, `designs.fasta`, `verdicts.json`, brief as markdown. | Files match the run on screen. |

---

## 9. Monday experiment

| ID | Requirement | Acceptance |
|---|---|---|
| EX-1 | **P1.** For the top promoted design, generate an experiment card: construct name, amino-acid sequence, suggested expression (e.g. E. coli or peptide synthesis), binding assay (SPR or BLI) vs KRAS G12C and vs Y96D, success criterion (e.g. mutant KD within 10× of WT). | Card is visible in UI and exportable as markdown. |
| EX-2 | **P2.** Markdown protocol is enough for this demo (Benchling optional / unused). | Document which path was used. |

---

## 10. Platform / non-functional

| ID | Requirement | Acceptance |
|---|---|---|
| NF-1 | **P0.** FastAPI + Next.js remain the app shell. New agents live under `backend/agents/` and `backend/tools/`. | Existing `uvicorn` / `npm run dev` still start. |
| NF-2 | **P0.** Bind HTTP to `0.0.0.0` and `$PORT` if deployed; local default backend `8080`, frontend `3000`. | Matches current repo. |
| NF-3 | **P0.** Secrets only in env: `ANTHROPIC_API_KEY`, `PAPERCLIP_*`, `TAMARIND_API_KEY`. Never commit keys. `USE_PROTO` stays off. Benchling not used. | `.env` gitignored. |
| NF-4 | **P0.** A run is a folder `data/runs/<run_id>/` with the contract files. Live demo can point at the latest successful folder. | `GET /api/runs/latest` returns it. |
| NF-5 | **P1.** One-command replay: load latest run without calling partners. Stage walkthrough uses this. | `POST /api/run` with `{ "mode": "replay" }`. |
| NF-6 | **P1.** Timeouts: Paperclip 120s, Tamarind fold poll up to 30 min, BindCraft campaign hours (not inline), Vina per ligand as today. UI stays in “running” with step text. | No silent hang. |
| NF-7 | **P0.** No special GPU required. Skip MD if Vina scores exist. | Pipeline completes on a laptop with fixtures + cached Vina. |

---

## 11. Explicit non-goals (do not build)

| ID | Non-goal |
|---|---|
| NG-1 | Extra disease targets (COVID, HIV, EGFR) as first-class demo. |
| NG-2 | Long explicit-solvent MD as the product story. |
| NG-3 | Using every sponsor (Phylo is optional; skip if Paperclip works). |
| NG-4 | Virtual FDA reviewer that only summarizes labels. |
| NG-5 | Designing 100 sequences and showing the prettiest without rejects. |
| NG-6 | Replacing Vina with a new docking engine this weekend. |
| NG-7 | Training new ML models. |

---

## 12. Requirement to workstream map

See `TODO.md` for owners. Quick map:

| Workstream | Requirement IDs |
|---|---|
| 1 Scientific lead | PR-*, SC-*, CR-6 |
| 2–3 Paperclip | EV-* |
| 4 Design (BindCraft) | DS-* |
| 5 Tamarind | ST-* |
| 6 Physics control | PH-*, EL-1, EL-2 |
| 7 Critic | CR-*, EL-3, EL-4 |
| 8 UI | UI-* |
| 9 Eval | EL-* |
| 10 Benchling + demo | EX-*, ACCEPTANCE.md |
