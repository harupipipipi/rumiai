import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  authorityApprovalConfig,
  authorityApprovalRiskTone,
  authorityApprovalRuntimeContent,
  authorityApprovalSettledLabel,
  authorityApprovalShouldRetryWithFreshContext,
  authorityApprovalTitle,
  authorityRelatedPermissions,
  authorityRequestSettledStatus,
  pendingAuthorityApproval,
  resolvePendingAuthorityApproval,
} from "./authorityApproval";
import {
  browserAuthorityApprovalPath,
  browserApprovalTokenizedPath,
  readBrowserApprovalTokenFromLocation,
} from "./authorityApprovalBrowserToken";

const SRC_ROOT = resolve(import.meta.dirname, "..");
const RISKY_AUTHORITY_FOLLOWUP_PHRASES = [
  "Thank you for granting",
  "approved provider",
  "approved model",
  "I can now use",
  "使用を許可しました",
];

function authorityApprovalWindowSource(): string {
  return readFileSync(resolve(SRC_ROOT, "components", "AuthorityApprovalWindow.tsx"), "utf8");
}

function assertNoRiskyAuthorityFollowupPhrases(text: string): void {
  for (const phrase of RISKY_AUTHORITY_FOLLOWUP_PHRASES) {
    assert.equal(text.includes(phrase), false, `unexpected risky phrase: ${phrase}`);
  }
}

function runtimeMetadataJson(content: string): Record<string, unknown> {
  const marker = "Resume metadata JSON:\n";
  const start = content.indexOf(marker);
  assert.notEqual(start, -1);
  return JSON.parse(content.slice(start + marker.length));
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

test("authority approval runtime content silently resumes without risky chatter", () => {
  const content = authorityApprovalRuntimeContent({
    requestId: "approval-1",
    principalId: "local-user",
    permissionId: "model.invoke",
    resource: {
      provider_id: "opencode-go",
      model_id: "deepseek-v4-pro",
      endpoint_url: "https://opencode.ai/zen/go/v1/chat/completions",
    },
  }, "token-1");

  assertNoRiskyAuthorityFollowupPhrases(content);
  assert.match(content, /Silent internal resume/);
  assert.match(content, /Continue the interrupted\/original user request/i);
  assert.match(content, /never mention approval, authority, API keys, providers, model access/i);
  assert.match(content, /do not thank the user for permission/i);
  assert.match(content, /Request id: approval-1/);
  assert.match(content, /Permission id: model\.invoke/);

  const metadata = runtimeMetadataJson(content);
  assert.deepEqual(metadata, {
    request_id: "approval-1",
    permission_id: "model.invoke",
    resource: {
      provider_id: "opencode-go",
      model_id: "deepseek-v4-pro",
      endpoint_url: "https://opencode.ai/zen/go/v1/chat/completions",
    },
    approval_token: "token-1",
  });
});

test("host authority runtime content keeps the same no-mention no-thanks guardrail", () => {
  const content = authorityApprovalRuntimeContent({
    requestId: "host-approval-1",
    principalId: "local-user",
    permissionId: "host.process.open_url",
    resource: {
      operation: "host.process.open_url.preview",
      caller_pack_id: "defaultspack",
    },
  }, "host-token-1");

  assertNoRiskyAuthorityFollowupPhrases(content);
  assert.match(content, /Retry the same host operation once/);
  assert.match(content, /never mention approval, authority, API keys, providers, model access/i);
  assert.match(content, /do not thank the user for permission/i);

  const metadata = runtimeMetadataJson(content);
  assert.equal(metadata.request_id, "host-approval-1");
  assert.equal(metadata.permission_id, "host.process.open_url");
  assert.equal(metadata.approval_token, "host-token-1");
  assert.deepEqual(metadata.resource, {
    operation: "host.process.open_url.preview",
    caller_pack_id: "defaultspack",
  });
});

test("authority approval window sends only the terse hidden resume marker", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /sendAuthorityResume\([\s\S]*"Internal authority resume\."/);
  assertNoRiskyAuthorityFollowupPhrases(source);
  assert.match(source, /runtime_content: authorityApprovalRuntimeContent\(settledApproval, decision\.token\)/);
  assert.match(source, /related_permissions: authorityRelatedPermissions\(approval\)/);
});

test("authority approval window always surfaces host execution summary rows", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /authorityHostExecutionSummary\(metadata\.host_execution_summary\)/);
  assert.match(source, /label: "操作内容"[\s\S]*metadata\.access_summary/);
  assert.match(source, /label: "実行ファイル"[\s\S]*hostExecutionSummary\.executable/);
  assert.match(source, /label: "引数"[\s\S]*hostExecutionSummary\.argument_count/);
  assert.match(source, /label: "作業フォルダ"[\s\S]*hostExecutionSummary\.cwd/);
  assert.match(source, /label: "対象path"[\s\S]*hostExecutionSummary\.target_paths/);
  assert.match(source, /label: "対象URL"[\s\S]*hostExecutionSummary\.target_urls/);
});

test("pending authority approval detects persisted assistant metadata", () => {
  const approval = pendingAuthorityApproval([
    {
      id: "u1",
      role: "user",
      content: [{ type: "text", text: "hello" }],
      rawText: "hello",
    },
    {
      id: "a1",
      role: "agent",
      content: [{ type: "text", text: "モデル/API の使用許可が必要です。承認後に続行します。" }],
      rawText: "モデル/API の使用許可が必要です。承認後に続行します。",
      metadata: {
        pendingAuthorityApproval: {
          request_id: "auth-metadata-1",
          principal_id: "local-user",
          permission_id: "model.invoke",
          resource: { provider_id: "opencode-go" },
        },
      },
    },
  ]);

  assert.equal(approval?.requestId, "auth-metadata-1");
  assert.equal(approval?.permissionId, "model.invoke");
  assert.deepEqual(approval?.resource, { provider_id: "opencode-go" });
});

test("pending authority resolver replaces stale conversation metadata with matching live request", () => {
  const resolved = resolvePendingAuthorityApproval(
    {
      requestId: "auth_old_approved",
      principalId: "profile:default-profile__graph:defaultspack.startup",
      permissionId: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        api_id: "legacy",
        model_id: "deepseek-v4-flash",
        model_ref: "opencode-go/deepseek-v4-flash",
        pack_id: "defaultspack",
      },
    },
    [{
      request_id: "auth_live_pending",
      status: "pending",
      principal_id: "defaultspack",
      permission_id: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        api_id: "legacy",
        model_id: "deepseek-v4-flash",
        model_ref: "opencode-go/deepseek-v4-flash",
        pack_id: "defaultspack",
      },
      risk_level: "medium",
      reason: "use provider",
    }],
  );

  assert.equal(resolved?.requestId, "auth_live_pending");
  assert.equal(resolved?.principalId, "defaultspack");
});

test("scoped pending authority resolver does not borrow a grant match from another conversation", () => {
  const resolved = resolvePendingAuthorityApproval(
    {
      requestId: "auth_stale_conv_a",
      conversationId: "conversation-a",
      principalId: "profile:default-profile__graph:defaultspack.startup",
      permissionId: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        api_id: "legacy",
        model_id: "deepseek-v4-flash",
        model_ref: "opencode-go/deepseek-v4-flash",
        pack_id: "defaultspack",
      },
    },
    [{
      request_id: "auth_pending_conv_b",
      status: "pending",
      conversation_id: "conversation-b",
      principal_id: "profile:default-profile__graph:defaultspack.startup",
      permission_id: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        api_id: "legacy",
        model_id: "deepseek-v4-flash",
        model_ref: "opencode-go/deepseek-v4-flash",
        pack_id: "defaultspack",
      },
    }],
    {
      conversationId: "conversation-a",
      requireConversationMatch: true,
      requirePrincipalMatch: true,
    },
  );

  assert.equal(resolved, null);
});

test("scoped pending authority resolver keeps grant fallback within the same conversation and principal", () => {
  const resolved = resolvePendingAuthorityApproval(
    {
      requestId: "auth_stale_conv_a",
      conversationId: "conversation-a",
      principalId: "conversation:conversation-a",
      permissionId: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        model_id: "deepseek-v4-flash",
      },
    },
    [{
      request_id: "auth_pending_conv_a",
      status: "pending",
      conversation_id: "conversation-a",
      principal_id: "conversation:conversation-a",
      permission_id: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        model_id: "deepseek-v4-flash",
      },
    }],
    {
      conversationId: "conversation-a",
      requireConversationMatch: true,
      requirePrincipalMatch: true,
    },
  );

  assert.equal(resolved?.requestId, "auth_pending_conv_a");
  assert.equal(resolved?.conversationId, "conversation-a");
  assert.equal(resolved?.principalId, "conversation:conversation-a");
});

test("scoped pending authority resolver still accepts an exact request id match", () => {
  const resolved = resolvePendingAuthorityApproval(
    {
      requestId: "auth_exact_pending",
      conversationId: "conversation-a",
      principalId: "conversation:conversation-a",
      permissionId: "model.invoke",
      resource: { provider_id: "opencode-go" },
    },
    [{
      request_id: "auth_exact_pending",
      status: "pending",
      conversation_id: "conversation-b",
      principal_id: "conversation:conversation-b",
      permission_id: "model.invoke",
      resource: { provider_id: "opencode-go" },
    }],
    {
      conversationId: "conversation-a",
      requireConversationMatch: true,
      requirePrincipalMatch: true,
    },
  );

  assert.equal(resolved?.requestId, "auth_exact_pending");
  assert.equal(resolved?.conversationId, "conversation-b");
});

test("pending authority resolver does not expose stale metadata when no live request matches", () => {
  const resolved = resolvePendingAuthorityApproval(
    {
      requestId: "auth_old_approved",
      principalId: "profile:default-profile__graph:defaultspack.startup",
      permissionId: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        model_id: "deepseek-v4-flash",
      },
    },
    [{
      request_id: "auth_other_pending",
      status: "pending",
      principal_id: "defaultspack",
      permission_id: "model.invoke",
      resource: {
        provider_id: "opencode-go",
        model_id: "qwen3.7-plus",
      },
    }],
  );

  assert.equal(resolved, null);
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

test("authority related permissions helper can identify provider-scoped network approval", () => {
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

test("authority approval browser token helper accepts URL aliases and builds tokenized path", () => {
  assert.equal(readBrowserApprovalTokenFromLocation("?browser_approval_token=tok-1"), "tok-1");
  assert.equal(readBrowserApprovalTokenFromLocation("?approval_browser_token=tok-2"), "tok-2");
  assert.equal(readBrowserApprovalTokenFromLocation("?browserApprovalToken=tok-3"), "tok-3");
  assert.equal(
    browserAuthorityApprovalPath("auth 1", "tok/en"),
    "/approval?request_id=auth+1&browser_approval_token=tok%2Fen",
  );
  assert.equal(
    browserApprovalTokenizedPath("/finger-recording?authority_approved=1", "tok/en"),
    "/finger-recording?authority_approved=1&browser_approval_token=tok%2Fen",
  );
  assert.equal(
    browserApprovalTokenizedPath("/finger-recording?browser_approval_token=existing", "tok/en"),
    "/finger-recording?browser_approval_token=existing",
  );
});

test("authority approval window bundles related provider permissions", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /related_permissions:\s*authorityRelatedPermissions\(approval\)/);
  assert.match(source, /approveAuthorityApproval\(request\.request_id,[\s\S]*scope: selectedScope,[\s\S]*config,[\s\S]*ui_operator: context\.ui_operator/);
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
  assert.match(source, /const approvalContextAvailable = nativeApprovalAvailable \|\| browserApprovalAvailable/);
  assert.match(source, /const showApprovalControls = Boolean\(request && request\.status === "pending" && approvalContextAvailable && !displayedSettledStatus/);
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

  assert.match(source, /const submitApproveOnce = async[\s\S]*getApprovalContext\(request\.request_id\)/);
  assert.match(source, /if \(nativeApprovalAvailableRef\.current\)[\s\S]*getAuthorityApprovalContext\(targetRequestId\)/);
  assert.match(source, /if \(!authorityApprovalShouldRetryWithFreshContext\(postError\)\) throw postError;\s*try \{\s*const retriedDecision = await submitApproveOnce\(\);/);
  assert.equal((source.match(/await submitApproveOnce\(\)/g) ?? []).length, 2);
});

test("authority approval browser route is read-only without URL token but can fetch browser ui_operator with token", () => {
  const source = authorityApprovalWindowSource();
  const tokenSource = readFileSync(resolve(SRC_ROOT, "lib", "authorityApprovalBrowserToken.ts"), "utf8");
  const apiSource = readFileSync(resolve(SRC_ROOT, "lib", "api.ts"), "utf8");
  const resourceSource = readFileSync(resolve(SRC_ROOT, "features", "chat", "resources", "authorityApprovalResources.ts"), "utf8");

  assert.match(source, /function hasNativeAuthorityApprovalContext\(\)/);
  assert.match(source, /readBrowserApprovalTokenFromLocation/);
  assert.doesNotMatch(source, /readBrowserApprovalTokenFromStorage/);
  assert.match(tokenSource, /BROWSER_APPROVAL_TOKEN_STORAGE_KEY/);
  assert.match(tokenSource, /"browser_approval_token"/);
  assert.match(tokenSource, /"approval_browser_token"/);
  assert.match(tokenSource, /"browserApprovalToken"/);
  assert.match(tokenSource, /"sessionStorage"/);
  assert.match(tokenSource, /"localStorage"/);
  assert.match(source, /const browserApprovalAvailable = Boolean\(!nativeApprovalAvailable && browserApprovalToken\)/);
  assert.match(source, /request\.status === "pending" && approvalContextAvailable && !displayedSettledStatus/);
  assert.match(source, /getBrowserAuthorityApprovalContext\(targetRequestId, token\)/);
  assert.match(source, /承認操作は Rumi Viewer の専用ウィンドウでのみ実行できます。/);
  assert.match(source, /ブラウザでは承認テストトークンがないため読み取り専用です。/);
  assert.match(source, /displayedSettledStatus && \(/);
  assert.match(source, /このリクエストは処理済みです。追加の操作は不要です。/);
  assert.match(apiSource, /browserAuthorityUiOperator\(requestId: string, browserApprovalToken: string\)/);
  assert.match(apiSource, /withQuery\("\/api\/authority\/browser-ui-operator", \{\s*browser_approval_token: browserApprovalToken,\s*\}\)/);
  assert.match(apiSource, /\/api\/authority\/browser-ui-operator/);
  assert.match(apiSource, /"X-Rumi-Approval-Browser-Token": browserApprovalToken/);
  assert.match(apiSource, /request_id: requestId,\s*browser_approval_token: browserApprovalToken/s);
  assert.match(resourceSource, /getBrowserAuthorityApprovalContext\(requestId: string, browserApprovalToken: string\)/);
});

test("authority approval browser QA token is preserved across child window URLs", () => {
  const appSource = readFileSync(resolve(SRC_ROOT, "App.tsx"), "utf8");
  const source = authorityApprovalWindowSource();

  assert.match(appSource, /browserApprovalTokenizedPath/);
  assert.match(appSource, /defaultspackUrlWithLocalAuth\(browserApprovalTokenizedPath\("\/finger-recording"\)\)/);
  assert.match(source, /browserApprovalTokenizedPath/);
  assert.match(source, /defaultspackUrlWithStoredLocalAuth\(browserApprovalTokenizedPath\("\/finger-recording\?authority_approved=1"\)\)/);
});

test("authority approval window explains disabled browser QA approval", () => {
  const source = authorityApprovalWindowSource();

  assert.match(source, /function authorityApprovalErrorMessage/);
  assert.match(source, /AUTHORITY_BROWSER_TEST_DISABLED/);
  assert.match(source, /AUTHORITY_UI_OPERATOR_UNAVAILABLE/);
  assert.match(source, /このDefaultspackはブラウザ承認QAが無効な状態で起動しています。/);
  assert.match(source, /承認操作に必要なRumi Viewerの署名secretがありません。/);
  assert.match(source, /setError\(authorityApprovalErrorMessage\(approvalError\)\)/);
  assert.match(source, /setError\(authorityApprovalErrorMessage\(rejectionError\)\)/);
});
