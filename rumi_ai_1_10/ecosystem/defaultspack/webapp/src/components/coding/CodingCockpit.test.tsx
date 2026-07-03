import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ApprovalQueue } from "./ApprovalQueue";
import { CodingCockpit } from "./CodingCockpit";
import { DiffPanel } from "./DiffPanel";
import { TerminalPanel } from "./TerminalPanel";

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
  assert.match(html, />Approve</);
  assert.match(html, />Deny</);
  assert.match(html, /aria-label="Deny terminal\.exec approval"/);
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
