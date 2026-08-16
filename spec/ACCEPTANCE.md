# Acceptance and demo

This is the Sunday checklist. If a box is empty, we are not ready to present.

---

## Judge test (must all pass)

A person who did not write the code, given the laptop, 90 seconds, no coaching:

- [ ] Finds the mutation list and at least one paper/trial identifier
- [ ] Finds a small-molecule table that shows **Ki next to Vina**, not Vina alone as the winner
- [ ] Finds at least one **rejected** design and a reason
- [ ] Finds one **promoted** sequence (FASTA or full amino acids)
- [ ] Sees a remaining risk or Monday experiment, not “this will work in patients”

If any fail, fix the UI, not the pitch.

---

## Scientific honesty test (must all pass)

- [x] No GPU-hero copy
- [x] No “molecular dynamics” label on Vina docking
- [x] No claim that a compound is better than an FDA drug from docking alone
- [x] Fixture/demo banner visible when data is not live
- [x] Invented Ki/PDB IDs: none (nulls allowed)
- [ ] Hypothesis is falsifiable (Workstream 1 sentence is on screen)

---

## Track mapping (say this if asked)

| Track | What we show |
|---|---|
| **A — AI scientist** | Full loop: evidence → hypothesis → design → test → reject/promote → experiment |
| **C — biological design** | The promoted FASTA did not exist Saturday morning (or we label it fixture and do not lie) |
| **B — dataset** | `spec.json` mutation atlas from Paperclip: mutations × sources × structures |

If the designer produced only fixtures or heuristic `sequence_design`, we **do not claim a new biological design from RFdiffusion**. We present Track A + B and say the design node is mocked or heuristic.

---

## 90-second spoken script

Time this. Cut until it fits.

1. **(0:00–0:15)** “KRAS G12C has a drug. Sotorasib. Patients relapse because the pocket mutates. We built an agent that is not allowed to ignore that.”
2. **(0:15–0:30)** Open mutation pane. “Paperclip pulled these mutations from papers and trials. Y96D is the example. Citations are here.”
3. **(0:30–0:45)** Small-molecule pane. “This is ordinary docking on the original protein. It looks fine. On the mutant, the same leads collapse. Docking without resistance is the wrong answer.”
4. **(0:45–1:05)** Design pane. “The designer proposed binders. The critic killed most of them — too similar to a known structure, or only good on wild type, or low fold confidence. The Engine column says whether this was BindCraft or a heuristic fallback.”
5. **(1:05–1:25)** Survivor. “This sequence is what we would order. Here is the Monday assay: bind G12C and Y96D. If mutant affinity dies, the computer was wrong.”
6. **(1:25–1:30)** Stop talking. Let them ask.

Do not open with GPU utilization. Do not mention COVID or Shikonin.

---

## Backup plan

| Failure | What we present |
|---|---|
| Paperclip down | Fixture spec; banner on; still show the *shape* of the atlas |
| BindCraft / Tamarind down | Sequences from `sequence_design` or fixtures; Engine column must not say BindCraft; no “new RFdiffusion sequence” claim |
| Tamarind down | Sequences + critic without 3D |
| Claude down | Template critic using eval rules only (still must reject WT-only) |
| Wi‑Fi down | Replay Saturday night run + recorded video |

---

## Definition of a prize-level run

Live or hybrid (`provenance` mixed) with:

1. Real Paperclip document IDs on at least two mutations
2. At least three live sequences that are not the fixture placeholders **or** an honest fixture/replay banner. Engine column matches `meta.design_engine`.
3. At least one mutant comparison for small molecules **or** designs
4. At least one reject and one promote
5. Experiment card with a number that would change our mind

That is enough. Do not add EGFR after noon on Sunday.
