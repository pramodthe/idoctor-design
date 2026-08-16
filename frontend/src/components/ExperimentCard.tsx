"use client";

import type { ReactNode } from "react";

interface ExperimentCardProps {
  markdown: string;
}

/** Render experiment.md as simple formatted text (pre with light markdown cues). */
export default function ExperimentCard({ markdown }: ExperimentCardProps) {
  const lines = markdown.split("\n");

  return (
    <div className="font-mono text-[12px] leading-relaxed text-slate-700">
      {lines.map((line, i) => {
        if (line.startsWith("# ")) {
          return (
            <h3
              key={i}
              className="mb-3 font-sans text-base font-semibold tracking-tight text-slate-900"
            >
              {line.slice(2)}
            </h3>
          );
        }
        if (line.startsWith("## ")) {
          return (
            <h4
              key={i}
              className="mb-2 mt-4 font-sans text-xs font-semibold uppercase tracking-wider text-teal-800"
            >
              {line.slice(3)}
            </h4>
          );
        }
        if (line.startsWith("- ")) {
          return (
            <div key={i} className="flex gap-2 pl-1">
              <span className="text-teal-600">·</span>
              <span className="whitespace-pre-wrap">{formatInline(line.slice(2))}</span>
            </div>
          );
        }
        if (line.startsWith("```")) {
          return <div key={i} className="my-1 border-t border-dashed border-slate-200" />;
        }
        if (line.trim() === "") {
          return <div key={i} className="h-2" />;
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {formatInline(line)}
          </p>
        );
      })}
    </div>
  );
}

function formatInline(text: string): ReactNode {
  // Simple **bold** and `code` rendering
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="rounded bg-slate-100 px-1 text-[11px] text-teal-900">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{part}</span>;
  });
}
