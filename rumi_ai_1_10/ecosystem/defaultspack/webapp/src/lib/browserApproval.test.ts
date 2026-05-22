import test from "node:test";
import assert from "node:assert/strict";

import type { ChatUiMessage } from "../renderers/types";
import { pendingBrowserApproval, pendingCodingApproval, staleCodingApproval } from "./browserApproval";

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

test("returns pending coding approval requests without browser tokens", () => {
  const approval = pendingCodingApproval([
    agentMessage({
      events: [{
        type: "approval_requested",
        tool_name: "coding_file_create",
        tool_call_id: "call_file",
        action: "coding_file_create",
        operation: "file.create",
        payload: { path: "index.html", content: "<html></html>" },
        requires_approval: true,
        approval_request_id: "apr_1",
        risk_level: "medium",
        display_summary: "Create index.html",
      }],
    }),
  ]);

  assert.deepEqual(approval, {
    action: "coding_file_create",
    operation: "file.create",
    payload: { path: "index.html", content: "<html></html>" },
    requestId: "apr_1",
    riskLevel: "medium",
    summary: "Create index.html",
    toolCallId: "call_file",
    toolName: "coding_file_create",
  });
});

test("returns generic browser tool approval requests when they use approval request ids", () => {
  const approval = pendingCodingApproval([
    agentMessage({
      toolLogs: [{
        tool_name: "browser_computer",
        tool_call_id: "call_browser",
        arguments: { action: "computer.click", payload: { x: 10, y: 20 } },
        result: {
          widget: {
            type: "approval_request",
            tool_name: "browser_computer",
            approval_required: true,
            approval_request_id: "apr_browser",
            operation: "tool.browser_computer",
          },
        },
      }],
    }),
  ]);

  assert.equal(approval?.toolName, "browser_computer");
  assert.equal(approval?.requestId, "apr_browser");
  assert.deepEqual(approval?.payload, { action: "computer.click", payload: { x: 10, y: 20 } });
});

test("returns stale browser tool approvals when no token or request id exists", () => {
  const approval = staleCodingApproval([
    agentMessage({
      toolLogs: [{
        tool_name: "browser_computer",
        arguments: { action: "computer.click" },
        result: {
          widget: {
            type: "approval_request",
            tool_name: "browser_computer",
            approval_required: true,
            arguments: { action: "computer.click" },
          },
        },
      }],
    }),
  ]);

  assert.equal(approval?.toolName, "browser_computer");
  assert.equal(approval?.reason, "missing_approval_request_id");
});

test("uses tool log arguments as coding approval payload fallback", () => {
  const approval = pendingCodingApproval([
    agentMessage({
      toolLogs: [{
        tool_name: "coding_file_create",
        tool_call_id: "call_file",
        arguments: { path: "index.html", content: "<html></html>" },
        result: {
          status: "ok",
          data: {
            approval_required: true,
            approval_request_id: "apr_log",
            operation: "file.create",
          },
        },
      }],
    }),
  ]);

  assert.equal(approval?.requestId, "apr_log");
  assert.deepEqual(approval?.payload, { path: "index.html", content: "<html></html>" });
});

test("ignores expired coding approval requests", () => {
  const approval = pendingCodingApproval([
    agentMessage({
      events: [{
        type: "approval_requested",
        tool_name: "coding_file_create",
        operation: "file.create",
        payload: { path: "index.html" },
        requires_approval: true,
        approval_request_id: "apr_expired",
        approval_expires_in_seconds: 10,
        timestamp: "2026-05-20T08:05:40Z",
      }],
    }),
  ], Date.parse("2026-05-20T08:06:00Z"));

  assert.equal(approval, null);
});

test("returns stale coding approvals without actionable request ids", () => {
  const approval = staleCodingApproval([
    agentMessage({
      metadata: {
        pendingApproval: {
          tool_name: "coding_file_create",
          tool_call_id: "call_file",
          operation: "file.create",
          payload: { path: "index.html" },
          approval_required: true,
          risk_level: "medium",
        },
      },
      toolLogs: [{
        tool_name: "coding_file_create",
        tool_call_id: "call_file",
        arguments: { path: "index.html" },
        result: {
          widget: {
            type: "approval_request",
            approval_required: true,
            risk_level: "medium",
            arguments: { path: "index.html" },
          },
        },
      }],
    }),
  ]);

  assert.deepEqual(approval, {
    operation: "file.create",
    payload: { path: "index.html" },
    reason: "missing_approval_request_id",
    riskLevel: "medium",
    summary: undefined,
    toolCallId: "call_file",
    toolName: "coding_file_create",
  });
});

test("does not treat actionable coding approvals as stale", () => {
  const approval = staleCodingApproval([
    agentMessage({
      toolLogs: [{
        tool_name: "coding_file_create",
        arguments: { path: "index.html" },
        result: {
          status: "ok",
          data: {
            approval_required: true,
            approval_request_id: "apr_log",
            operation: "file.create",
          },
        },
      }],
    }),
  ]);

  assert.equal(approval, null);
});
