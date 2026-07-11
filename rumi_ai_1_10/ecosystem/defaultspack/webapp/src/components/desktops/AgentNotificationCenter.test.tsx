import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import type { Conversation } from "../../lib/api";
import { layerClassName } from "../../ui/layers/layerTokens";
import { classifyConversation } from "./AgentNotificationCenter";

function conversation(messages: Conversation["messages"]): Conversation {
  return {
    id: "chat-1",
    title: "Deploy helper",
    created_at: 1,
    updated_at: 300,
    messages,
  } as Conversation;
}

test("latest successful run is not failed by an older failed event", () => {
  const item = classifyConversation(conversation([
    { id: "old", conversation_id: "chat-1", role: "assistant", content: [], created_at: 100, events: [{ type: "task_failed", status: "failed" }] },
    { id: "latest", conversation_id: "chat-1", role: "assistant", content: [{ type: "text", text: "Deploy complete" }], created_at: 300, finish_reason: "stop" },
  ]), {}, {}, 400);
  assert.equal(item.status, "done");
  assert.equal(item.summary, "Deploy complete");
  assert.equal(item.unread, true);
});

test("read high-water mark controls the unread badge deterministically", () => {
  const value = conversation([
    { id: "latest", conversation_id: "chat-1", role: "assistant", content: [{ type: "text", text: "Done" }], created_at: 300, finish_reason: "stop" },
  ]);
  assert.equal(classifyConversation(value, {}, { "chat-1": 299 }, 400).unread, true);
  assert.equal(classifyConversation(value, {}, { "chat-1": 300 }, 400).unread, false);
});

test("notification center keeps filter, search, navigation, mark-all, and toast layer contracts", () => {
  const source = readFileSync(new URL("./AgentNotificationCenter.tsx", import.meta.url), "utf8");
  assert.match(source, /label: "見るべき"/);
  assert.match(source, /placeholder="タイトル・内容・toolで検索"/);
  assert.match(source, /window\.location\.assign/);
  assert.match(source, /onClick=\{markAllRead\}/);
  assert.match(source, /layerClassName\.toast/);
  assert.equal(layerClassName.toast, "rumi-layer-toast");
});
