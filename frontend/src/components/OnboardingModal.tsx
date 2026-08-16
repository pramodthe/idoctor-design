"use client";

interface OnboardingModalProps {
  onDismiss: () => void;
}

export default function OnboardingModal({ onDismiss }: OnboardingModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm">
      <div className="animate-fade-in mx-4 w-full max-w-md border border-slate-200 bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-teal-300">
              iD
          </div>
          <div>
            <h2 className="font-display text-lg font-semibold text-slate-900">
              iDoctor Design
            </h2>
            <p className="text-xs text-slate-500">Why Lumakras fails — and what to test next</p>
          </div>
        </div>

        <div className="mb-6 space-y-3 text-sm leading-relaxed text-slate-600">
          <p>
            KRAS G12C cancers often respond to sotorasib (Lumakras), then relapse when pocket
            mutations such as Y96D stop the drug from binding.
          </p>
          <p>
            iDoctor Design reads that resistance record, designs a new miniprotein or peptide under
            those constraints, and docks known small molecules only as a control.
          </p>
          <p>
            A critic rejects designs that look good on wild-type G12C alone, copy known PDB
            binders, or contradict the literature — the reject pile is part of the product.
          </p>
          <p>
            What you get is a promoted sequence you can check, plus a Monday wet-lab card for
            G12C versus the mutant.
          </p>
          <p>
            If partner APIs are down, run fixture or replay; the demo-data
            banner (className demo-banner) will say so. Do not treat heuristic
            sequence_design as RFdiffusion.
          </p>
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={onDismiss}
            className="bg-slate-900 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-teal-800"
          >
            Open lab
          </button>
        </div>
      </div>
    </div>
  );
}
