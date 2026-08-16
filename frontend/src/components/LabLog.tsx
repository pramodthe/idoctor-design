"use client";

import { useEffect, useRef } from "react";
import type { LabLogEvent } from "@/lib/types";
import { AGENT_DISPLAY_NAMES, type AgentName } from "@/lib/types";

interface LabLogProps {
  events: LabLogEvent[];
  live?: boolean;
  compact?: boolean;
}

const KIND_LABEL: Record<string, string> = {
  step: "step",
  tool: "tool",
  thought: "think",
  output: "out",
  route: "route",
};

function agentLabel(agent: string): string {
  if (agent in AGENT_DISPLAY_NAMES) {
    return AGENT_DISPLAY_NAMES[agent as AgentName];
  }
  return agent;
}

export default function LabLog({ events, live = false, compact = false }: LabLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  return (
    <div className="flex h-full min-h-[200px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Live activity
        </h3>
        <span className="flex items-center gap-1.5 text-[10px] text-slate-400">
          {live && (
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute h-full w-full animate-ping rounded-full bg-blue-400 opacity-70" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-blue-500" />
            </span>
          )}
          {live ? "streaming" : "record"} · {events.length}
        </span>
      </div>
      <div
        className={`flex-1 overflow-y-auto px-4 py-3 font-mono text-[11px] leading-relaxed ${
          compact ? "max-h-[220px]" : "max-h-[360px]"
        }`}
      >
        {events.length === 0 && (
          <p className="py-6 text-center text-slate-400">
            {live
              ? "Waiting for the first agent…"
              : "No tool trace on this run (fixture/replay may be quiet)."}
          </p>
        )}
        {events.map((ev, i) => (
          <div key={`${i}-${ev.kind}-${ev.text.slice(0, 24)}`} className="lab-log-line mb-1.5">
            <span className="mr-2 text-[10px] uppercase tracking-wide text-slate-400">
              {agentLabel(ev.agent).split(" (")[0]}
            </span>
            <span
              className={`mr-2 rounded px-1 py-px text-[9px] font-semibold uppercase ${
                ev.kind === "tool"
                  ? "bg-blue-50 text-blue-700"
                  : ev.kind === "output"
                    ? "bg-slate-100 text-slate-600"
                    : ev.kind === "route"
                      ? "bg-amber-50 text-amber-700"
                      : "text-slate-400"
              }`}
            >
              {KIND_LABEL[ev.kind] || ev.kind}
            </span>
            <span className="whitespace-pre-wrap break-words text-slate-700">
              {ev.text}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
