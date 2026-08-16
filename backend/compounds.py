"""KRAS G12C compound library for iDoctor Design docking control arm."""

KRAS_COMPOUNDS = [
    {
        "id": "sotorasib",
        "name": "Sotorasib (Lumakras)",
        "smiles": "C=CC(=O)N1CCN(c2nc(OC)ncc2F)C(=O)[C@@H]1c1cc(Cl)c(F)c(NC(=O)C2CC2)c1",
        "known_ki_nm": 6.3,
    },
    {
        "id": "adagrasib",
        "name": "Adagrasib (Krazati)",
        "smiles": "C=CC(=O)N1CCN(c2c(F)cc(OC)nc2N3CCCC3)CC1c1cc(Cl)c(F)c(NC(=O)C2CC2)c1",
        "known_ki_nm": 0.13,
    },
    {
        "id": "ars1620",
        "name": "ARS-1620",
        "smiles": "C=CC(=O)Nc1cc(N2CCN(c3ncnc4[nH]ccc34)CC2)c(F)cc1Cl",
        "known_ki_nm": 120.0,
    },
    {
        "id": "ars853",
        "name": "ARS-853",
        "smiles": "C=CC(=O)Nc1cc(NC(=O)c2ccccn2)c(OC)cc1Cl",
        "known_ki_nm": 1700.0,
    },
    {
        "id": "mrtx849",
        "name": "MRTX849 (Adagrasib analog)",
        "smiles": "C=CC(=O)N1CCN(c2nc(N3CCCC3)ncc2F)C[C@@H]1c1cc(Cl)c(F)c(N)c1",
        "known_ki_nm": 5.2,
    },
    {
        "id": "bi2852",
        "name": "BI-2852",
        "smiles": "CC1(C)CC(NC(=O)c2cccc(C(F)(F)F)c2)CC(C)(C)N1c1ccnc(Cl)n1",
        "known_ki_nm": 740.0,
    },
    {
        "id": "gdc6036",
        "name": "GDC-6036 (Divarasib)",
        "smiles": "C=CC(=O)N1CCN(c2cnc(OC)nc2)CC1c1cc(Cl)c(F)c(NC(=O)C2CC2)c1",
        "known_ki_nm": 0.8,
    },
    {
        "id": "jdq443",
        "name": "JDQ443",
        "smiles": "C=CC(=O)Nc1cc(N2CCN(c3ncc(C#N)cn3)CC2)c(F)cc1Cl",
        "known_ki_nm": 2.1,
    },
    {
        "id": "lyn1604",
        "name": "LY3537982",
        "smiles": "C=CC(=O)N1CCN(c2nc(OCC)ncc2Cl)C[C@@H]1c1ccc(F)c(NC(=O)C2CC2)c1",
        "known_ki_nm": 0.5,
    },
    {
        "id": "rmcx684",
        "name": "RMC-6684",
        "smiles": "C=CC(=O)N1CCN(c2ccnc(NC3CCOCC3)n2)CC1c1cc(Cl)c(F)c(N)c1",
        "known_ki_nm": 1.4,
    },
    {
        "id": "compound12_jmc",
        "name": "Compound 12 (J.Med.Chem 2022)",
        "smiles": "C=CC(=O)Nc1cc(NC(=O)c2cccc(OC)c2)c(OC)cc1Cl",
        "known_ki_nm": 340.0,
    },
    {
        "id": "kras_frag1",
        "name": "Fragment hit A (Switch II)",
        "smiles": "Oc1ccc(-c2cn[nH]c2)cc1Cl",
        "known_ki_nm": 8500.0,
    },
    {
        "id": "kras_frag2",
        "name": "Fragment hit B (Switch II)",
        "smiles": "c1ccc(-c2cc(O)no2)c(F)c1",
        "known_ki_nm": 12000.0,
    },
    {
        "id": "bax2398",
        "name": "BAY-293",
        "smiles": "CC(C)c1cc(NC(=O)c2cccc(C(F)(F)F)c2)no1",
        "known_ki_nm": 2100.0,
    },
    {
        "id": "sml8708",
        "name": "SML-8-73-1",
        "smiles": "O=P(O)(O)OC[C@H]1OC(n2cnc3c(N)ncnc32)[C@H](O)[C@@H]1O",
        "known_ki_nm": 15000.0,
    },
]

TARGET_COMPOUNDS = {
    "6OIM": KRAS_COMPOUNDS,
}
