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

test("generic authority approval settlements schedule window close", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.match(source, /function scheduleAuthorityApprovalWindowClose\(\)/);
  assert.match(source, /if \(await closeCurrentWindow\(\)\) return/);
  assert.match(source, /window\.close\(\)/);
  assert.match(source, /const settleAuthorityRequest = useCallback[\s\S]*scheduleAuthorityApprovalWindowClose\(\);/);
  assert.match(source, /await finalizeApprovedDecision\(request, decision\)/);
  assert.match(source, /await finalizeDeniedRequest\(request\)/);
});

test("generic authority approval load settles already completed backend requests", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.match(source, /const singleSettledStatus = authorityRequestSettledStatus\(single\.status\)[\s\S]*settleAuthorityRequest\(single, singleSettledStatus\)/);
  assert.match(source, /const displayedSettledStatus = decisionSettledStatus \?\? authorityRequestSettledStatus\(request\?\.status\)/);
  assert.match(source, /authorityApprovalSettledLabel\(displayedSettledStatus\)/);
  assert.match(source, /\{showApprovalControls \? \(/);
});

test("generic authority approval success refetches before settling", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.match(source, /const finalizeApprovedDecision = useCallback[\s\S]*readAuthoritySettlementOrNull\(settledRequest\.request_id\)[\s\S]*settleAuthorityRequest\(finalRequest, finalStatus/);
  assert.match(source, /const finalizeDeniedRequest = useCallback[\s\S]*readAuthoritySettlementOrNull\(settledRequest\.request_id\)[\s\S]*settleAuthorityRequest\(finalRequest, finalStatus\)/);
});

test("generic authority approval stale post failure refetches and settles before error", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.equal((source.match(/if \(await settleFromServer\(request\.request_id\)\) return;/g) ?? []).length, 4);
});

test("generic authority approval retries stale native context once without browser bypass", () => {
  const source = readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");

  assert.equal((source.match(/authorityApprovalShouldRetryWithFreshContext\(postError\)/g) ?? []).length, 2);
  assert.match(source, /const submitApproveOnce = async[\s\S]*getAuthorityApprovalContext\(request\.request_id\)/);
  assert.match(source, /const retriedDecision = await submitApproveOnce\(\)/);
  assert.match(source, /const submitRejectOnce = async[\s\S]*getAuthorityApprovalContext\(request\.request_id\)/);
  assert.doesNotMatch(source, /window\.localStorage/);
});
