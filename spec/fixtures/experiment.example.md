# Monday experiment — des_001 (fixture)

This card is **demo data**. Replace sequence and numbers from the live promoted design.

## Construct

- Name: iDoctorDesign-des_001
- Type: miniprotein (His-tagged expression construct as needed)
- Target: KRAS G12C Switch II region, resistance check on Y96D

## Sequence

```
GSHMASGGSGSGSGSGSGSDDEEELLKKLKEELKKLKEELKKLGGS
```

## Production

- Order a gene (codon-optimized) or peptide as appropriate for length.
- Express in E. coli, Ni-NTA purify, polish if needed.
- Quality: intact mass + SDS-PAGE.

## Binding assay

- Method: SPR or BLI.
- Ligand: KRAS G12C (WT in this project’s language) and KRAS G12C/Y96D.
- Analyte: des_001.
- Include sotorasib as a small-molecule control on the same proteins if the assay allows.

## Number that would change our mind

- Promote to a real follow-up only if **Y96D KD is within 10× of G12C KD** and both are tighter than a negative-control miniprotein.
- If Y96D binding is lost while G12C binding remains, the critic should have rejected this as `wt_only_signal` — the computer was wrong.

## What would falsify the computational story

- No binding to either protein.
- Equal binding to an off-target GTPase.
- Sequence turns out to be a known binder we failed to catch in novelty check.
