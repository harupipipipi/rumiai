import test from "node:test";
import assert from "node:assert/strict";

import { agentDisplayStats, formatCompactNumber, statusTone } from "./AgentCard";
import { summarizeAgentFleet } from "./AgentDashboard";
import type { AgentRecord } from "../lib/api";

const agents: AgentRecord[] = [
  {
    id: "a1",
    name: "Runner",
    status: "running",
    blockers: ["approval"],
    metrics: { ticks: 4, tokens: 1200, tool_calls: 7, failures: 1, cost_usd: 0.25 },
  },
  {
    id: "a2",
    name: "Reviewer",
    status: "waiting_approval",
    metrics: { input_tokens: 300, output_tokens: 200, tool_calls: 2, cost_usd: 0.1 },
  },
];

test("agent cards derive dashboard stats without double-counting explicit total tokens", () => {
  assert.deepEqual(agentDisplayStats(agents[0]), {
    ticks: 4,
    blockers: 1,
    costUsd: 0.25,
    tokens: 1200,
    toolCalls: 7,
    failures: 1,
  });
  assert.equal(agentDisplayStats(agents[1]).tokens, 500);
});

test("agent dashboard summarizes fleet health", () => {
  const summary = summarizeAgentFleet(agents);

  assert.equal(summary.total, 2);
  assert.equal(summary.running, 1);
  assert.equal(summary.waitingApproval, 1);
  assert.equal(summary.tokens, 1700);
  assert.equal(summary.toolCalls, 9);
});

test("agent dashboard helpers format status and compact metrics", () => {
  assert.equal(formatCompactNumber(12500), "12.5k");
  assert.match(statusTone("blocked"), /amber/);
  assert.match(statusTone("failed"), /red/);
});
