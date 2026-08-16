"use client";

import type { AppState } from "@/lib/types";

const STATUS_CONFIG = {
  idle: { label: "READY", color: "bg-teal-600", text: "text-teal-700" },
  running: { label: "RUNNING", color: "bg-teal-500 animate-pulse", text: "text-teal-700" },
  completed: { label: "COMPLETE", color: "bg-emerald-600", text: "text-emerald-700" },
};

export default function Header({ appState }: { appState: AppState }) {
  const status = STATUS_CONFIG[appState];

  return (
    <header className="relative border-b border-slate-200/80 bg-white/75 backdrop-blur-xl">
      {appState === "running" && (
        <div className="absolute bottom-0 left-0 h-[2px] w-full overflow-hidden">
          <div className="shimmer-bar h-full w-full bg-gradient-to-r from-transparent via-teal-500 to-transparent" />
        </div>
      )}
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.png"
            alt="iDoctor Design"
            className="h-10 w-10 rounded-lg object-cover"
          />
          <div>
            <h1 className="font-display text-xl font-semibold tracking-tight text-slate-900">
              iDoctor Design
            </h1>
            <p className="text-[11px] tracking-wide text-slate-500">
              KRAS G12C resistance · evidence before confidence
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-1.5 sm:flex">
            {["Paperclip", "Tamarind", "Claude"].map((tag) => (
              <span
                key={tag}
                className="border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-500"
              >
                {tag}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2 border border-slate-200 bg-slate-50 px-3 py-1">
            <div className="relative">
              <div className={`h-2 w-2 rounded-full ${status.color}`} />
              {appState === "running" && (
                <div className="absolute inset-0 h-2 w-2 rounded-full text-teal-500 pulse-ring" />
              )}
            </div>
            <span className={`text-xs font-semibold tracking-wider ${status.text}`}>
              {status.label}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
