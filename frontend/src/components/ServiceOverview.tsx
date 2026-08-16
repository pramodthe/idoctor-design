"use client";

import { useState } from "react";
import type { AgentTrace, Design, VerdictItem } from "@/lib/types";
import { AGENT_DISPLAY_NAMES, type AgentName } from "@/lib/types";

const FLOW: { from: AgentName; to: AgentName }[] = [
  { from: "evidence", to: "designer" },
  { from: "designer", to: "structure" },
  { from: "structure", to: "novelty" },
  { from: "novelty", to: "complex" },
  { from: "complex", to: "physics" },
  { from: "physics", to: "evaluate" },
  { from: "evaluate", to: "critic" },
  { from: "critic", to: "experiment" },
];

const THROUGHPUT_BARS = [
  { time: "12:30", low: 20, med: 15, high: 25 },
  { time: "12:35", low: 35, med: 10, high: 40 },
  { time: "12:40", low: 25, med: 20, high: 15 },
  { time: "12:45", low: 45, med: 25, high: 30 },
  { time: "12:50", low: 60, med: 15, high: 20 },
  { time: "12:55", low: 30, med: 35, high: 10 },
  { time: "13:00", low: 50, med: 20, high: 25 },
  { time: "13:05", low: 40, med: 30, high: 15 },
  { time: "13:10", low: 55, med: 25, high: 20 },
  { time: "13:15", low: 35, med: 15, high: 30 },
];

interface ServiceOverviewProps {
  traces?: AgentTrace[];
  designs?: Design[];
  verdicts?: VerdictItem[];
}

export default function ServiceOverview({
  traces = [],
  designs = [],
  verdicts = [],
}: ServiceOverviewProps) {
  const [selectedRows, setSelectedRows] = useState<Record<string, boolean>>({
    "0": true,
    "1": true,
    "2": true,
  });

  const duration = (agent: string) => {
    const t = traces.find((x) => x.agent === agent);
    if (!t?.duration_seconds) return "1.2s";
    return `${Number(t.duration_seconds).toFixed(1)}s`;
  };

  const rows =
    designs.length > 0
      ? designs.slice(0, 5).map((d, i) => {
          const v = verdicts.find(
            (x) => x.subject_kind === "design" && x.subject_id === d.id
          );
          return {
            id: String(i),
            service: d.id,
            from: "sdkeng-client-sip.dev",
            to: v?.verdict === "promote" ? "5-16-app.agent.datadog.com" : "reject-dead-letter.dev",
            status: v?.verdict || (i % 2 === 0 ? "promote" : "reject"),
            current: d.plddt != null ? `${(d.plddt * 5.8).toFixed(0)}` : "510",
          };
        })
      : [
          { id: "0", service: "sdkeng-client-sip...", from: "5-16-app.agent.datadog.com", to: "sdkeng-client-sip-proxy.dev", status: "reject", current: "510" },
          { id: "1", service: "sawmill.dev", from: "sdkeng-client-sip-proxy.dev", to: "5-16-app.agent.datadog.com", status: "reject", current: "214" },
          { id: "2", service: "api.au1.twilio.com", from: "5-16-0-app.agent.datadogh...", to: "sdkeng-client-sip-proxy.dev", status: "hold", current: "127" },
          { id: "3", service: "sdkeng-client-sip...", from: "sdkeng-client-sip-proxy.dev", to: "5-16-app.agent.datadog.com", status: "hold", current: "83" },
        ];

  const toggleRow = (id: string) => {
    setSelectedRows((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="grid h-full grid-cols-12 gap-3">
      {/* Left Widget: FlowTune Throughput Stacked Bar Chart */}
      <div className="flowtune-glass col-span-5 flex flex-col justify-between p-3.5 relative overflow-hidden">
        {/* Header & Legend */}
        <div className="flex items-center justify-between pb-2">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-bold text-slate-900 tracking-tight">Throughput</span>
          </div>

          <div className="flex items-center gap-3 text-[10px] font-semibold text-slate-500">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-xs bg-[#FF3B69]" />
              <span className="text-slate-400 font-normal">High</span>
              <span className="text-slate-700">439</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-xs bg-[#F59E0B]" />
              <span className="text-slate-400 font-normal">Medium</span>
              <span className="text-slate-700">146</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-xs bg-[#3B82F6]" />
              <span className="text-slate-400 font-normal">Low</span>
              <span className="text-slate-700">2.3k</span>
            </span>
          </div>
        </div>

        {/* Chart Area with Floating KPI Badge */}
        <div className="relative flex items-end justify-between gap-1.5 pt-4 pb-1">
          {/* Floating Alerts Badge */}
          <div className="absolute left-2 top-0 z-10 flowtune-subcard bg-white/95 px-3 py-1.5 shadow-md shadow-slate-900/5 ring-1 ring-slate-100 flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-50 text-blue-600">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-sm font-extrabold text-slate-900">52</span>
                <span className="text-[10px] font-bold text-emerald-600">Excellent</span>
              </div>
              <p className="text-[9px] text-slate-400 font-medium leading-none">pLDDT &gt; 80 metric</p>
            </div>
          </div>

          {/* Stacked Bars */}
          {THROUGHPUT_BARS.map((bar, idx) => (
            <div key={idx} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full max-w-[18px] flex-col-reverse overflow-hidden rounded-t-md shadow-xs" style={{ height: "65px" }}>
                <div style={{ height: `${bar.low}%` }} className="bg-[#3B82F6]" />
                <div style={{ height: `${bar.med}%` }} className="bg-[#F59E0B]" />
                <div style={{ height: `${bar.high}%` }} className="bg-[#FF3B69]" />
              </div>
              <span className="text-[9px] font-medium text-slate-400">{bar.time}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right Widget: FlowTune Service Overview Notched Table Sheet */}
      <div className="flowtune-glass col-span-7 flex flex-col justify-between overflow-hidden p-3.5">
        {/* Header Tab Notch */}
        <div className="flex items-center justify-between pb-2">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-slate-100 text-slate-600">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </span>
            <span className="text-[13px] font-bold text-slate-900 tracking-tight">Service Overview</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button type="button" className="chrome-btn" title="Export">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </button>
            <button type="button" className="chrome-btn" title="Expand">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
            </button>
          </div>
        </div>

        {/* Table Content */}
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-slate-100 text-[10px] font-semibold text-slate-400">
                <th className="w-6 py-1.5 pl-1"></th>
                <th className="py-1.5 font-medium">Service</th>
                <th className="py-1.5 font-medium">From</th>
                <th className="py-1.5 font-medium">To</th>
                <th className="py-1.5 font-medium">Status</th>
                <th className="py-1.5 text-right font-medium pr-1">Current (kBps) ▾</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-50/80 hover:bg-slate-50/60 transition-colors">
                  <td className="py-1.5 pl-1">
                    <input
                      type="checkbox"
                      checked={Boolean(selectedRows[r.id])}
                      onChange={() => toggleRow(r.id)}
                      className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                  </td>
                  <td className="py-1.5 font-medium text-slate-800 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                    <span className="truncate max-w-[110px]">{r.service}</span>
                  </td>
                  <td className="py-1.5 font-mono text-[10px] text-slate-500 truncate max-w-[130px]">{r.from}</td>
                  <td className="py-1.5 font-mono text-[10px] text-slate-500 truncate max-w-[130px]">{r.to}</td>
                  <td className="py-1.5">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                        r.status === "reject"
                          ? "bg-[#FF3B69] text-white"
                          : r.status === "hold"
                            ? "bg-[#FF9500] text-white"
                            : "bg-[#10B981] text-white"
                      }`}
                    >
                      {r.status === "reject" ? "Alert" : r.status === "hold" ? "Warm" : "OK"}
                    </span>
                  </td>
                  <td className="py-1.5 text-right font-mono text-[11px] font-bold text-slate-700 pr-1">{r.current}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
