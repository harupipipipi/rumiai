import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ApprovalQueue } from "./ApprovalQueue";
import { CheckpointPanel } from "./CheckpointPanel";
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
  assert.match(html, /許可/);
  assert.match(html, /拒否/);
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
  assert.doesNotMatch(html, />許可</);
  assert.doesNotMatch(html, />拒否</);
});

test("diff panel renders status, content, and an operable refresh control", () => {
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
  assert.match(html, /aria-label="Refresh diff"/);
});

test("checkpoint panel renders refresh and restore-review controls for supplied snapshots", () => {
  const html = renderToStaticMarkup(
    createElement(CheckpointPanel, {
      workspaceId: "ws-main",
      initialCheckpoints: [
        {
          snapshot_id: "snapshot-1",
          path: "/repo/.rumi/checkpoints/snapshot-1",
        },
      ],
      initialDiff: { diff: "-before\n+after", files_changed: 1, files: ["src/App.tsx"] },
    }),
  );

  assert.match(html, /snapshot-1/);
  assert.match(html, /Refresh checkpoints/);
  assert.match(html, /Review restore snapshot-1/);
  assert.match(html, /Restore diff/);
  assert.match(html, /-before/);
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

test("MCP requester never approves its own request", () => {
  const source = readFileSync(resolve(import.meta.dirname, "CodingCockpit.tsx"), "utf8");
  assert.doesNotMatch(source, /codingResources\.approveCodingApproval/);
  assert.match(source, /separate Approvals queue/);
  assert.match(source, /requesting form cannot approve its own request/);
});
