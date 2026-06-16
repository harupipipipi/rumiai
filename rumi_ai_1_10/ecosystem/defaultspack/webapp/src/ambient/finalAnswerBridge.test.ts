import test from "node:test";
import assert from "node:assert/strict";

import { parseAmbientFinalAnswerPayload } from "./finalAnswerBridge";

test("parseAmbientFinalAnswerPayload accepts compact latest answer payloads", () => {
  assert.deepEqual(parseAmbientFinalAnswerPayload(JSON.stringify({
    conversation_id: "chat-1",
    text: "  了解です  ",
    updated_at: 123,
  })), {
    conversation_id: "chat-1",
    text: "了解です",
    updated_at: 123,
  });
});

test("parseAmbientFinalAnswerPayload ignores invalid or empty payloads", () => {
  assert.equal(parseAmbientFinalAnswerPayload("{"), null);
  assert.equal(parseAmbientFinalAnswerPayload(JSON.stringify({ text: "   " })), null);
});
