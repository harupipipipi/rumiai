import test from "node:test";
import assert from "node:assert/strict";

import { ambientFinalAnswerKey, parseAmbientFinalAnswerPayload } from "./finalAnswerBridge";
import { shouldReadAmbientFinalAnswer } from "./useFinalAnswerBridge";

test("parseAmbientFinalAnswerPayload accepts compact latest answer payloads", () => {
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

test("parseAmbientFinalAnswerPayload ignores invalid or empty payloads", () => {
  assert.equal(parseAmbientFinalAnswerPayload("{"), null);
  assert.equal(parseAmbientFinalAnswerPayload(JSON.stringify({ text: "   " })), null);
});

test("read-aloud identity is stable across polling and rerender", () => {
  const payload = parseAmbientFinalAnswerPayload(JSON.stringify({
    conversation_id: "chat-1",
    message_id: "assistant-7",
    message_created_at: 1_500,
    text: "回答です",
    updated_at: 1_600,
  }));
  assert.ok(payload);
  assert.equal(ambientFinalAnswerKey(payload), "chat-1:assistant-7");
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
  assert.equal(shouldReadAmbientFinalAnswer({
    enabled: false,
    blocked: false,
    payload,
    enabledAt: 1_000,
    alreadySeen: false,
  }), false);
});
