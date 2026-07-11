import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ApprovalQueue } from "./ApprovalQueue";
import { CodingCockpit } from "./CodingCockpit";
import { DiffPanel } from "./DiffPanel";
import { TerminalPanel } from "./TerminalPanel";
import {
  approvedMcpRetryReason,
  mcpApprovalReviewRows,
  sameMcpDraft,
  type McpConnectionDraft,
} from "./mcpApproval";

test("approval queue renders cockpit approval decisions", () => {
  const html = renderToStaticMarkup(
    createElement(ApprovalQueue, {
      initialApprovals: [
        {
          request_id: "apr_1",
          operation: "terminal.exec",
          risk_level: "high",
          status: "pending",
          display_summary: "terminal.exec: git push origin main",
        },
      ],
    }),
  );

  assert.match(html, /terminal\.exec/);
  assert.match(html, /Approve/);
  assert.match(html, /Deny/);
});

test("approval queue separates expired pending approvals from active approvals", () => {
  const html = renderToStaticMarkup(
    createElement(ApprovalQueue, {
      initialApprovals: [
        {
          request_id: "apr_expired",
          operation: "terminal.exec",
          risk_level: "medium",
          status: "pending",
          display_summary: "terminal.exec: old command",
          expires_at: 1,
        },
      ],
    }),
  );

  assert.match(html, /Active pending approvals/);
  assert.match(html, />0<\/span>/);
  assert.match(html, /No active approvals/);
  assert.match(html, /Recent approval history/);
  assert.match(html, /expired/);
  assert.doesNotMatch(html, /Approve/);
  assert.doesNotMatch(html, /Deny/);
});

test("MCP approval review renders the complete normalized redacted contract", () => {
  const approval = {
    request_id: "apr_mcp_1",
    operation: "tool.mcp_connect",
    risk_level: "high",
    status: "pending",
    display_summary: "Connect reviewed MCP server",
    details: {
      config: { env: { FAKE_SECRET: "must-not-render" } },
      mcp_review: {
        executable: "/usr/bin/fake-mcp",
        transport: "stdio",
        args: ["--safe-fixture"],
        cwd: "/fake/workspace",
        redacted_env: { FAKE_SECRET: "[redacted]" },
        server_source: "shared_registry",
        capabilities: ["tools"],
        tools: ["fake.read"],
        network: "disabled",
        filesystem: "workspace-only",
        persistence: "process lifetime",
        consequences: ["Starts a local fake fixture process"],
      },
    },
  };
  const html = renderToStaticMarkup(createElement(ApprovalQueue, { initialApprovals: [approval] }));
  const rows = mcpApprovalReviewRows(approval);

  for (const label of [
    "Executable", "Transport", "Arguments", "Working directory", "Environment (redacted)",
    "Server source", "Capabilities", "Tools", "Network", "Filesystem", "Persistence", "Consequences",
  ]) {
    assert.ok(rows.some((row) => row.label === label), `${label} should be present`);
    assert.match(html, new RegExp(label.replace(/[()]/g, "\\$&")));
  }
  assert.match(html, /\[redacted\]/);
  assert.doesNotMatch(html, /must-not-render/);
});

test("MCP approved retry is single-attempt and rejects config or workspace mutation", () => {
  const draft: McpConnectionDraft = {
    serverId: "fixture-mcp",
    command: "/usr/bin/fake-mcp",
    args: ["--fixture"],
    workspaceId: "ws-a",
  };
  const pending = { requestId: "apr_mcp_1", draft };
  const approved = {
    request_id: "apr_mcp_1",
    status: "approved",
    approved: true,
    token: "fake-single-use-token",
  };

  assert.equal(approvedMcpRetryReason(pending, draft, approved), null);
  assert.match(approvedMcpRetryReason(null, draft, approved) ?? "", /stale|settled/);
  assert.match(approvedMcpRetryReason(pending, { ...draft, command: "/usr/bin/changed" }, approved) ?? "", /changed/);
  assert.match(approvedMcpRetryReason(pending, { ...draft, workspaceId: "ws-b" }, approved) ?? "", /changed/);
  assert.equal(sameMcpDraft(draft, { ...draft }), true);
  assert.equal(sameMcpDraft(draft, { ...draft, args: ["--mutated"] }), false);
});

test("MCP retry reports denial expiry and already-settled decisions as recoverable", () => {
  const draft: McpConnectionDraft = {
    serverId: "fixture-mcp",
    command: "/usr/bin/fake-mcp",
    args: [],
    workspaceId: "ws-a",
  };
  const pending = { requestId: "apr_mcp_1", draft };
  for (const status of ["denied", "expired", "consumed", "obsolete"]) {
    const reason = approvedMcpRetryReason(pending, draft, {
      request_id: "apr_mcp_1",
      status,
      approved: false,
      reason: `fixture ${status}`,
    });
    assert.equal(reason, `fixture ${status}`);
  }
});

test("CodingCockpit never approves an MCP request from the requester path", () => {
  const source = readFileSync(new URL("./CodingCockpit.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /approveCodingApproval/);
  assert.match(source, /result\.approval_required/);
  assert.match(source, /rememberPendingMcp/);
});

test("diff panel renders status and diff content", () => {
  const html = renderToStaticMarkup(
    createElement(DiffPanel, {
      initialStatus: { branch: "main", clean: false, modified: ["src/App.tsx"] },
      initialDiff: { diff: "-old\n+new", files_changed: 1, files: ["src/App.tsx"] },
    }),
  );

  assert.match(html, /main/);
  assert.match(html, /src\/App\.tsx/);
  assert.match(html, /-old/);
  assert.match(html, /\+new/);
});

test("terminal panel renders classification and risk reasons", () => {
  const html = renderToStaticMarkup(
    createElement(TerminalPanel, {
      initialLogs: [
        {
          id: "log-1",
          command: "git push origin main",
          approval_required: true,
          classification: "high",
          risk_reasons: ["network"],
          exit_code: null,
          stdout: "",
          stderr: "",
        },
      ],
    }),
  );

  assert.match(html, /git push origin main/);
  assert.match(html, /approval/);
  assert.match(html, /network/);
});

test("coding cockpit renders workspace and sidecar sections", () => {
  const html = renderToStaticMarkup(
    createElement(CodingCockpit, {
      workspaces: [{ workspace_id: "ws-main", label: "Main Repo", root_path: "/repo", trusted: true }],
      selectedWorkspaceId: "ws-main",
    }),
  );

  assert.match(html, /Coding Cockpit/);
  assert.match(html, /Main Repo/);
  assert.match(html, /Approvals/);
  assert.match(html, /Checkpoints/);
  assert.match(html, /Terminal/);
  assert.match(html, /Browser/);
  assert.match(html, /MCP/);
  assert.match(html, /Agents/);
});
