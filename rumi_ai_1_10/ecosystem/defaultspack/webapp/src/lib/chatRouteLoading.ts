type ChatRouteLocation = {
  href: string;
  pathname: string;
  search: string;
  hash: string;
};

type ChatRouteHistory = {
  pushState(state: unknown, title: string, url?: string | URL | null): void;
  replaceState(state: unknown, title: string, url?: string | URL | null): void;
};

type ChatRouteWindow = {
  location: ChatRouteLocation;
  history: ChatRouteHistory;
};

type ChatRouteHistoryMode = "push" | "replace";

function routeWindow(targetWindow?: ChatRouteWindow): ChatRouteWindow {
  if (targetWindow) return targetWindow;
  return window;
}

function cleanString(value: unknown): string {
  return String(value ?? "").trim();
}

function metadataRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function metadataString(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = cleanString(record[key]);
    if (value) return value;
  }
  return "";
}

function hasStaleConversationMarker(record: Record<string, unknown>): boolean {
  if (record.superseded === true || record.stale === true || record.is_stale === true) return true;
  const status = cleanString(record.status ?? record.state ?? record.lifecycle).toLowerCase();
  return status === "stale" || status === "superseded";
}

export function chatIdFromLocation(targetWindow?: ChatRouteWindow): string | null {
  const params = new URLSearchParams(routeWindow(targetWindow).location.search);
  return params.get("chat") || null;
}

export function isPendingInLocation(targetWindow?: ChatRouteWindow): boolean {
  const params = new URLSearchParams(routeWindow(targetWindow).location.search);
  return params.get("pending") === "1";
}

export function replaceChatIdInUrl(
  conversationId: string | null,
  pending?: boolean,
  options: { historyMode?: ChatRouteHistoryMode; targetWindow?: ChatRouteWindow } = {},
): void {
  const target = routeWindow(options.targetWindow);
  const url = new URL(target.location.href);
  url.pathname = target.location.pathname === "/coding" ? "/coding" : "/chat";
  if (conversationId) {
    url.searchParams.set("chat", conversationId);
  } else {
    url.searchParams.delete("chat");
  }
  if (pending === true) {
    url.searchParams.set("pending", "1");
  } else if (pending === false || !conversationId) {
    url.searchParams.delete("pending");
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  const current = `${target.location.pathname}${target.location.search}${target.location.hash}`;
  if (next === current) return;
  const state = { conversationId };
  if (options.historyMode === "replace") {
    target.history.replaceState(state, "", next);
  } else {
    target.history.pushState(state, "", next);
  }
}

export async function loadConversationForRefresh({
  preferredId,
  activeConversationId,
  locationChatId,
  listedConversations,
  loadConversation,
}: {
  preferredId?: string | null;
  activeConversationId?: string | null;
  locationChatId?: string | null;
  listedConversations: Array<{ id: string }>;
  loadConversation: (conversationId: string | null) => Promise<void>;
}): Promise<void> {
  const targetId = preferredId ?? locationChatId ?? activeConversationId ?? listedConversations[0]?.id ?? null;
  if (!targetId) {
    await loadConversation(null);
    return;
  }

  if (listedConversations.some((conversation) => conversation.id === targetId)) {
    await loadConversation(targetId);
    return;
  }

  try {
    await loadConversation(targetId);
  } catch {
    await loadConversation(listedConversations[0]?.id ?? null);
  }
}

export function resolveSupersededConversationRedirect(
  conversation: { id?: string | null; metadata?: unknown } | null | undefined,
  requestedId: string | null | undefined,
): string | null {
  const record = metadataRecord(conversation?.metadata);
  if (!hasStaleConversationMarker(record)) return null;
  const activeId = metadataString(
    record,
    "active_conversation_id",
    "activeConversationId",
    "replacement_conversation_id",
    "replacementConversationId",
    "replacement_chat_id",
    "replacementChatId",
    "superseded_by_conversation_id",
    "supersededByConversationId",
  );
  if (!activeId || activeId === requestedId || activeId === conversation?.id) return null;
  return activeId;
}
