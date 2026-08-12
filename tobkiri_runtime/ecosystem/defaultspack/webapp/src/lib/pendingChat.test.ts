import test from "node:test";
import assert from "node:assert/strict";

import type { ChatMessage } from "./api";
import {
  PENDING_USER_ONLY_GRACE_MS,
  isAssistantMessageStillRunning,
  pendingRequestBelongsToConversation,
  shouldClearPendingAfterConversationRefresh,
  shouldForgetPendingAfterPollError,
  shouldKeepPendingAfterConversationRefresh,
  type PendingChatRequest,
} from "./pendingChat";

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

test("recovered pending for an empty conversation is cleared so the new composer can render", () => {
  const request = { ...pending(1000), recoveredFromLocation: true };

  assert.equal(shouldKeepPendingAfterConversationRefresh(undefined, request, 1200), false);
  assert.equal(shouldClearPendingAfterConversationRefresh(undefined, request, 1200), true);
});

test("operation-backed pending survives empty and user-only refreshes until a terminal response", () => {
  const request = { ...pending(1000), operationId: "operation-1", recoveredFromLocation: true };

  assert.equal(shouldKeepPendingAfterConversationRefresh(undefined, request, 1200), true);
  assert.equal(
    shouldKeepPendingAfterConversationRefresh(
      message({ role: "user" }),
      request,
      1000 + PENDING_USER_ONLY_GRACE_MS,
    ),
    true,
  );
});

test("pending approval state clears global thinking while preserving the approval message", () => {
  const latest = message({
    finish_reason: "streaming",
    metadata: {
      thinking: { state: "running" },
      pendingAuthorityApproval: {
        request_id: "auth-1",
        permission_id: "model.invoke",
        resource: { provider_id: "opencode-go" },
      },
    },
  });

  assert.equal(isAssistantMessageStillRunning(latest), true);
  assert.equal(shouldKeepPendingAfterConversationRefresh(latest, pending(1000), 1200), false);
  assert.equal(shouldClearPendingAfterConversationRefresh(latest, pending(1000), 1200), true);
});

test("tool approval events clear global thinking so the approval card can recover input", () => {
  const latest = message({
    finish_reason: "streaming",
    metadata: { thinking: { state: "running" } },
    events: [{
      type: "approval_requested",
      phase: "approval_requested",
      tool_name: "browser_companion",
      requires_approval: true,
      approval_request_id: "apr-browser-1",
    }],
  });

  assert.equal(isAssistantMessageStillRunning(latest), true);
  assert.equal(shouldKeepPendingAfterConversationRefresh(latest, pending(1000), 1200), false);
  assert.equal(shouldClearPendingAfterConversationRefresh(latest, pending(1000), 1200), true);
});

test("pending request must belong to the active conversation", () => {
  assert.equal(pendingRequestBelongsToConversation("c1", pending(1000)), true);
  assert.equal(pendingRequestBelongsToConversation("c2", pending(1000)), false);
  assert.equal(pendingRequestBelongsToConversation(null, pending(1000)), false);
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
