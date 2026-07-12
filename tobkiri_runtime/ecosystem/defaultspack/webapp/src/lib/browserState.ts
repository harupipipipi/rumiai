import type { ChatActivityEvent } from "./api";

export type BrowserStateView = {
  state_revision: number;
  loading: boolean;
  stale: boolean;
  run_id?: string;
  conversation_id?: string;
  scope_key?: string;
  invalidated?: Record<string, unknown>;
  snapshot?: Record<string, unknown>;
  dom_snapshot?: Record<string, unknown>;
  screenshot?: Record<string, unknown>;
  tool_call_id?: string;
  tool_name?: string;
};

const BROWSER_STATE_EVENT_TYPES = new Set([
  "browser_state_invalidated",
  "browser_state_snapshot",
  "browser_dom_snapshot",
  "browser_screenshot",
]);

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function browserStateScopeKey(event: ChatActivityEvent): string {
  const conversationId = asString(event.conversation_id) ?? "";
  const runId = asString(event.run_id) ?? "";
  const sourceKey = asString(event.tool_call_id)
    ?? asString(event.source)
    ?? asString(event.tool_name)
    ?? "";
  return `${conversationId}:${runId}:${sourceKey}`;
}

export function isBrowserStateEvent(event: ChatActivityEvent): boolean {
  return BROWSER_STATE_EVENT_TYPES.has(String(event.type ?? ""));
}

export function browserStateEventRevision(event: ChatActivityEvent): number {
  const value = Number(event.state_revision ?? -1);
  return Number.isFinite(value) ? value : -1;
}

export function createBrowserStateView(): BrowserStateView {
  return {
    state_revision: -1,
    loading: false,
    stale: false,
  };
}

export function reduceBrowserStateEvent(current: BrowserStateView, event: ChatActivityEvent): BrowserStateView {
  if (!isBrowserStateEvent(event)) return current;
  const nextScopeKey = browserStateScopeKey(event);
  const currentScopeKey = current.scope_key ?? "";
  const sameScope = !nextScopeKey || !currentScopeKey || nextScopeKey === currentScopeKey;
  const nextRevision = browserStateEventRevision(event);
  if (sameScope && nextRevision < current.state_revision) return current;

  const seed = sameScope ? current : createBrowserStateView();
  const base: BrowserStateView = {
    ...seed,
    state_revision: nextRevision,
    run_id: asString(event.run_id) ?? seed.run_id,
    conversation_id: asString(event.conversation_id) ?? seed.conversation_id,
    scope_key: nextScopeKey || seed.scope_key,
    tool_call_id: typeof event.tool_call_id === "string" ? event.tool_call_id : seed.tool_call_id,
    tool_name: typeof event.tool_name === "string" ? event.tool_name : seed.tool_name,
  };

  if (event.type === "browser_state_invalidated") {
    return {
      ...base,
      loading: true,
      stale: true,
      invalidated: asRecord(event.invalidated) ?? current.invalidated,
    };
  }
  if (event.type === "browser_state_snapshot") {
    return {
      ...base,
      loading: false,
      stale: false,
      snapshot: asRecord(event.snapshot) ?? current.snapshot,
    };
  }
  if (event.type === "browser_dom_snapshot") {
    return {
      ...base,
      loading: false,
      stale: false,
      dom_snapshot: asRecord(event.dom_snapshot) ?? current.dom_snapshot,
    };
  }
  if (event.type === "browser_screenshot") {
    return {
      ...base,
      loading: false,
      stale: false,
      screenshot: asRecord(event.screenshot) ?? asRecord(event) ?? current.screenshot,
    };
  }
  return current;
}

export function reduceBrowserStateFromEvents(events: ChatActivityEvent[]): BrowserStateView {
  return events.reduce(reduceBrowserStateEvent, createBrowserStateView());
}
