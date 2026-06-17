import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

const SRC_ROOT = resolve(import.meta.dirname, "..");

test("ambient panel cannot render or persist its own Rumi approval", () => {
  const source = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.doesNotMatch(source, /RumiPermissionApprovalDialog/);
  assert.doesNotMatch(source, /ambientTriggerClient\.grantPermission/);
  assert.match(source, /openAuthorityApprovalWindow\(AMBIENT_AUTHORITY_REQUEST_ID\)/);
});

test("authority approval route does not render ambient gesture overlay", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.doesNotMatch(source, /<AmbientTriggerPanel/);
  assert.doesNotMatch(source, /onApprovalGesture/);
});

test("ambient authority approval cancel and close settle the opener", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.match(source, /broadcastAmbientApprovalCancelled/);
  assert.match(source, /requestId:\s*AMBIENT_AUTHORITY_REQUEST_ID,\s*status:\s*"denied"/s);
  assert.match(source, /window\.addEventListener\("pagehide",\s*settleOnClose\)/);
  assert.match(source, /window\.addEventListener\("beforeunload",\s*settleOnClose\)/);
  assert.match(source, /onClick=\{\(\) => void closeWindow\(\)\}/);
});

test("generic authority approval approve and reject schedule window close", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.match(source, /function scheduleAuthorityApprovalWindowClose\(\)/);
  assert.match(source, /if \(await closeCurrentWindow\(\)\) return/);
  assert.match(source, /window\.close\(\)/);
  assert.equal((source.match(/scheduleAuthorityApprovalWindowClose\(\);/g) ?? []).length, 2);
});
