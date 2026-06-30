import test from "node:test";
import assert from "node:assert/strict";

import { loadConversationForRefresh } from "../App";

test("refresh conversation loading honors URL chat id missing from the conversation list", async () => {
  const loaded: Array<string | null> = [];

  await loadConversationForRefresh({
    preferredId: null,
    activeConversationId: null,
    locationChatId: "old-chat",
    listedConversations: [{ id: "recent-chat" }],
    loadConversation: async (conversationId) => {
      loaded.push(conversationId);
    },
  });

  assert.deepEqual(loaded, ["old-chat"]);
});

test("refresh conversation loading falls back when direct URL chat load fails", async () => {
  const loaded: Array<string | null> = [];

  await loadConversationForRefresh({
    preferredId: null,
    activeConversationId: null,
    locationChatId: "missing-chat",
    listedConversations: [{ id: "recent-chat" }],
    loadConversation: async (conversationId) => {
      loaded.push(conversationId);
      if (conversationId === "missing-chat") {
        throw new Error("HTTP 404");
      }
    },
  });

  assert.deepEqual(loaded, ["missing-chat", "recent-chat"]);
});
