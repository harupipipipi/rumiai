import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ApprovalQueue } from "./ApprovalQueue";
import { CheckpointPanel } from "./CheckpointPanel";
import {
  approvedMcpLifecycleRetryReason,
  CodingCockpit,
  isMcpLifecycleApprovalRequest,
  mcpServerDetailRows,
  redactMcpArguments,
  type PendingMcpLifecycle,
} from "./CodingCockpit";
import { DiffPanel } from "./DiffPanel";
import { TerminalPanel } from "./TerminalPanel";
import {
  approvedMcpRetryReason,
  mcpApprovalReviewRows,
  sameMcpDraft,
  type McpConnectionDraft,
} from "./mcpApproval";

test("approval queue renders cockpit approval decisions", () => {
  const html = renderToStaticMarkup(createElement(ApprovalQueue, { initialApprovals: [{ request_id: "apr_1", operation: "terminal.exec", risk_level: "high", status: "pending", display_summary: "terminal.exec: git push origin main" }] }));
  assert.match(html, /terminal\.exec/);
  assert.match(html, /許可/);
  assert.match(html, /拒否/);
});

test("approval queue separates expired pending approvals from active approvals", () => {
  const html = renderToStaticMarkup(createElement(ApprovalQueue, { initialApprovals: [{ request_id: "apr_expired", operation: "terminal.exec", risk_level: "medium", status: "pending", display_summary: "terminal.exec: old command", expires_at: 1 }] }));
  assert.match(html, /Active pending approvals/);
  assert.match(html, />0<\/span>/);
  assert.match(html, /No active approvals/);
  assert.match(html, /Recent approval history/);
  assert.match(html, /expired/);
  assert.doesNotMatch(html, />許可</);
  assert.doesNotMatch(html, />拒否</);
});

test("MCP approval review renders the complete normalized redacted contract", () => {
  const approval = { request_id: "apr_mcp_1", operation: "tool.mcp_connect", risk_level: "high", status: "pending", display_summary: "Connect reviewed MCP server", details: { config: { env: { FAKE_SECRET: "must-not-render" } }, mcp_review: { executable: "/usr/bin/fake-mcp", transport: "stdio", args: ["--safe-fixture"], cwd: "/fake/workspace", redacted_env: { FAKE_SECRET: "[redacted]" }, server_source: "shared_registry", capabilities: ["tools"], tools: ["fake.read"], network: "disabled", filesystem: "workspace-only", persistence: "process lifetime", consequences: ["Starts a local fake fixture process"] } } };
  const html = renderToStaticMarkup(createElement(ApprovalQueue, { initialApprovals: [approval] }));
  const rows = mcpApprovalReviewRows(approval);
  for (const label of ["Executable", "Transport", "Arguments", "Working directory", "Environment (redacted)", "Server source", "Capabilities", "Tools", "Network", "Filesystem", "Persistence", "Consequences"]) {
    assert.ok(rows.some((row) => row.label === label), `${label} should be present`);
    assert.match(html, new RegExp(label.replace(/[()]/g, "\\$&")));
  }
  assert.match(html, /\[redacted\]/);
  assert.doesNotMatch(html, /must-not-render/);
});

test("MCP approved retry is single-attempt and rejects config or workspace mutation", () => {
  const draft: McpConnectionDraft = { serverId: "fixture-mcp", command: "/usr/bin/fake-mcp", args: ["--fixture"], workspaceId: "ws-a" };
  const pending = { requestId: "apr_mcp_1", draft };
  const approved = { request_id: "apr_mcp_1", status: "approved", approved: true, token: "fake-single-use-token" };
  assert.equal(approvedMcpRetryReason(pending, draft, approved), null);
  assert.match(approvedMcpRetryReason(null, draft, approved) ?? "", /stale|settled/);
  assert.match(approvedMcpRetryReason(pending, { ...draft, command: "/usr/bin/changed" }, approved) ?? "", /changed/);
  assert.match(approvedMcpRetryReason(pending, { ...draft, workspaceId: "ws-b" }, approved) ?? "", /changed/);
  assert.equal(sameMcpDraft(draft, { ...draft }), true);
  assert.equal(sameMcpDraft(draft, { ...draft, args: ["--mutated"] }), false);
});

test("MCP retry reports denial expiry and already-settled decisions as recoverable", () => {
  const draft: McpConnectionDraft = { serverId: "fixture-mcp", command: "/usr/bin/fake-mcp", args: [], workspaceId: "ws-a" };
  const pending = { requestId: "apr_mcp_1", draft };
  for (const status of ["denied", "expired", "consumed", "obsolete"]) {
    const reason = approvedMcpRetryReason(pending, draft, { request_id: "apr_mcp_1", status, approved: false, reason: `fixture ${status}` });
    assert.equal(reason, `fixture ${status}`);
  }
});

test("CodingCockpit never approves an MCP request from the requester path", () => {
  const source = readFileSync(new URL("./CodingCockpit.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /approveCodingApproval/);
  assert.match(source, /result\.approval_required/);
  assert.match(source, /rememberPendingMcp/);
});

test("diff panel renders status, content, and an operable refresh control", () => {
  const html = renderToStaticMarkup(createElement(DiffPanel, { initialStatus: { branch: "main", clean: false, modified: ["src/App.tsx"] }, initialDiff: { diff: "-old\n+new", files_changed: 1, files: ["src/App.tsx"] } }));
  assert.match(html, /main/);
  assert.match(html, /src\/App\.tsx/);
  assert.match(html, /-old/);
  assert.match(html, /\+new/);
  assert.match(html, /aria-label="Refresh diff"/);
});

test("checkpoint panel renders refresh and restore-review controls for supplied snapshots", () => {
  const html = renderToStaticMarkup(createElement(CheckpointPanel, { workspaceId: "ws-main", initialCheckpoints: [{ snapshot_id: "snapshot-1", path: "/repo/.rumi/checkpoints/snapshot-1" }], initialDiff: { diff: "-before\n+after", files_changed: 1, files: ["src/App.tsx"] } }));
  assert.match(html, /snapshot-1/);
  assert.match(html, /Refresh checkpoints/);
  assert.match(html, /Review restore snapshot-1/);
  assert.match(html, /Restore diff/);
  assert.match(html, /-before/);
});

test("terminal panel renders classification and risk reasons", () => {
  const html = renderToStaticMarkup(createElement(TerminalPanel, { initialLogs: [{ id: "log-1", command: "git push origin main", approval_required: true, classification: "high", risk_reasons: ["network"], exit_code: null, stdout: "", stderr: "" }] }));
  assert.match(html, /git push origin main/);
  assert.match(html, /approval/);
  assert.match(html, /network/);
});

test("coding cockpit renders workspace and sidecar sections", () => {
  const html = renderToStaticMarkup(createElement(CodingCockpit, { workspaces: [{ workspace_id: "ws-main", label: "Main Repo", root_path: "/repo", trusted: true }], selectedWorkspaceId: "ws-main" }));
  assert.match(html, /Coding Cockpit/);
  assert.match(html, /Main Repo/);
  assert.match(html, /Approvals/);
  assert.match(html, /Checkpoints/);
  assert.match(html, /Terminal/);
  assert.match(html, /Browser/);
  assert.match(html, /MCP/);
  assert.match(html, /Agents/);
});

test("MCP requester never approves its own request", () => {
  const source = readFileSync(resolve(import.meta.dirname, "CodingCockpit.tsx"), "utf8");
  assert.doesNotMatch(source, /codingResources\.approveCodingApproval/);
  assert.match(source, /separate Approvals queue/);
  assert.match(source, /requesting form cannot approve its own request/);
});

test("MCP server details expose lifecycle state without leaking credentials", () => {
  const server = { server_id: "filesystem", name: "Filesystem", transport: "stdio", status: "connected", connected: true, tools: ["files.read", "files.search"], registered_config: { command: "/usr/local/bin/mcp-filesystem", args: ["--root", "/repo", "--token", "raw-token-value", "api_key=raw-api-key", "https://user:password@example.test/sse?access_token=raw#fragment"], cwd: "/repo", env: { API_TOKEN: "raw-env-secret", PUBLIC_FLAG: "raw-public-value" } }, permissions: { approved: true } } as Parameters<typeof mcpServerDetailRows>[0];
  const text = JSON.stringify(mcpServerDetailRows(server));
  assert.match(text, /connected/);
  assert.match(text, /stdio/);
  assert.match(text, /mcp-filesystem/);
  assert.match(text, /\[redacted\]/);
  assert.match(text, /API_TOKEN/);
  assert.match(text, /PUBLIC_FLAG/);
  assert.match(text, /files\.read/);
  for (const secret of ["raw-token-value", "raw-api-key", "raw-env-secret", "raw-public-value", "user:password", "access_token", "#fragment"]) {
    assert.equal(text.includes(secret), false, `unexpected MCP detail leak: ${secret}`);
  }
});

test("MCP argument redaction binds secret flags to their following values", () => {
  assert.deepEqual(redactMcpArguments(["--token", "secret-after-flag", "password=inline-secret", "https://user:pass@example.test/api?token=query#fragment", "--safe"]), ["--token", "[redacted]", "password=[redacted]", "https://example.test/api", "--safe"]);
});

test("MCP lifecycle approval retries require the exact request and workspace", () => {
  const pending: PendingMcpLifecycle = { requestId: "approval-lifecycle-1", action: "remove", serverId: "filesystem", workspaceId: "ws-main" };
  const approved = { request_id: "approval-lifecycle-1", status: "approved", approved: true, token: "single-use-token" };
  assert.equal(approvedMcpLifecycleRetryReason(pending, "ws-main", approved), null);
  assert.match(approvedMcpLifecycleRetryReason(null, "ws-main", approved) ?? "", /stale|settled/);
  assert.match(approvedMcpLifecycleRetryReason(pending, "ws-other", approved) ?? "", /workspace changed/);
  assert.equal(approvedMcpLifecycleRetryReason(pending, "ws-main", { ...approved, approved: false, token: undefined, reason: "denied for fixture" }), "denied for fixture");
  assert.equal(isMcpLifecycleApprovalRequest({ request_id: "x", operation: "tool.mcp_disconnect", risk_level: "medium", status: "pending" }), true);
  assert.equal(isMcpLifecycleApprovalRequest({ request_id: "x", operation: "tool.mcp_remove", risk_level: "high", status: "pending" }), true);
});

test("Coding Cockpit exposes reviewed MCP lifecycle controls", () => {
  const source = readFileSync(resolve(import.meta.dirname, "CodingCockpit.tsx"), "utf8");
  const resources = readFileSync(resolve(import.meta.dirname, "../../features/coding/resources/codingResources.ts"), "utf8");
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
