import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  authorityApprovalConfig,
  authorityApprovalRiskTone,
  authorityApprovalSettledLabel,
  authorityApprovalShouldRetryWithFreshContext,
  authorityApprovalTitle,
  authorityRelatedPermissions,
  authorityRequestSettledStatus,
} from "./authorityApproval";

const SRC_ROOT = resolve(import.meta.dirname, "..");

function authorityApprovalWindowSource(): string {
  return readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");
}

test("authority approval title describes app provider key and endpoint without duplicating provider", () => {
  const title = authorityApprovalTitle({
    permissionId: "model.invoke",
    resource: {
      app_display_name: "defaultspack v2",
      provider_display_name: "OpenCode Go provider",
      model_display_name: "DeepSeek V4 Pro via OpenCode Go",
      credential_label: "OpenCode Go API key",
      endpoint_url: "https://opencode.ai/zen/go/v1/chat/completions",
    },
  });

  assert.equal(
    title,
    "defaultspack v2 / OpenCode Go provider に OpenCode Go API key の使用と https://opencode.ai/zen/go/v1/chat/completions へのアクセスを許可しますか？",
  );
  assert.equal(title.includes("provider provider"), false);
});

test("authority approval config accumulates distinct host action aliases", () => {
  assert.deepEqual(
    authorityApprovalConfig({
      permissionId: "host.process.open_url",
      resource: {
        host_action: "host.process.open_url",
        operation: "host.process.open_url.preview",
      },
    }),
    {
      host_actions: ["host.process.open_url", "host.process.open_url.preview"],
    },
  );
});

test("authority approval config dedupes matching host action aliases", () => {
  assert.deepEqual(
    authorityApprovalConfig({
      permissionId: "host.process.open_url",
      resource: {
        host_action: "host.process.open_url",
        operation: "host.process.open_url",
      },
    }),
    {
      host_actions: ["host.process.open_url"],
    },
  );
});

test("authority related permissions bundle provider-scoped network approval", () => {
  assert.deepEqual(
    authorityRelatedPermissions({
      permissionId: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        api_id: "legacy",
        model_id: "deepseek-v4-pro",
      },
    }),
    ["api_key.use", "network.egress"],
  );
});

test("authority approval risk tones render critical and high as danger", () => {
  assert.match(authorityApprovalRiskTone("critical"), /red-600/);
  assert.match(authorityApprovalRiskTone("critical"), /ring-red/);
  assert.match(authorityApprovalRiskTone("high"), /red-500/);
  assert.doesNotMatch(authorityApprovalRiskTone("critical"), /sky/);
  assert.doesNotMatch(authorityApprovalRiskTone("high"), /sky/);
});

test("authority request settled status recognizes approved and denied requests", () => {
  assert.equal(authorityRequestSettledStatus("approved"), "approved");
  assert.equal(authorityRequestSettledStatus("denied"), "denied");
  assert.equal(authorityRequestSettledStatus("rejected"), "denied");
  assert.equal(authorityRequestSettledStatus("pending"), null);
  assert.equal(authorityApprovalSettledLabel("approved"), "承認済み");
  assert.equal(authorityApprovalSettledLabel("denied"), "拒否済み");
});

test("authority approval context retry only matches stale native ui_operator failures", () => {
  assert.equal(
    authorityApprovalShouldRetryWithFreshContext(new Error("HTTP 403\n詳細: ui_operator expired")),
    true,
  );
  assert.equal(
    authorityApprovalShouldRetryWithFreshContext("HTTP 403\n詳細: ui_operator source is invalid"),
    true,
  );
  assert.equal(
    authorityApprovalShouldRetryWithFreshContext("HTTP 403\n詳細: ui_operator request mismatch"),
    true,
  );
  assert.equal(
    authorityApprovalShouldRetryWithFreshContext("HTTP 409\n詳細: Authority request is approved"),
    false,
  );
  assert.equal(
    authorityApprovalShouldRetryWithFreshContext("Typed confirmation is required for this host operation"),
    false,
  );
});

test("authority approval window settles already-approved or denied requests on load without pending CTAs", () => {
  const source = authorityApprovalWindowSource();

  assert.match(
    source,
    /const singleSettledStatus = authorityRequestSettledStatus\(single\.status\)[\s\S]*settleAuthorityRequest\(single, singleSettledStatus\)/,
  );
  assert.match(source, /const displayedSettledStatus = decisionSettledStatus \?\? authorityRequestSettledStatus\(request\?\.status\)/);
  assert.match(source, /const showApprovalControls = Boolean\(request && request\.status === "pending" && nativeApprovalAvailable && !displayedSettledStatus/);
  assert.match(source, /authorityApprovalSettledLabel\(displayedSettledStatus\)/);
});

test("authority approval window settles and closes immediately after approve or deny post success", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /function scheduleAuthorityApprovalWindowClose\(\)[\s\S]*closeAuthorityApprovalWindow/);
  assert.match(source, /const shouldScheduleClose = options\?\.scheduleClose \?\? nativeApprovalAvailableRef\.current/);
  assert.match(source, /const decision = await submitApproveOnce\(\);\s*settleApprovedDecision\(request, decision\);\s*await finalizeApprovedDecision\(request, decision\);/);
  assert.match(source, /await submitRejectOnce\(\);\s*settleDeniedRequest\(request\);\s*await finalizeDeniedRequest\(request\);/);
});

test("authority approval window treats post failure followed by settled GET as settled", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /const settleFromServer = useCallback/);
  assert.equal((source.match(/if \(await settleFromServer\(request\.request_id\)\) return;/g) ?? []).length, 4);
});

test("authority approval window refreshes stale ui_operator once and retries once", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /const submitApproveOnce = async[\s\S]*getAuthorityApprovalContext\(request\.request_id\)/);
  assert.match(source, /if \(!authorityApprovalShouldRetryWithFreshContext\(postError\)\) throw postError;\s*try \{\s*const retriedDecision = await submitApproveOnce\(\);/);
  assert.equal((source.match(/await submitApproveOnce\(\)/g) ?? []).length, 2);
});

test("authority approval browser route cannot approve pending requests but still shows settled status", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /function hasNativeAuthorityApprovalContext\(\)/);
  assert.match(source, /request\.status === "pending" && nativeApprovalAvailable && !displayedSettledStatus/);
  assert.match(source, /承認操作は Rumi Viewer の専用ウィンドウでのみ実行できます。/);
  assert.match(source, /displayedSettledStatus && \(/);
  assert.match(source, /このリクエストは処理済みです。追加の操作は不要です。/);
});
