const DEFAULT_SETTINGS = {
  serverUrl: "http://127.0.0.1:8766",
  pairingToken: "",
  clientLabel: "",
  pollIntervalMinutes: 1
};

const STORAGE_KEY = "rumiBrowserCompanionSettings";
const CLIENT_ID_KEY = "rumiBrowserCompanionClientId";
const LAST_STATUS_KEY = "rumiBrowserCompanionLastStatus";
const ALARM_NAME = "rumi-browser-companion-poll";
const BRIDGE_POLL_PATH = "/api/tools/browser-companion/bridge/poll";
const BRIDGE_RESULT_PATH = "/api/tools/browser-companion/bridge/result";
const SEARCH_HOME_ROUTE_STATE_KEY = "rumiSearchHomeRouteStateByTab";
const SEARCH_HOME_ROUTE_MAX_AGE_MS = 1000 * 60 * 60 * 6;

chrome.runtime.onInstalled.addListener(async () => {
  const settings = await ensureSettings();
  await ensureClientId();
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: normalizePollInterval(settings.pollIntervalMinutes) });
  await chrome.runtime.openOptionsPage();
  void pollBridge("onInstalled");
});

chrome.runtime.onStartup.addListener(async () => {
  const settings = await ensureSettings();
  await ensureClientId();
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: normalizePollInterval(settings.pollIntervalMinutes) });
  void pollBridge("onStartup");
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    void pollBridge("alarm");
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  void clearSearchHomeRouteState(tabId);
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !changes[STORAGE_KEY]) {
    return;
  }
  void ensureSettings().then((settings) => {
    chrome.alarms.create(ALARM_NAME, { periodInMinutes: normalizePollInterval(settings.pollIntervalMinutes) });
    void pollBridge("settingsChanged");
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) {
    return false;
  }

  (async () => {
    switch (message.type) {
      case "rumi:get-status":
        sendResponse(await getStatus());
        return;
      case "rumi:poll-now":
        sendResponse(await pollBridge("manual"));
        return;
      case "rumi:list-tabs":
        sendResponse({ ok: true, tabs: await getTabsSummary() });
        return;
      case "rumi:search-home:set-route-state":
        sendResponse(await setSearchHomeRouteState(sender?.tab?.id, message.payload));
        return;
      case "rumi:search-home:advance-candidate":
        sendResponse(await advanceSearchHomeRouteState(sender?.tab?.id, message.action));
        return;
      default:
        sendResponse({ ok: false, error: `Unknown message type: ${message.type}` });
    }
  })().catch((error) => {
    sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
  });

  return true;
});

async function ensureSettings() {
  const stored = await readLocalSettingsWithSyncMigration();
  const merged = {
    ...DEFAULT_SETTINGS,
    ...(stored || {})
  };
  merged.pollIntervalMinutes = normalizePollInterval(merged.pollIntervalMinutes);
  await chrome.storage.local.set({ [STORAGE_KEY]: merged });
  return merged;
}

async function getSettings() {
  const stored = await readLocalSettingsWithSyncMigration();
  return {
    ...DEFAULT_SETTINGS,
    ...(stored || {}),
    pollIntervalMinutes: normalizePollInterval(
      stored?.pollIntervalMinutes ?? DEFAULT_SETTINGS.pollIntervalMinutes
    )
  };
}

async function readLocalSettingsWithSyncMigration() {
  const localStored = await chrome.storage.local.get(STORAGE_KEY);
  if (localStored[STORAGE_KEY]) {
    return localStored[STORAGE_KEY];
  }
  const syncStored = await chrome.storage.sync.get(STORAGE_KEY);
  if (syncStored[STORAGE_KEY]) {
    await chrome.storage.local.set({ [STORAGE_KEY]: syncStored[STORAGE_KEY] });
    await chrome.storage.sync.remove(STORAGE_KEY);
    return syncStored[STORAGE_KEY];
  }
  return null;
}

async function ensureClientId() {
  const stored = await chrome.storage.local.get(CLIENT_ID_KEY);
  if (stored[CLIENT_ID_KEY]) {
    return stored[CLIENT_ID_KEY];
  }
  const clientId = self.crypto && crypto.randomUUID ? crypto.randomUUID() : `rumi-${Date.now()}`;
  await chrome.storage.local.set({ [CLIENT_ID_KEY]: clientId });
  return clientId;
}

async function getStatus() {
  const stored = await chrome.storage.local.get(LAST_STATUS_KEY);
  return stored[LAST_STATUS_KEY] || { ok: true, state: "idle" };
}

async function setStatus(status) {
  const withTimestamp = {
    ...status,
    updatedAt: new Date().toISOString()
  };
  await chrome.storage.local.set({ [LAST_STATUS_KEY]: withTimestamp });
  return withTimestamp;
}

function normalizePollInterval(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 1) {
    return 1;
  }
  return Math.max(1, Math.round(numeric));
}

async function pollBridge(trigger) {
  const settings = await getSettings();
  const clientId = await ensureClientId();
  if (!settings.serverUrl || !settings.pairingToken) {
    return setStatus({
      ok: false,
      state: "not_configured",
      trigger,
      message: "Set server URL and pairing token in Options."
    });
  }

  const metadata = await buildClientMetadata(settings, clientId);
  const requestBody = {
    event: "poll",
    trigger,
    pairing_token: settings.pairingToken,
    client: metadata
  };

  try {
    const response = await fetch(joinUrl(settings.serverUrl, BRIDGE_POLL_PATH), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${settings.pairingToken}`
      },
      body: JSON.stringify(requestBody)
    });
    const envelope = await safeJson(response);
    const payload = unwrapBridgePayload(envelope);
    if (!response.ok || envelope.status === "error") {
      throw new Error(`Bridge poll failed (${response.status}): ${JSON.stringify(envelope)}`);
    }

    const commands = normalizeCommands(payload);
    const results = [];
    for (const command of commands) {
      results.push(await executeBridgeCommand(command));
    }

    if (results.length > 0) {
      await postCommandResults(settings, metadata, results);
    }

    return setStatus({
      ok: true,
      state: "connected",
      trigger,
      commandCount: commands.length,
      serverUrl: settings.serverUrl
    });
  } catch (error) {
    return setStatus({
      ok: false,
      state: "bridge_error",
      trigger,
      serverUrl: settings.serverUrl,
      message: String(error && error.message ? error.message : error)
    });
  }
}

async function buildClientMetadata(settings, clientId) {
  const browser = detectBrowser();
  const tabs = await getTabsSummary();
  const activeTab = tabs.find((tab) => tab.active) || null;
  return {
    client_id: clientId,
    label: settings.clientLabel || `${browser.name} Companion`,
    extension_version: chrome.runtime.getManifest().version,
    browser_name: browser.name,
    browser_version: browser.version,
    user_agent: navigator.userAgent,
    platform: navigator.platform || "",
    tabs,
    active_tab_id: activeTab ? activeTab.id : null,
    capabilities: {
      multi_browser: true,
      user_session_cookies: true,
      list_tabs: true,
      select_tab: true,
      navigate: true,
      capture_visible_tab: true,
      dom_snapshot: true,
      semantic_dom: true,
      accessible_labels: true,
      element_actions: ["click", "type", "press", "scroll", "extract", "highlight", "clear_highlight"]
    },
    generated_at: new Date().toISOString()
  };
}

function detectBrowser() {
  const ua = navigator.userAgent;
  const brands = navigator.userAgentData?.brands || [];
  const fromBrands =
    brands.find((brand) => /Chrom(e|ium)|Microsoft Edge|Opera|Brave/i.test(brand.brand)) || null;

  if (fromBrands) {
    return {
      name: fromBrands.brand,
      version: navigator.userAgentData?.getHighEntropyValues
        ? "Chromium"
        : fromBrands.version || "unknown"
    };
  }

  const candidates = [
    { name: "Microsoft Edge", regex: /Edg\/([\d.]+)/ },
    { name: "Opera", regex: /OPR\/([\d.]+)/ },
    { name: "Chrome", regex: /Chrome\/([\d.]+)/ },
    { name: "Chromium", regex: /Chromium\/([\d.]+)/ }
  ];

  for (const candidate of candidates) {
    const match = ua.match(candidate.regex);
    if (match) {
      return { name: candidate.name, version: match[1] };
    }
  }

  return { name: "Unknown Chromium Browser", version: "unknown" };
}

async function getTabsSummary() {
  const tabs = await chrome.tabs.query({});
  return tabs.map((tab) => tabSummary(tab));
}

async function postCommandResults(settings, client, results) {
  const response = await fetch(joinUrl(settings.serverUrl, BRIDGE_RESULT_PATH), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${settings.pairingToken}`
    },
    body: JSON.stringify({
      event: "command_results",
      pairing_token: settings.pairingToken,
      client_id: client.client_id,
      client,
      results
    })
  });
  const envelope = await safeJson(response);
  if (!response.ok || envelope.status === "error") {
    throw new Error(`Bridge result post failed (${response.status}): ${JSON.stringify(envelope)}`);
  }
}

async function executeBridgeCommand(command) {
  const startedAt = new Date().toISOString();
  const action = String(command?.action || "");
  try {
    const result = await dispatchCommand(command);
    const semantics = actionResultSemantics(action, result);
    return {
      command_id: command.command_id || null,
      action,
      ok: true,
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      ...semantics,
      result
    };
  } catch (error) {
    const semantics = actionResultSemantics(action);
    return {
      command_id: command.command_id || null,
      action,
      ok: false,
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      ...semantics,
      error: String(error && error.message ? error.message : error)
    };
  }
}

function actionResultSemantics(action, result) {
  if (action === "page.capture") {
    return { requires_foreground: true, can_parallel_user_work: false };
  }
  if (action === "page.snapshot" && result && typeof result === "object" && result.capture) {
    return { requires_foreground: true, can_parallel_user_work: false };
  }
  if (action === "browser.select_tab") {
    return { requires_foreground: true, can_parallel_user_work: false };
  }
  if (
    action === "browser.tabs" ||
    action === "page.navigate" ||
    action === "page.snapshot" ||
    action === "page.click" ||
    action === "page.type" ||
    action === "page.press" ||
    action === "page.scroll" ||
    action === "page.extract" ||
    action === "page.highlight" ||
    action === "page.clear_highlight"
  ) {
    return { requires_foreground: false, can_parallel_user_work: true };
  }
  return {};
}

async function dispatchCommand(command) {
  const action = String(command?.action || "");
  const payload = command && typeof command.payload === "object" ? command.payload : {};
  switch (action) {
    case "browser.tabs":
      return listTabs();
    case "browser.select_tab":
      return selectTab(payload);
    case "page.navigate":
      return navigateTab(payload);
    case "page.capture":
      return captureVisibleTab(payload);
    case "page.snapshot":
      return captureDomSnapshot(payload);
    case "page.click":
    case "page.type":
    case "page.press":
    case "page.scroll":
    case "page.extract":
    case "page.highlight":
    case "page.clear_highlight":
      return sendElementCommand(action, payload);
    default:
      throw new Error(`Unsupported command action: ${action}`);
  }
}

async function listTabs() {
  const tabs = await getTabsSummary();
  const activeTab = tabs.find((tab) => tab.active) || null;
  return {
    tabs,
    active_tab_id: activeTab ? activeTab.id : null,
    requires_foreground: false,
    can_parallel_user_work: true
  };
}

async function selectTab(payload) {
  const tabId = await resolveTabId(payload.tab_id);
  const tab = await chrome.tabs.get(tabId);
  await chrome.tabs.update(tabId, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
  const selected = await chrome.tabs.get(tabId);
  return {
    tab: tabSummary(selected),
    active_tab_id: selected.id,
    requires_foreground: true,
    can_parallel_user_work: false
  };
}

async function navigateTab(payload) {
  const tabId = await resolveTabId(payload.tab_id);
  if (!payload.url) {
    throw new Error("navigate requires url");
  }
  const tab = await chrome.tabs.update(tabId, { url: payload.url });
  return {
    tab: tabSummary(tab),
    active_tab_id: tab.id,
    url: tab.url || payload.url,
    requires_foreground: false,
    can_parallel_user_work: true
  };
}

async function captureVisibleTab(payload) {
  const tabId = await resolveTabId(payload.tab_id);
  const tab = await chrome.tabs.get(tabId);
  await chrome.tabs.update(tabId, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
  const format = payload.format === "jpeg" ? "jpeg" : "png";
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format,
    quality: format === "jpeg" ? Math.max(0, Math.min(100, Number(payload.quality) || 90)) : undefined
  });
  const activeTab = await chrome.tabs.get(tabId);
  return {
    tab: tabSummary(activeTab),
    active_tab_id: activeTab.id,
    data_url: dataUrl,
    image_size: imageSizeFromDataUrl(dataUrl),
    requires_foreground: true,
    can_parallel_user_work: false,
    target_window: {
      window_id: tab.windowId
    }
  };
}

async function captureDomSnapshot(payload) {
  const tabId = await resolveTabId(payload.tab_id);
  const snapshotOptions = {};
  if (payload.include_hidden !== undefined) {
    snapshotOptions.includeHidden = Boolean(payload.include_hidden);
  } else if (payload.includeHidden !== undefined) {
    snapshotOptions.includeHidden = Boolean(payload.includeHidden);
  }
  if (payload.include_html !== undefined) {
    snapshotOptions.includeHtml = Boolean(payload.include_html);
  } else if (payload.includeHtml !== undefined) {
    snapshotOptions.includeHtml = Boolean(payload.includeHtml);
  }
  if (payload.include_attributes !== undefined) {
    snapshotOptions.includeAttributes = Boolean(payload.include_attributes);
  } else if (payload.includeAttributes !== undefined) {
    snapshotOptions.includeAttributes = Boolean(payload.includeAttributes);
  }
  if (Array.isArray(payload.attribute_names)) {
    snapshotOptions.attributeNames = payload.attribute_names;
  } else if (Array.isArray(payload.attributeNames)) {
    snapshotOptions.attributeNames = payload.attributeNames;
  }
  if (payload.include_semantics !== undefined) {
    snapshotOptions.includeSemantics = Boolean(payload.include_semantics);
  } else if (payload.includeSemantics !== undefined) {
    snapshotOptions.includeSemantics = Boolean(payload.includeSemantics);
  }

  const snapshotRequest = {
    type: "rumi:dom-snapshot",
    maxNodes: payload.limit
  };
  if (Object.keys(snapshotOptions).length > 0) {
    snapshotRequest.options = snapshotOptions;
  }

  const snapshot = await sendToTab(tabId, snapshotRequest);
  const tab = await chrome.tabs.get(tabId);
  const result = {
    tab: tabSummary(tab),
    active_tab_id: tab.id,
    snapshot,
    requires_foreground: false,
    can_parallel_user_work: true
  };
  if (payload.include_capture) {
    result.capture = await captureVisibleTab({ ...payload, tab_id: tabId });
    result.requires_foreground = true;
    result.can_parallel_user_work = false;
  }
  return result;
}

async function sendElementCommand(action, payload) {
  const tabId = await resolveTabId(payload.tab_id);
  const result = await sendToTab(tabId, {
    type: "rumi:element-command",
    command: {
      action,
      ...payload
    }
  });
  const tab = await chrome.tabs.get(tabId);
  return {
    ...result,
    tab: tabSummary(tab),
    active_tab_id: tab.id,
    url: tab.url || "",
    requires_foreground: false,
    can_parallel_user_work: true
  };
}

async function sendToTab(tabId, message) {
  const resolvedTabId = Number(tabId);
  if (!Number.isInteger(resolvedTabId)) {
    throw new Error("A numeric tab_id is required");
  }
  try {
    return await chrome.tabs.sendMessage(resolvedTabId, message);
  } catch (error) {
    throw new Error(`Tab message failed for ${resolvedTabId}: ${String(error && error.message ? error.message : error)}`);
  }
}

async function resolveTabId(candidate) {
  const tabId = Number(candidate);
  if (Number.isInteger(tabId)) {
    return tabId;
  }
  const focusedTabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (focusedTabs[0]?.id != null) {
    return focusedTabs[0].id;
  }
  const activeTabs = await chrome.tabs.query({ active: true });
  if (activeTabs[0]?.id != null) {
    return activeTabs[0].id;
  }
  throw new Error("No active tab is available");
}

async function safeJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    return { raw: text, parse_error: String(error && error.message ? error.message : error) };
  }
}

function joinUrl(base, path) {
  return `${String(base || "").replace(/\/+$/, "")}${path}`;
}

function unwrapBridgePayload(value) {
  if (value && typeof value === "object" && value.data && typeof value.data === "object") {
    return value.data;
  }
  return value && typeof value === "object" ? value : {};
}

function normalizeCommands(payload) {
  if (Array.isArray(payload.commands)) {
    return payload.commands.filter((item) => item && typeof item === "object");
  }
  if (payload.command && typeof payload.command === "object") {
    return [payload.command];
  }
  return [];
}

async function loadSearchHomeRouteStates() {
  const stored = await chrome.storage.local.get(SEARCH_HOME_ROUTE_STATE_KEY);
  const value = stored[SEARCH_HOME_ROUTE_STATE_KEY];
  return value && typeof value === "object" ? value : {};
}

async function saveSearchHomeRouteStates(states) {
  await chrome.storage.local.set({ [SEARCH_HOME_ROUTE_STATE_KEY]: states });
}

async function clearSearchHomeRouteState(tabId) {
  if (!Number.isInteger(tabId)) {
    return;
  }
  const states = await loadSearchHomeRouteStates();
  if (!(String(tabId) in states)) {
    return;
  }
  delete states[String(tabId)];
  await saveSearchHomeRouteStates(states);
}

async function setSearchHomeRouteState(tabId, payload) {
  if (!Number.isInteger(tabId)) {
    return { ok: false, error: "Active tab is required for Search Home route state." };
  }
  const normalized = normalizeSearchHomeRouteState(payload);
  if (!normalized) {
    return { ok: false, error: "Invalid Search Home route payload." };
  }
  const states = await loadSearchHomeRouteStates();
  states[String(tabId)] = normalized;
  await saveSearchHomeRouteStates(states);
  return { ok: true, tab_id: tabId, selected_index: normalized.selected_index };
}

async function advanceSearchHomeRouteState(tabId, action) {
  if (!Number.isInteger(tabId)) {
    return { ok: false, error: "Active tab is required for Search Home navigation." };
  }
  const states = await loadSearchHomeRouteStates();
  const current = normalizeSearchHomeRouteState(states[String(tabId)]);
  if (!current || !isFreshSearchHomeRouteState(current)) {
    return { ok: false, error: "No fresh Search Home route state was found for this tab." };
  }
  let url = "";
  let nextIndex = normalizeSearchHomeIndex(current, current.selected_index);
  const normalizedAction = normalizeSearchHomeRouteAction(action);
  if (normalizedAction === "fallback") {
    url = normalizeSearchHomeCandidateUrl(current.fallback_url);
  } else if (normalizedAction === "open") {
    const selectedCandidate = current.target_candidates[nextIndex];
    url = normalizeSearchHomeCandidateUrl(selectedCandidate?.final_url || selectedCandidate?.url || current.target_url);
  } else {
    const delta = normalizedAction === "prev" ? -1 : 1;
    nextIndex = nextSearchHomeIndex(current, delta);
    const nextCandidate = current.target_candidates[nextIndex];
    url = normalizeSearchHomeCandidateUrl(nextCandidate?.final_url || nextCandidate?.url);
  }
  if (!url) {
    return { ok: false, error: "No destination URL was available for the requested Search Home action." };
  }
  states[String(tabId)] = {
    ...current,
    target_url: url,
    selected_index: nextIndex,
    updated_at: new Date().toISOString()
  };
  await saveSearchHomeRouteStates(states);
  await chrome.tabs.update(tabId, { url });
  return { ok: true, tab_id: tabId, url, selected_index: nextIndex };
}

function normalizeSearchHomeRouteAction(action) {
  const value = String(action || "").trim().toLowerCase();
  if (value === "previous" || value === "prev" || value === "left") {
    return "prev";
  }
  if (value === "open" || value === "enter") {
    return "open";
  }
  if (value === "fallback") {
    return "fallback";
  }
  return "next";
}

function normalizeSearchHomeRouteState(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidates = Array.isArray(value.target_candidates)
    ? value.target_candidates
        .map((candidate) => normalizeSearchHomeCandidate(candidate))
        .filter(Boolean)
    : [];
  const fallbackUrl = normalizeSearchHomeCandidateUrl(value.fallback_url);
  const selectedIndex = normalizeSearchHomeIndex({ target_candidates: candidates }, Number(value.selected_index));
  return {
    query: String(value.query || ""),
    target_url: normalizeSearchHomeCandidateUrl(value.target_url) || fallbackUrl || (candidates[0]?.final_url || candidates[0]?.url || ""),
    fallback_url: fallbackUrl,
    selected_index: selectedIndex,
    target_candidates: candidates,
    updated_at: typeof value.updated_at === "string" && value.updated_at ? value.updated_at : new Date().toISOString()
  };
}

function normalizeSearchHomeCandidate(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const finalUrl = normalizeSearchHomeCandidateUrl(value.final_url || value.url);
  if (!finalUrl) {
    return null;
  }
  return {
    url: normalizeSearchHomeCandidateUrl(value.url) || finalUrl,
    final_url: finalUrl,
    title: String(value.title || ""),
    domain: String(value.domain || "")
  };
}

function normalizeSearchHomeCandidateUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "";
    }
    return url.toString();
  } catch {
    return "";
  }
}

function normalizeSearchHomeIndex(state, value) {
  const total = Array.isArray(state?.target_candidates) ? state.target_candidates.length : 0;
  if (total <= 0) {
    return -1;
  }
  return Number.isInteger(value) && value >= 0 && value < total ? value : 0;
}

function nextSearchHomeIndex(state, delta) {
  const total = Array.isArray(state?.target_candidates) ? state.target_candidates.length : 0;
  if (total <= 0) {
    return -1;
  }
  const base = normalizeSearchHomeIndex(state, state.selected_index);
  return (base + delta + total) % total;
}

function isFreshSearchHomeRouteState(state) {
  if (!state || typeof state.updated_at !== "string" || !state.updated_at) {
    return false;
  }
  const updatedAt = Date.parse(state.updated_at);
  if (!Number.isFinite(updatedAt)) {
    return false;
  }
  return Date.now() - updatedAt <= SEARCH_HOME_ROUTE_MAX_AGE_MS;
}

function tabSummary(tab) {
  return {
    id: tab.id,
    windowId: tab.windowId,
    active: Boolean(tab.active),
    audible: Boolean(tab.audible),
    discarded: Boolean(tab.discarded),
    favIconUrl: tab.favIconUrl || "",
    pinned: Boolean(tab.pinned),
    status: tab.status || "unknown",
    title: tab.title || "",
    url: tab.url || ""
  };
}

function imageSizeFromDataUrl(dataUrl) {
  const match = /^data:image\/[a-z0-9.+-]+;base64,([A-Za-z0-9+/=]+)$/i.exec(String(dataUrl || ""));
  if (!match) {
    return null;
  }
  try {
    const bytes = Uint8Array.from(atob(match[1]), (char) => char.charCodeAt(0));
    if (bytes.length >= 24 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
      const view = new DataView(bytes.buffer);
      return {
        width: view.getUint32(16),
        height: view.getUint32(20)
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}
