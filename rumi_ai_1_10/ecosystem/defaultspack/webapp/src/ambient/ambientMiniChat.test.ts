import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { Conversation } from "../lib/api";
import { AmbientMiniChat } from "./AmbientMiniChat";
import { ambientConversationIdFromResult, ambientLinkedConversationId, ambientMiniChatMessages } from "./ambientMiniChatState";
import type { AmbientStatus } from "./ambientTriggerClient";

test("ambient mini chat resolves the linked conversation from routing state", () => {
  assert.equal(ambientLinkedConversationId(status({ mode: "selected_chat", conversation_id: "chat-1" }), null), "chat-1");
  assert.equal(ambientLinkedConversationId(status({ mode: "selected_chat" }), "active-chat"), "active-chat");
  assert.equal(ambientLinkedConversationId(status({ mode: "startup_new_chat", session_conversation_id: "session-chat" }), "active-chat"), "session-chat");
  assert.equal(ambientLinkedConversationId(status({ mode: "always_new_chat", conversation_id: "ignored" }), "active-chat"), null);
});

test("ambient mini chat extracts dispatched conversation ids from ambient results", () => {
  assert.equal(ambientConversationIdFromResult({ conversation_id: "top-level" }), "top-level");
  assert.equal(ambientConversationIdFromResult({ dispatch: { conversation_id: "dispatch-chat" } }), "dispatch-chat");
  assert.equal(ambientConversationIdFromResult({ pending_approval: { conversation_id: "pending-chat" } }), "pending-chat");
  assert.equal(ambientConversationIdFromResult({ status: "ok" }), null);
});

test("ambient mini chat keeps recent user and assistant text in order", () => {
  const conversation = {
    id: "c1",
    title: "Mini",
    created_at: 1,
    updated_at: 4,
    model: "stub/default",
    tags: [],
    is_starred: false,
    is_archived: false,
    messages: [
      message({ id: "a1", role: "assistant", raw_text: "こんにちは", created_at: 3, sequence_number: 2 }),
      message({ id: "u1", role: "user", raw_text: "hello こんにちは", created_at: 2, sequence_number: 1 }),
      message({ id: "s1", role: "system", raw_text: "hidden", created_at: 1, sequence_number: 0 }),
    ],
  } satisfies Conversation;

  assert.deepEqual(ambientMiniChatMessages(conversation, 4), [
    { id: "u1", role: "user", text: "hello こんにちは", createdAt: 2 },
    { id: "a1", role: "assistant", text: "こんにちは", createdAt: 3 },
  ]);
});

test("ambient mini chat hides routing picker controls for the standalone normal screen", () => {
  const html = renderToStaticMarkup(createElement(AmbientMiniChat, {
    conversation: null,
    conversationId: null,
    routingSummary: "次の送信で作成",
    loading: false,
    error: null,
    input: "",
    sending: false,
    disabled: false,
    latestInputPreview: null,
    showPicker: false,
    onInputChange: () => {},
    onSubmit: (event) => event.preventDefault(),
    onRefresh: () => {},
    onPickChat: () => {},
  }));

  assert.equal(html.includes("チャットを選ぶ"), false);
  assert.equal(html.includes("選択"), false);
  assert.equal(html.includes("Defaultspack"), false);
  assert.match(html, /次の送信で作成/);
  assert.match(html, /メッセージ/);
});

function status(routing: AmbientStatus["routing"]): AmbientStatus {
  return {
    ambient_monitor: { enabled: false },
    services: {
      voice_wake_monitor: {},
      gesture_wake_monitor: {},
    },
    permissions: {
      rumi: {},
      os: {},
    },
    routing,
  };
}

function message(patch: Partial<Conversation["messages"][number]>): Conversation["messages"][number] {
  return {
    id: "m",
    role: "user",
    content: [{ type: "text", text: "" }],
    raw_text: "",
    created_at: 1,
    conversation_id: "c1",
    ...patch,
  };
}
