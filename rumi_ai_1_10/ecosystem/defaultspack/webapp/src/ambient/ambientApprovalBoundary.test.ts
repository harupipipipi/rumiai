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

test("ambient mini authority browser fallback is debug QA only and opens tokenized approval URLs", () => {
  const source = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");
  const helperSource = readFileSync(resolve(SRC_ROOT, "lib", "authorityApprovalBrowserToken.ts"), "utf8");

  assert.match(source, /const browserApprovalQaEnabled = standalone && debugMode/);
  assert.match(source, /browserApprovalQaEnabled && miniAuthorityApproval && !hasNativeAuthorityApprovalWindow\(\) && browserApprovalToken\.trim\(\)/);
  assert.match(source, /const nextBrowserApprovalToken = browserApprovalQaEnabled \? readBrowserApprovalToken\(\) : ""/);
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

test("ambient browser approval QA remains route-scoped without visible send controls", () => {
  const appSource = readFileSync(resolve(SRC_ROOT, "App.tsx"), "utf8");
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(appSource, /pathname === "\/ambient-debug"/);
  assert.match(appSource, /pathname === "\/ambient-debug" \|\| pathname === "\/finger-recording"/);
  assert.match(appSource, /const explicitDebugConversationId = fingerDebugMode \? chatIdFromLocation\(\) : null/);
  assert.match(appSource, /<AmbientTriggerPanel variant="window" debugMode=\{fingerDebugMode\} conversationId=\{explicitDebugConversationId\}/);
  assert.doesNotMatch(appSource, /pathname === "\/viewer"/);
  assert.match(panelSource, /const explicitDebugConversationId = debugMode \? cleanString\(conversationId\) : null/);
  assert.match(panelSource, /explicitDebugConversationId \?\? ambientLinkedConversationId\(status, conversationId\)/);
  assert.doesNotMatch(panelSource, /Browser QA/);
  assert.doesNotMatch(panelSource, /OK送信/);
  assert.doesNotMatch(panelSource, /data-testid="ambient-debug-panel"/);
  assert.doesNotMatch(panelSource, /data-testid="ambient-debug-transcript"/);
  assert.doesNotMatch(panelSource, /data-testid="ambient-debug-simulate-ok"/);
  assert.doesNotMatch(panelSource, /data-testid="ambient-debug-status"/);
});

test("ambient mini window removed browser QA simulated OK payload", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");
  const miniChatSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientMiniChat.tsx"), "utf8");

  assert.doesNotMatch(panelSource, /Local Browser QA only/);
  assert.doesNotMatch(panelSource, /debug_qa/);
  assert.doesNotMatch(panelSource, /debug-ok-mark\.webm/);
  assert.doesNotMatch(panelSource, /ambient\.debug_qa/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat"/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat-output"/);
  assert.match(miniChatSource, /data-testid="ambient-mini-chat-input"/);
});

test("ambient mini chat open button opens the linked chat in the Defaultspack main window", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");
  const miniChatSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientMiniChat.tsx"), "utf8");
  const desktopSource = readFileSync(resolve(SRC_ROOT, "lib", "desktopApproval.ts"), "utf8");

  assert.match(miniChatSource, /data-testid="ambient-mini-chat-open"/);
  assert.match(panelSource, /function openMiniChatConversation\(\)/);
  assert.match(panelSource, /openDefaultspackMainWindow\(path\)/);
  assert.match(panelSource, /window\.open\(defaultspackUrlWithLocalAuth\(path\), "rumi-defaultspack"/);
  assert.doesNotMatch(panelSource, /window\.location\.assign/);
  assert.match(desktopSource, /open_defaultspack_main_window/);
  assert.match(panelSource, /onOpenChat=\{openMiniChatConversation\}/);
});

test("ambient event submit forwards browser QA token header", () => {
  const clientSource = readFileSync(resolve(SRC_ROOT, "ambient", "ambientTriggerClient.ts"), "utf8");

  assert.match(clientSource, /readBrowserApprovalToken/);
  assert.match(clientSource, /function browserApprovalHeaders\(\)/);
  assert.match(clientSource, /"X-Rumi-Approval-Browser-Token": token/);
  assert.match(clientSource, /startMonitor\(options\?: \{ voice_wake\?: boolean; gesture_pinch\?: boolean \}\)[\s\S]*headers: browserApprovalHeaders\(\)/);
  assert.match(clientSource, /stopMonitor\(\)[\s\S]*headers: browserApprovalHeaders\(\)/);
  assert.match(clientSource, /submitEvent\(payload: AmbientEventPayload\)[\s\S]*headers: browserApprovalHeaders\(\)/);
});

test("ambient action failures expand details so auth errors are visible", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /catch \(error\) \{\s*setExpanded\(true\);\s*setMessage\(error instanceof Error \? error\.message : "操作を完了できませんでした。"\)/);
});

test("real OK-mark recording routes audio through transcription before dispatch", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /setPinchDetectorStatus\("transcribing"\)/);
  assert.match(panelSource, /ambientOperationLabels\.transcribing/);
  const pinchSubmitStart = panelSource.indexOf('source: "camera",\n        trigger: "pinch",\n        mode: "dispatch_audio"');
  assert.notEqual(pinchSubmitStart, -1);
  const pinchSubmitEnd = panelSource.indexOf("      });", pinchSubmitStart);
  assert.notEqual(pinchSubmitEnd, -1);
  const pinchSubmitSource = panelSource.slice(pinchSubmitStart, pinchSubmitEnd);
  assert.doesNotMatch(pinchSubmitSource, /audio_data_url: recording\.dataUrl/);
  assert.match(panelSource, /audio_mime_type: recording\.mimeType/);
  assert.match(panelSource, /audio_name: `ok-mark-recording\.\$\{recording\.extension\}`/);
  assert.match(panelSource, /dataUrl: recording\.dataUrl/);
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

test("ambient mini chat fallback conversation does not override backend routing", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /api\.listConversations\(\{[\s\S]*tag: "ambient"[\s\S]*group_id: "gesture"[\s\S]*limit: 1/);
  assert.doesNotMatch(panelSource, /if \(conversation\?\.id\) setMiniConversationIdOverride\(conversation\.id\)/);
});

test("ambient submission waits for the stored model reply before completing", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /waitForAmbientAssistantResponse/);
  assert.match(panelSource, /setPinchDetectorStatus\("waiting_response"\)/);
  assert.match(panelSource, /outcome\.status === "completed"/);
  assert.match(panelSource, /setPinchDetectorStatus\("completed"\)/);
  assert.match(panelSource, /setLatestSubmittedInput\(null\)/);
});

test("ambient browser-owned monitor does not leave backend enabled without camera capture", () => {
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(panelSource, /const monitorEnabledRef = useRef\(false\)/);
  assert.match(panelSource, /cameraStreamRef\.current\?\.getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/);
  assert.match(panelSource, /if \(monitorEnabledRef\.current\) \{[\s\S]*ambientTriggerClient\.stopMonitor\(\)/);
  assert.match(panelSource, /async function acquireCameraForMonitoring\(\)/);
  assert.match(panelSource, /if \(!monitorEnabled \|\| cameraStream \|\| cameraAcquireInFlightRef\.current\) return/);
  assert.match(panelSource, /await acquireCameraForMonitoring\(\);[\s\S]*待機を再開しました/);
  assert.match(panelSource, /await ambientTriggerClient\.stopMonitor\(\)\.catch\(\(\) => undefined\);[\s\S]*await refresh\(\{ probeOs: true \}\)/);
});

test("Viewer authenticates every dedicated Defaultspack window and rejects unsafe stale listeners", () => {
  const repositoryRoot = resolve(import.meta.dirname, "../../../../../../");
  const viewerSource = readFileSync(resolve(repositoryRoot, "rumi_viewer", "src-tauri", "src", "lib.rs"), "utf8");
  const dockSource = readFileSync(resolve(repositoryRoot, "rumi_viewer", "src-tauri", "src", "dock_registration.rs"), "utf8");

  assert.match(viewerSource, /authenticated_defaultspack_window_url\(config, authority_approval_url/);
  assert.match(viewerSource, /authenticated_defaultspack_window_url\(config, ambient_trigger_url/);
  assert.match(viewerSource, /authenticated_defaultspack_window_url\(config, finger_recording_url/);
  assert.match(viewerSource, /authenticated_defaultspack_window_url\(config, defaults_console_url/);
  assert.match(viewerSource, /authenticated_defaultspack_window_url\(config, host_permissions_url/);
  assert.match(dockSource, /active HMAC store is encrypted; using the Kernel-managed desktop token cache/);
  assert.match(dockSource, /Viewer did not stop it\. Close that process or free port/);
  assert.match(dockSource, /identify_defaultspack_listener\(&listener, metadata\)/);
});

test("ambient model selection persists to the canonical selected conversation", () => {
  const routingSource = readFileSync(resolve(SRC_ROOT, "ambient", "useAmbientRouting.ts"), "utf8");
  const panelSource = readFileSync(resolve(SRC_ROOT, "ambient", "AmbientTriggerPanel.tsx"), "utf8");

  assert.match(routingSource, /async function saveRoutingModel\(model: string\)/);
  assert.match(routingSource, /api\.updateConversation\(targetConversationId, \{ model: normalizedModel \}\)/);
  assert.match(panelSource, /onModelCommit=\{\(model\) => void saveRoutingModel\(model\)\}/);
});
