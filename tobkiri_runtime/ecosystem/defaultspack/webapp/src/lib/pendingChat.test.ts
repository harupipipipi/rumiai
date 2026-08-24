import test from "node:test";
import assert from "node:assert/strict";

import type { ChatMessage } from "./api";
import {
  PENDING_CHAT_REQUEST_TTL_MS,
  PENDING_USER_ONLY_GRACE_MS,
  activePendingChatOperation,
  isAssistantMessageStillRunning,
  shouldClearPendingAfterConversationRefresh,
  shouldForgetPendingAfterPollError,
  type PendingChatRequest,
} from "./pendingChat";

test("active pending operations exclude stale or invalid persisted requests", () => {
  const now = Date.UTC(2026, 7, 24, 3, 4);
  const request = pending(now - 1_000);

  assert.equal(activePendingChatOperation(request, now), "send");
  assert.equal(activePendingChatOperation({ ...request, kind: "approval" }, now), "approval");
  assert.equal(activePendingChatOperation({
    ...request,
    startedAt: now - PENDING_CHAT_REQUEST_TTL_MS,
  }, now), null);
  assert.equal(activePendingChatOperation({ ...request, startedAt: Number.NaN }, now), null);
  assert.equal(activePendingChatOperation({ ...request, startedAt: now + 1_000 }, now), null);
  assert.equal(activePendingChatOperation(null, now), null);
});

function message(patch: Partial<ChatMessage>): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content: [],
    created_at: 1000,
    conversation_id: "c1",
    metadata: null,
    events: [],
    tool_logs: [],
    ...patch,
  };
}

function pending(startedAt: number): PendingChatRequest {
  return {
    conversationId: "c1",
    startedAt,
    status: "Processing...",
    toolNames: [],
  };
}

test("assistant streaming metadata keeps pending active", () => {
  assert.equal(isAssistantMessageStillRunning(message({
    finish_reason: "streaming",
    metadata: { thinking: { state: "running" } },
  })), true);
});

test("completed assistant clears pending", () => {
  const latest = message({
    finish_reason: "stop",
    metadata: { thinking: { state: "completed" } },
  });

  assert.equal(shouldClearPendingAfterConversationRefresh(latest, pending(1000), 2000), true);
});

test("stale user-only pending is cleared after reload grace", () => {
  const latest = message({ role: "user" });

  assert.equal(shouldClearPendingAfterConversationRefresh(latest, pending(1000), 1000 + PENDING_USER_ONLY_GRACE_MS - 1), false);
  assert.equal(shouldClearPendingAfterConversationRefresh(latest, pending(1000), 1000 + PENDING_USER_ONLY_GRACE_MS), true);
});

test("poll transport failures preserve the operation id until an explicit terminal response", () => {
  for (const error of [
    new TypeError("Failed to fetch"),
    new Error("network connection interrupted"),
    new Error("HTTP 500 Internal Server Error"),
    new Error("timeout while checking conversation"),
  ]) {
    assert.equal(shouldForgetPendingAfterPollError(error), false, error.message);
  }
  assert.equal(shouldForgetPendingAfterPollError(new Error("HTTP 404 Not Found\nconversation missing")), true);
  assert.equal(shouldForgetPendingAfterPollError(new Error("HTTP 410 Gone (EXPIRED)")), true);
  assert.equal(shouldForgetPendingAfterPollError(new Error("NOT_FOUND")), true);
});
