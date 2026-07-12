import test from "node:test";
import assert from "node:assert/strict";

import type { Conversation } from "../lib/api";
import {
  ambientFinalAnswerKey,
  createAmbientFinalAnswerReference,
  parseAmbientFinalAnswerPayload,
  parseAmbientFinalAnswerReference,
  publishAmbientFinalAnswerPayload,
} from "./finalAnswerBridge";
import {
  ambientFinalAnswerPayloadFromReference,
  shouldReadAmbientFinalAnswer,
} from "./useFinalAnswerBridge";

test("parseAmbientFinalAnswerPayload accepts direct in-memory answer payloads", () => {
  assert.deepEqual(parseAmbientFinalAnswerPayload(JSON.stringify({
    conversation_id: "chat-1",
    message_id: "assistant-7",
    message_created_at: 120,
    text: "  了解です  ",
    updated_at: 123,
  })), {
    conversation_id: "chat-1",
    message_id: "assistant-7",
    message_created_at: 120,
    text: "了解です",
    updated_at: 123,
  });
});

test("ambient final-answer references are short-lived and contain no answer text", () => {
  const reference = createAmbientFinalAnswerReference({
    conversationId: "chat-1",
    messageId: "assistant-7",
    messageCreatedAt: 1_500,
    text: "private answer text",
    updatedAt: 1_600,
  }, 1_700);

  assert.ok(reference);
  const serialized = JSON.stringify(reference);
  assert.doesNotMatch(serialized, /private answer text|"text"/);
  assert.equal(reference.kind, "ambient_final_answer_ref");
  assert.equal(reference.expires_at, 31_700);
  assert.deepEqual(parseAmbientFinalAnswerReference(reference, 1_800), reference);
  assert.equal(parseAmbientFinalAnswerReference(reference, 31_701), null);
  assert.equal(parseAmbientFinalAnswerReference({ ...reference, text: "injected" }, 1_800), null);
});

test("publishing broadcasts only the reference and never persists a full payload fallback", () => {
  const originalBroadcastChannel = globalThis.BroadcastChannel;
  const messages: unknown[] = [];
  class FakeBroadcastChannel {
    constructor(readonly name: string) {}
    postMessage(value: unknown) {
      messages.push({ name: this.name, value });
    }
    close() {}
  }
  Object.defineProperty(globalThis, "BroadcastChannel", {
    configurable: true,
    value: FakeBroadcastChannel,
  });

  try {
    const reference = publishAmbientFinalAnswerPayload({
      conversationId: "chat-1",
      messageId: "assistant-7",
      messageCreatedAt: 1_500,
      text: "sensitive final answer",
      updatedAt: 1_600,
    });

    assert.ok(reference);
    assert.equal(messages.length, 1);
    const serialized = JSON.stringify(messages);
    assert.doesNotMatch(serialized, /sensitive final answer|"text"/);
    assert.match(serialized, /ambient_final_answer_ref/);
  } finally {
    Object.defineProperty(globalThis, "BroadcastChannel", {
      configurable: true,
      value: originalBroadcastChannel,
    });
  }
});

test("publishing fails closed when an authoritative conversation or message identity is missing", () => {
  assert.equal(publishAmbientFinalAnswerPayload({
    conversationId: null,
    messageId: "assistant-7",
    text: "answer",
  }), null);
  assert.equal(publishAmbientFinalAnswerPayload({
    conversationId: "chat-1",
    messageId: null,
    text: "answer",
  }), null);
});

test("authenticated conversation lookup must match the referenced conversation and final message", () => {
  const reference = createAmbientFinalAnswerReference({
    conversationId: "chat-1",
    messageId: "assistant-7",
    messageCreatedAt: 1_500,
    text: "not transported",
    updatedAt: 1_600,
  }, 1_700);
  assert.ok(reference);

  const conversation = {
    id: "chat-1",
    title: "Chat",
    created_at: 1_000,
    updated_at: 1_600,
    messages: [
      {
        id: "assistant-7",
        role: "assistant",
        content: "authoritative answer",
        created_at: 1_500,
        conversation_id: "chat-1",
      },
    ],
  } as Conversation;

  const payload = ambientFinalAnswerPayloadFromReference(reference, conversation);
  assert.ok(payload);
  assert.equal(payload.text, "authoritative answer");
  assert.equal(ambientFinalAnswerKey(payload), "chat-1:assistant-7");
  assert.equal(ambientFinalAnswerPayloadFromReference(
    { ...reference, message_id: "assistant-other" },
    conversation,
  ), null);
  assert.equal(ambientFinalAnswerPayloadFromReference(
    reference,
    { ...conversation, id: "chat-other" },
  ), null);
});

test("read-aloud identity is stable across authoritative polling and rerender", () => {
  const payload = parseAmbientFinalAnswerPayload(JSON.stringify({
    conversation_id: "chat-1",
    message_id: "assistant-7",
    message_created_at: 1_500,
    text: "回答です",
    updated_at: 1_600,
  }));
  assert.ok(payload);
  assert.equal(shouldReadAmbientFinalAnswer({
    enabled: true,
    blocked: false,
    payload,
    enabledAt: 1_000,
    alreadySeen: false,
  }), true);
  assert.equal(shouldReadAmbientFinalAnswer({
    enabled: true,
    blocked: false,
    payload,
    enabledAt: 1_000,
    alreadySeen: true,
  }), false);
});
