# iDoctor Design spec

This folder is the source of truth for the re:AGENT rebuild.

Do not invent product behavior from stale notes. If code and this spec disagree, **change the code**. The product name is **iDoctor Design**.

## What this product is

**iDoctor Design** is an AI scientist for one clinical problem: KRAS G12C drugs such as sotorasib (Lumakras) work, then stop working because the protein mutates.

The agent:

1. Reads papers, trials, and databases (Paperclip)
2. Writes a design spec a scientist can inspect
3. Designs a new protein/peptide binder (Proto)
4. Tests designs (Tamarind + existing docking)
5. Is allowed to **reject** its own work
6. Hands a wet-lab person a Monday experiment (**markdown** card; Benchling unused)

Sunday we demo a sequence that did not exist Saturday, plus the designs we threw away and why.

## How to use these docs (spec-driven)

Read in this order:

| # | File | Who it is for |
|---|---|---|
| 1 | [PROJECT_BRIEF.md](./PROJECT_BRIEF.md) | Everyone. Plain language. What we are building and why. |
| 2 | [REQUIREMENTS.md](./REQUIREMENTS.md) | Product + engineering. Numbered, testable rules. |
| 3 | [TODO.md](./TODO.md) | The 10-person weekend. Checkboxes by workstream. |
| 4 | [ARCHITECTURE.md](./ARCHITECTURE.md) | Implementers. How the pieces connect. |
| 5 | [DATA_CONTRACTS.md](./DATA_CONTRACTS.md) | Every Cursor window. Shared JSON files. **Read this before writing code.** |
| 6 | [ACCEPTANCE.md](./ACCEPTANCE.md) | Demo + judging. How we know it is done. |

Example payloads live in [`fixtures/`](./fixtures/). UI, critic, and eval teams must build against these files on Saturday morning **before** Paperclip or Proto return real data.

## Rules for vibe coding

1. One scientific question. Not four diseases.
2. Do not pitch GPU utilization or “Shikonin beats Paxlovid.”
3. Every promote/reject needs a citation or a metric.
4. Teams share files from `DATA_CONTRACTS.md`, not private schemas.
5. If a partner API is down, load the matching fixture and keep going.
6. Check a box in `TODO.md` only when the acceptance note is true.

## What we keep from the old repo

Keep AutoDock Vina, RDKit, the 3D viewer, LangGraph, and the KRAS G12C compound library (`6OIM`). That stack is the **small-molecule control arm** — proof that approved-style drugs look fine on the original protein and are the wrong answer under resistance.

Do not keep the four-target docking demo as the product.
