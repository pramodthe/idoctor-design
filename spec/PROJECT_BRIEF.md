# Project brief — iDoctor Design

**Working name:** iDoctor Design (KRAS G12C binder loop)  
**Hackathon:** re:AGENT (15–16 August 2026, San Francisco)  
**Track:** Track A — Build an AI Scientist  
**Backup prizes:** Track C (we output a new biological sequence) and Track B (we output a literature-derived resistance atlas)  
**Team size this spec assumes:** 10 people, 10 Cursor IDEs, one weekend  

This document is for everyone, including people who are not computational chemists.

---

## The problem, in normal language

Cancer cells often carry a broken switch protein called **KRAS**. One common broken version is **KRAS G12C**. In 2021 the FDA approved **sotorasib (Lumakras)**, the first drug that could stick to that broken switch and turn it down.

It helps many patients. Then, often within months, the cancer finds a workaround. The protein changes shape slightly — a **resistance mutation** — and the drug no longer fits. The patient relapses. That is not a rare edge case. It is the central clinical failure mode of this drug class.

Today, figuring out “what should we make next?” means a human reading hundreds of papers, looking at structures, and guessing. That is slow, easy to fake with a pretty AI summary, and easy to get wrong if a computer docking program is treated as truth.

## What we are building

An **AI scientist** that does the job a careful computational biologist would do on Monday, and shows its work:

1. **Read the record.** Search papers, clinical trials, drug databases, and protein structures for how sotorasib actually fails.
2. **Write a spec.** Not a paragraph of vibe. A structured list: which mutations matter, which pocket residues to bind, which old drugs already failed, what “success” means.
3. **Design something new.** Prefer Tamarind **BindCraft** (RFdiffusion + ProteinMPNN + AF2 filters) from a finished campaign on disk. If that file is missing, use the labeled heuristic `sequence_design` or fixtures — and say so. Do not present those fallbacks as a diffusion-model run.
4. **Test it on a computer.** Fold the design, see if it can sit on KRAS, and compare it to the old small-molecule drugs we already know how to dock.
5. **Argue with itself.** If a design only looks good on the original protein, or copies a known binder from the PDB, or contradicts the papers — **reject it**. The reject pile is part of the product.
6. **Propose a real experiment.** A one-page wet-lab card: make this protein, measure binding to KRAS G12C and to the mutant, this is the number that would change our mind.

## What we are not building

- A general “chat with biology” chatbot.
- A replay of four diseases (COVID, HIV, EGFR, KRAS) with GPU branding.
- A leaderboard that says a weak natural product “beats” an FDA drug because a docking score said so.
- A slide deck. The hackathon asked for a working thing.

## Why this can win

re:AGENT is not “who has the prettiest 3D protein.” The hosts asked for:

- agents that **gather evidence**
- **generate and test hypotheses**
- produce **results worth trusting**
- use the weekend’s tools: **Paperclip, Tamarind, Claude** (BindCraft on Tamarind for design; Proto/Modal leftover, unused)

Most teams will either summarize papers or dump AI-generated sequences. iDoctor Design does both, then adds the missing piece: **evaluation**. We show where computer scores lie, and we keep the designs we could not kill.

The 90-second story:

> “Here is why Lumakras fails, in the patients’ mutations, cited from papers. Here is a docking screen that looks fine and then collapses on the mutant. Here are ten new binders the model proposed. We threw away eight. This one survived. Here is the experiment to run Monday.”

## What already exists in this repo (do not throw it away)

The previous demo stack can:

- Download a real 3D protein from the Protein Data Bank
- Dock known drugs with AutoDock Vina (physics-based, CPU, no special GPU required)
- Filter obvious junk chemistry (Lipinski / PAINS)
- Show a 3D viewer and a ranked table

That is useful as the **control experiment**: “approved-style small molecules against ordinary KRAS G12C.” It is the wrong product to demo as-is, because it never reads the resistance literature, never designs a new molecule, and currently celebrates docking scores even when they contradict lab measurements.

## What “done” looks like on Sunday

A judge who is not on our team can open the app and answer three questions from the screen, not from a pitch:

1. **What did the literature force us to optimize for?** A mutation list with paper IDs.
2. **What did we make that did not exist yesterday?** A protein/peptide sequence and a short reason it was allowed to live.
3. **Why should we not trust it?** A reject list, a WT-vs-mutant comparison, and a note on how similar it is to known structures.

If those three are visible, we have a real entry. If we only have a nicer docking dashboard without resistance evidence and rejects, we do not.

## Who the user is

**Primary user:** a computational biologist or med-chemist at the hackathon judging table (and, later, a scientist deciding whether to order a gene).

They need to see evidence, not confidence. They will try to break the top design with one question. The UI must make that question cheap to ask.

**Secondary user:** our own presenter. The live path must work if Wi‑Fi dies, using saved results from Saturday night.

## One-sentence pitch

iDoctor Design is an AI scientist that reads how KRAS G12C drugs fail, designs a new binder under those constraints, and is only allowed to keep the designs it cannot disprove.

## Glossary (plain language)

| Term | Meaning |
|---|---|
| **KRAS** | A protein that tells the cell to grow. Broken KRAS is common in lung, colon, and pancreatic cancer. |
| **G12C** | A specific spelling mistake in KRAS. The 12th building block becomes cysteine. |
| **Sotorasib / Lumakras** | The first approved drug for KRAS G12C. |
| **Resistance mutation** | A later spelling mistake (for example Y96D) that makes the drug fall off. |
| **WT (wild type)** | Here: KRAS that still has G12C but not the extra resistance mutation. |
| **PDB** | Public warehouse of 3D protein shapes. Each structure has an ID like `6OIM`. |
| **Docking / Vina** | A computer guess of how well a small drug sits in a pocket. Useful, often wrong. |
| **Ki / nM** | Lab measurement of how tightly something binds. Smaller number = tighter. 3 nM is strong; 1000 nM is weak. |
| **Miniprotein / peptide** | A short, designable protein — not a traditional pill, but something we can order as DNA and express. |
| **Paperclip** | Weekend tool: search papers, trials, FDA docs, ChEMBL, PDB as if they were files. |
| **Tamarind** | Weekend tool: fold proteins and run BindCraft (RFdiffusion + ProteinMPNN + AF2) in the cloud. |
| **Claude** | The reasoning model for the critic / scientist voice. Use hackathon API credits. |
| **BindCraft** | Tamarind job type for binder design. Multi-hour; not called inline per UI click. |
| **sequence_design** | Local heuristic generator used when no BindCraft campaign is on disk. Not RFdiffusion. |
| **Benchling** | Optional lab notebook (unused in this demo — Monday card is markdown). |

## Decision log (frozen unless the scientific lead changes it)

| Decision | Choice | Why |
|---|---|---|
| Disease / target | KRAS G12C only | Depth beats four shallow demos. We already have `6OIM` and a compound list. |
| Clinical hook | Sotorasib resistance | Famous, well published, judges will recognize it. |
| Starting mutations | Y96D, H95D, R68S, Y96C (verify with Paperclip) | Enough to show WT vs mutant without boiling the ocean. |
| What we design | Miniprotein or peptide binder to the Switch II region | BindCraft’s native job when a campaign exists; a new sequence is a Track C artifact. |
| What we do not design | A new small-molecule drug from scratch | Too weak for Track C; docking known pills is only the control. |
| GPU | Tamarind for BindCraft + folding; CPU for Vina | Vina does not need a GPU. Proto/Modal is leftover. |
| LLM | Claude (Anthropic) | Critic / scientist voice; template fallback if unset. |
| UI shell | Reuse the Next.js viewer shell; change the scientific contract | Do not rebuild the viewer from zero. |
