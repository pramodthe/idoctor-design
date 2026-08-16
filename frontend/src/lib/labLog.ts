import type { AgentTrace, LabLogEvent } from "./types";

export function tracesToLabLog(traces: AgentTrace[] | undefined | null): LabLogEvent[] {
  const out: LabLogEvent[] = [];
  for (const trace of traces || []) {
    const agent = trace.agent || "agent";
    for (const step of trace.steps || []) {
      const text = step.detail ? `${step.action}: ${step.detail}` : step.action;
      if (text) out.push({ agent, kind: "step", text });
    }
    for (const raw of trace.tool_calls || []) {
      if (!raw || typeof raw !== "object") continue;
      const tc = raw as { tool?: string; input?: unknown; detail?: string };
      const name = tc.tool || "tool";
      let text = "";
      if (tc.input && typeof tc.input === "object" && tc.input !== null) {
        const inp = tc.input as Record<string, unknown>;
        if (typeof inp.command === "string") text = `${name} ${inp.command}`;
        else if (typeof inp.query === "string") text = `${name} ${inp.query}`;
        else text = `${name} ${JSON.stringify(inp).slice(0, 200)}`;
      } else {
        text = `${name} ${tc.detail || ""}`.trim();
      }
      out.push({ agent, kind: "tool", tool: name, text });
    }
    if (trace.output_summary) {
      out.push({ agent, kind: "output", text: trace.output_summary });
    }
    const route = (trace as AgentTrace & { critic_route?: string }).critic_route;
    if (route) out.push({ agent, kind: "route", text: `next → ${route}` });
  }
  return out;
}
