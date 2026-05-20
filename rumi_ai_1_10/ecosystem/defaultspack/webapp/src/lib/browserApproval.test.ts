import test from "node:test";
import assert from "node:assert/strict";

import type { ChatUiMessage } from "../renderers/types";
import { pendingBrowserApproval } from "./browserApproval";

function agentMessage(patch: Partial<ChatUiMessage>): ChatUiMessage {
  return {
    id: "m1",
    role: "agent",
    content: [],
    rawText: "",
    events: [],
    toolLogs: [],
    ...patch,
  };
}

test("returns a fresh browser computer approval request", () => {
  const approval = pendingBrowserApproval([
    agentMessage({
      events: [{
        type: "approval_requested",
        tool_name: "computer_use",
        action: "computer.screenshot",
        payload: { app: "Google Chrome" },
        requires_approval: true,
        approval_token: "tok",
        approval_expires_in_seconds: 300,
        timestamp: "2026-05-20T08:05:40Z",
      }],
    }),
  ], Date.parse("2026-05-20T08:06:00Z"));

  assert.deepEqual(approval, {
    action: "computer.screenshot",
    payload: { app: "Google Chrome" },
    token: "tok",
    toolName: "computer_use",
  });
});

test("ignores expired browser computer approvals", () => {
  const approval = pendingBrowserApproval([
    agentMessage({
      events: [{
        type: "approval_requested",
        tool_name: "computer_use",
        action: "computer.screenshot",
        payload: { app: "Google Chrome" },
        requires_approval: true,
        approval_token: "tok",
        approval_expires_in_seconds: 300,
        timestamp: "2026-05-20T08:05:40Z",
      }],
    }),
  ], Date.parse("2026-05-20T08:11:00Z"));

  assert.equal(approval, null);
});

test("ignores redacted approval tokens from stored tool logs", () => {
  const approval = pendingBrowserApproval([
    agentMessage({
      toolLogs: [{
        tool_name: "computer_use",
        timestamp: "2026-05-20T08:05:40Z",
        result: {
          status: "ok",
          data: {
            widget: {
              type: "browser_computer",
              action: "computer.screenshot",
              requires_approval: true,
              approval_token: "[redacted]",
              approval_expires_in_seconds: 300,
              payload: { app: "Google Chrome" },
            },
          },
        },
      }],
    }),
  ], Date.parse("2026-05-20T08:06:00Z"));

  assert.equal(approval, null);
});
