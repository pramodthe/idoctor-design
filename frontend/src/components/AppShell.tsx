"use client";

import type { ReactNode } from "react";

export type NavSection =
  | "overview"
  | "structure"
  | "evidence";

interface AppShellProps {
  topBar: ReactNode;
  children: ReactNode;
}

export default function AppShell({
  topBar,
  children,
}: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50/50">
      {topBar}
      <main className="min-h-0 flex-1 overflow-y-auto p-4 lg:p-5">
        {children}
      </main>
    </div>
  );
}


