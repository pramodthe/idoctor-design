"use client";

import { useState } from "react";
import type { SpecMutation, MutationEffect } from "@/lib/types";

const EFFECT_STYLES: Record<MutationEffect, string> = {
  loss: "bg-red-50 text-red-700 border-red-200",
  reduced: "bg-amber-50 text-amber-800 border-amber-200",
  unclear: "bg-slate-100 text-slate-600 border-slate-200",
};

interface MutationMapProps {
  mutations: SpecMutation[];
}

export default function MutationMap({ mutations }: MutationMapProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      {mutations.map((m) => {
        const open = expanded === m.id;
        return (
          <div
            key={m.id}
            className="border-b border-slate-200/80 last:border-0"
          >
            <button
              type="button"
              onClick={() => setExpanded(open ? null : m.id)}
              className="flex w-full items-start gap-3 py-3 text-left transition-colors hover:bg-teal-50/40"
            >
              <span className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
                {m.id}
              </span>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${EFFECT_STYLES[m.effect_on_sotorasib]}`}
              >
                {m.effect_on_sotorasib}
              </span>
              <span className="min-w-0 flex-1 text-xs text-slate-500">
                {m.sources.map((s) => s.id).join(", ")}
              </span>
              <svg
                className={`mt-1 h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {open && (
              <div className="animate-fade-in space-y-3 pb-4 pl-1">
                {m.notes && (
                  <p className="text-xs leading-relaxed text-slate-600">{m.notes}</p>
                )}
                {m.sources.map((s) => (
                  <div
                    key={`${s.kind}-${s.id}`}
                    className="border-l-2 border-teal-600/40 pl-3"
                  >
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-teal-700">
                        {s.kind}
                      </span>
                      <span className="font-mono text-xs text-slate-800">{s.id}</span>
                      {s.title && (
                        <span className="text-xs text-slate-500">{s.title}</span>
                      )}
                    </div>
                    {s.quote && (
                      <blockquote className="mt-1 text-xs italic leading-relaxed text-slate-600">
                        &ldquo;{s.quote}&rdquo;
                      </blockquote>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
