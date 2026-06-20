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

test("ambient mini authority settlement never sends its own resume", () => {
  const source = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.doesNotMatch(source, /sendAuthorityResume/);
  assert.doesNotMatch(source, /authorityApprovalRuntimeContent/);
  assert.match(source, /waitForMiniAuthorityContinuation/);
  assert.match(source, /承認後の続行がまだ完了していません。もう一度送信してください。/);
});

test("ambient mini authority CTA resolves stale request metadata before opening", () => {
  const source = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(source, /resolveMiniAuthorityApprovalTarget/);
  assert.match(source, /api\.listAuthorityRequests\(\{ status: "pending" \}\)/);
  assert.match(source, /const miniAuthorityApprovalConversationId = miniConversation\?\.id \?\? miniConversationId \?\? null/);
  assert.match(source, /sourceConversationId: miniAuthorityApprovalConversationId/);
  assert.match(source, /resolvePendingAuthorityApproval\(approval, pending\.pending \?\? \[\], \{[\s\S]*conversationId: currentConversationId,[\s\S]*requireConversationMatch: true,[\s\S]*requirePrincipalMatch: true,[\s\S]*\}\)/);
  assert.match(source, /authorityRequestSettledStatus\(currentRequest\.status\)/);
  assert.match(source, /openAuthorityApprovalWindow\(resolvedApproval\.requestId\)/);
  assert.doesNotMatch(source, /openAuthorityApprovalWindow\(approval\.requestId\)/);
});

test("ambient mini authority browser fallback opens only tokenized approval URLs", () => {
  const source = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");
  const helperSource = readFileSync(resolve(SRC_ROOT, "lib", "authorityApprovalBrowserToken.ts"), "utf8");

  assert.match(source, /const nextBrowserApprovalToken = readBrowserApprovalToken\(\)/);
  assert.match(source, /browserAuthorityApprovalPath\(resolvedApproval\.requestId, nextBrowserApprovalToken\)/);
  assert.match(source, /window\.open\(approvalUrl/);
  assert.match(source, /ブラウザで承認するにはテストトークンを保存してください。/);
  assert.doesNotMatch(source, /window\.open\(["'`]\/approval\?request_id/);
  assert.match(helperSource, /params\.set\("browser_approval_token", token\)/);
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
  assert.match(source, /resolvePendingAuthorityApproval\(requestToApproval\(single\), list\.pending \?\? \[\]\)/);
  assert.match(source, /setRequestId\(activePendingApproval\.requestId\)/);
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
  assert.match(source, /const submitApproveOnce = async[\s\S]*getApprovalContext\(request\.request_id\)/);
  assert.match(source, /if \(nativeApprovalAvailableRef\.current\)[\s\S]*getAuthorityApprovalContext\(targetRequestId\)/);
  assert.match(source, /getBrowserAuthorityApprovalContext\(targetRequestId, token\)/);
  assert.match(source, /const retriedDecision = await submitApproveOnce\(\)/);
  assert.match(source, /const submitRejectOnce = async[\s\S]*getApprovalContext\(request\.request_id\)/);
  assert.doesNotMatch(source, /window\.localStorage/);
});

test("ambient debug QA controls are limited to finger recording window routes", () => {
  const appSource = readFileSync(resolve(SRC_ROOT, "App.tsx"), "utf8");
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(appSource, /pathname === "\/ambient-debug"/);
  assert.match(appSource, /pathname === "\/ambient-debug" \|\| pathname === "\/finger-recording"/);
  assert.match(appSource, /const explicitDebugConversationId = fingerDebugMode \? chatIdFromLocation\(\) : null/);
  assert.match(appSource, /<AmbientTriggerPanel variant="window" debugMode=\{fingerDebugMode\} conversationId=\{explicitDebugConversationId\}/);
  assert.doesNotMatch(appSource, /pathname === "\/viewer"/);
  assert.match(panelSource, /const explicitDebugConversationId = debugMode \? cleanString\(conversationId\) : null/);
  assert.match(panelSource, /explicitDebugConversationId \?\? ambientLinkedConversationId\(status, conversationId\)/);
  assert.match(panelSource, /const debugQaVisible = standalone && debugMode/);
  assert.match(panelSource, /data-testid="ambient-debug-panel"/);
  assert.match(panelSource, /data-testid="ambient-debug-transcript"/);
  assert.match(panelSource, /data-testid="ambient-debug-simulate-ok"/);
  assert.match(panelSource, /data-testid="ambient-debug-status"/);
});

test("ambient debug QA simulated OK payload avoids persistent media bytes", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");
  const miniChatSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientMiniChat.tsx"), "utf8");

  assert.match(panelSource, /Local Browser QA only: this simulates OK-mark release without persistent audio\/image bytes/);
  assert.match(panelSource, /mode: "record_audio_start"[\s\S]*debug_qa: true/);
  assert.match(panelSource, /mode: "dispatch_audio"[\s\S]*action_id: "chat\.message"/);
  assert.match(panelSource, /input_text: inputText/);
  assert.match(panelSource, /type: "audio\/webm"[\s\S]*size: 0[\s\S]*ephemeral: true[\s\S]*do_not_persist: true/);
  assert.match(panelSource, /transcript_source: "debug_qa"/);
  assert.doesNotMatch(panelSource, /dataUrl: debug/);
  assert.doesNotMatch(panelSource, /blob: debug/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat"/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat-output"/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat-input"/);
});

test("ambient event submit forwards browser QA token header", () => {
  const clientSource = readFileSync(resolve(SRC_ROOT, "ambient", "ambientTriggerClient.ts"), "utf8");

  assert.match(clientSource, /readBrowserApprovalToken/);
  assert.match(clientSource, /function browserApprovalHeaders\(\)/);
  assert.match(clientSource, /"X-Rumi-Approval-Browser-Token": token/);
  assert.match(clientSource, /submitEvent\(payload: AmbientEventPayload\)[\s\S]*headers: browserApprovalHeaders\(\)/);
});

test("real OK-mark recording routes audio through transcription before dispatch", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /setPinchDetectorStatus\("transcribing"\)/);
  assert.match(panelSource, /ambientOperationLabels\.transcribing/);
  assert.match(panelSource, /audio_data_url: recording\.dataUrl/);
  assert.match(panelSource, /audio_mime_type: recording\.mimeType/);
  assert.match(panelSource, /audio_name: `ok-mark-recording\.\$\{recording\.extension\}`/);
  assert.match(panelSource, /\.\.\.\(transcript \? \{ input_text: transcript \} : \{\}\)/);
  assert.match(panelSource, /setLatestSubmittedInput\(transcript \|\| null\)/);
  assert.doesNotMatch(panelSource, /録音音声を送信しました。文字起こしはまだありません。/);
  assert.doesNotMatch(panelSource, /音声を確認して返答してください。/);
});

test("ambient readout toggle uses stable on off copy", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /aria-pressed=\{readoutEnabled\}/);
  assert.match(panelSource, /readoutEnabled \? "オン" : "オフ"/);
  assert.doesNotMatch(panelSource, /読み上げ: 再生中/);
});

test("ambient mini chat keeps a submitted conversation active over stale routing", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /const miniConversationId = miniConversationIdOverride \|\| linkedAmbientConversationId/);
  assert.match(panelSource, /function ambientSubmittedConversationIdFromResult/);
  assert.match(panelSource, /ambientConversationIdFromNestedResult\(record\?\.pending_approval\)/);
  assert.match(panelSource, /ambientConversationIdFromNestedResult\(record\?\.dispatch\)/);
  assert.match(panelSource, /ambientConversationIdFromNestedResult\(record\?\.dispatch_result\)/);
  assert.match(panelSource, /record\.data, depth \+ 1/);
  assert.match(panelSource, /async function selectMiniChatRoutingConversation[\s\S]*setMiniConversationIdOverride\(null\)[\s\S]*selectConversationForRouting\(chatId\)/);
  assert.match(panelSource, /onSelect=\{\(chatId\) => void selectMiniChatRoutingConversation\(chatId\)\}/);
});
