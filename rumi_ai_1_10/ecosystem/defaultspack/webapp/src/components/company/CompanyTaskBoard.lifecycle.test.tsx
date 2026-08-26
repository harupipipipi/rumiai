import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { CompanyTask } from "../../lib/api";
import {
  CompanyTaskBoard,
  archiveCompanyTaskUpdate,
  companyTaskStatusOptions,
  restoreCompanyTaskUpdate,
} from "./CompanyTaskBoard";

function task(overrides: Partial<CompanyTask> = {}): CompanyTask {
  return {
    id: "task-1",
    company_id: "company-1",
    title: "Investigate the failing build",
    status: "blocked",
    metadata: { owner: "qa" },
    ...overrides,
  };
}

test("company task archive keeps prior status and restore recovers it", () => {
  const archived = archiveCompanyTaskUpdate(task());
  assert.equal(archived.status, "cancelled");
  assert.deepEqual(archived.metadata, {
    owner: "qa",
    archived_from_status: "blocked",
    archived_from_company_tasks_ui: true,
  });

  const restored = restoreCompanyTaskUpdate({
    ...task(),
    status: "cancelled",
    metadata: archived.metadata,
  });
  assert.equal(restored.status, "blocked");
  assert.deepEqual(restored.metadata, { owner: "qa" });
});

test("company task status options retain unknown persisted states", () => {
  assert.ok(companyTaskStatusOptions("waiting_user_input").includes("waiting_user_input"));
  assert.equal(companyTaskStatusOptions("queued").filter((value) => value === "queued").length, 1);
});

test("company task board exposes status, dispatch, and archive controls by accessible name", () => {
  const html = renderToStaticMarkup(createElement(CompanyTaskBoard, {
    tasks: [task({ status: "queued" })],
    agents: [],
    runs: [],
    onUpdateTask() {},
    onDispatchTask() {},
  }));

  assert.match(html, /aria-label="Status for Investigate the failing build"/);
  assert.match(html, /aria-label="Dispatch Investigate the failing build"/);
  assert.match(html, /aria-label="Archive Investigate the failing build"/);
  assert.match(html, /<option value="cancelled">cancelled<\/option>/);
});
