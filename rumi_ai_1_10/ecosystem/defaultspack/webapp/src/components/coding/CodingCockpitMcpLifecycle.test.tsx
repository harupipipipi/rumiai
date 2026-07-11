import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  approvedMcpLifecycleRetryReason,
  isMcpLifecycleApprovalRequest,
  mcpServerDetailRows,
  redactMcpArguments,
  type PendingMcpLifecycle,
} from "./CodingCockpit";

test("MCP server details expose lifecycle state without leaking credentials", () => {
  const server = {
    server_id: "filesystem",
    name: "Filesystem",
    transport: "stdio",
    status: "connected",
    connected: true,
    tools: ["files.read", "files.search"],
    registered_config: {
      command: "/usr/local/bin/mcp-filesystem",
      args: [
        "--root",
        "/repo",
        "--token",
        "raw-token-value",
        "api_key=raw-api-key",
        "https://user:password@example.test/sse?access_token=raw#fragment",
      ],
      cwd: "/repo",
      env: {
        API_TOKEN: "raw-env-secret",
        PUBLIC_FLAG: "raw-public-value",
      },
    },
    permissions: { approved: true },
  } as Parameters<typeof mcpServerDetailRows>[0];

  const text = JSON.stringify(mcpServerDetailRows(server));

  assert.match(text, /connected/);
  assert.match(text, /stdio/);
  assert.match(text, /mcp-filesystem/);
  assert.match(text, /\[redacted\]/);
  assert.match(text, /API_TOKEN/);
  assert.match(text, /PUBLIC_FLAG/);
  assert.match(text, /files\.read/);
  for (const secret of [
    "raw-token-value",
    "raw-api-key",
    "raw-env-secret",
    "raw-public-value",
    "user:password",
    "access_token",
    "#fragment",
  ]) {
    assert.equal(text.includes(secret), false, `unexpected MCP detail leak: ${secret}`);
  }
});

test("MCP argument redaction binds secret flags to their following values", () => {
  assert.deepEqual(
    redactMcpArguments([
      "--token",
      "secret-after-flag",
      "password=inline-secret",
      "https://user:pass@example.test/api?token=query#fragment",
      "--safe",
    ]),
    [
      "--token",
      "[redacted]",
      "password=[redacted]",
      "https://example.test/api",
      "--safe",
    ],
  );
});

test("MCP lifecycle approval retries require the exact request and workspace", () => {
  const pending: PendingMcpLifecycle = {
    requestId: "approval-lifecycle-1",
    action: "remove",
    serverId: "filesystem",
    workspaceId: "ws-main",
  };
  const approved = {
    request_id: "approval-lifecycle-1",
    status: "approved",
    approved: true,
    token: "single-use-token",
  };

  assert.equal(approvedMcpLifecycleRetryReason(pending, "ws-main", approved), null);
  assert.match(
    approvedMcpLifecycleRetryReason(null, "ws-main", approved) ?? "",
    /stale|settled/,
  );
  assert.match(
    approvedMcpLifecycleRetryReason(pending, "ws-other", approved) ?? "",
    /workspace changed/,
  );
  assert.equal(
    approvedMcpLifecycleRetryReason(pending, "ws-main", {
      ...approved,
      approved: false,
      token: undefined,
      reason: "denied for fixture",
    }),
    "denied for fixture",
  );
  assert.equal(isMcpLifecycleApprovalRequest({
    request_id: "x",
    operation: "tool.mcp_disconnect",
    risk_level: "medium",
    status: "pending",
  }), true);
  assert.equal(isMcpLifecycleApprovalRequest({
    request_id: "x",
    operation: "tool.mcp_remove",
    risk_level: "high",
    status: "pending",
  }), true);
});

test("Coding Cockpit exposes reviewed MCP lifecycle controls", () => {
  const source = readFileSync(resolve(import.meta.dirname, "CodingCockpit.tsx"), "utf8");
  const resources = readFileSync(
    resolve(import.meta.dirname, "../../features/coding/resources/codingResources.ts"),
    "utf8",
  );

  assert.match(source, /aria-expanded=\{expanded\}/);
  assert.match(source, />\s*Reconnect\s*</);
  assert.match(source, />\s*Disconnect\s*</);
  assert.match(source, />\s*Confirm remove\s*</);
  assert.match(source, /removes projected tools, and deletes the saved registration/);
  assert.match(source, /separate Approvals queue/);
  assert.doesNotMatch(source, /codingResources\.approveCodingApproval/);
  assert.match(resources, /disconnectMcpServer/);
  assert.match(resources, /removeMcpServer/);
  assert.match(resources, /\/api\/tools\/mcp\/disconnect/);
});
