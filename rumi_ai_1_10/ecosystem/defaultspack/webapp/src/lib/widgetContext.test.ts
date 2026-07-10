import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import type { Conversation } from "./api";
import { createWidgetConversationContext } from "./widgetContext";

const conversation = {
  id: "conversation-active",
  title: "Widget context",
  created_at: 1,
  updated_at: 2,
  model: "stub/default",
  tags: [],
  is_starred: false,
  is_archived: false,
  messages: [],
} satisfies Conversation;

test("widget context locks conversation reads and exports to the active conversation", async () => {
  const calls: Array<[string, string, string?]> = [];
  const context = createWidgetConversationContext(conversation.id, {
    async getConversation(conversationId) {
      calls.push(["get", conversationId]);
      return conversation;
    },
    async exportConversation(conversationId, format) {
      calls.push(["export", conversationId, format]);
      return { conversation_id: conversationId, format, content: "{}" };
    },
  });

  assert.equal(context.activeConversationId, conversation.id);
  assert.equal(await context.fetchConversation(), conversation);
  assert.deepEqual(await context.exportConversation(), {
    conversation_id: conversation.id,
    format: "json",
    content: "{}",
  });
  assert.deepEqual(calls, [
    ["get", conversation.id],
    ["export", conversation.id, "json"],
  ]);
});

test("widget context performs no API or filesystem work without an active conversation", async () => {
  let apiCalled = false;
  const context = createWidgetConversationContext(null, {
    async getConversation() {
      apiCalled = true;
      return conversation;
    },
    async exportConversation() {
      apiCalled = true;
      return { conversation_id: conversation.id, format: "json", content: "{}" };
    },
  });

  assert.equal(await context.fetchConversation(), null);
  assert.equal(await context.exportConversation(), null);
  assert.equal(apiCalled, false);
});

test("App propagates one controlled context into every widget-capable shell surface", () => {
  const source = fs.readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
  assert.match(source, /const widgetContext = useMemo\(\s*\(\) => createWidgetConversationContext\(activeConversationId\)/);
  assert.equal(source.match(/widgetContext=\{widgetContext\}/g)?.length, 4);
  assert.doesNotMatch(source, /\b(?:readFile(?:Sync)?|readTextFile)\s*\(/);
});
