import test from "node:test";
import assert from "node:assert/strict";
import {
  contentBlocksToText,
  deriveConversationTitle,
  formatRelativeTime,
  messageToText,
} from "./chat";
import type { ChatMessage } from "./api";

test("contentBlocksToText flattens text blocks", () => {
  const text = contentBlocksToText([
    { type: "text", text: "hello" },
    { type: "image", url: "ignored" },
    { type: "text", text: "world" },
  ]);
  assert.equal(text, "hello\nworld");
});

test("messageToText prefers raw_text when present", () => {
  const message = {
    id: "m1",
    role: "assistant",
    content: [{ type: "text", text: "fallback" }],
    raw_text: "preferred",
    created_at: Date.now(),
    conversation_id: "c1",
  } satisfies ChatMessage;
  assert.equal(messageToText(message), "preferred");
});

test("deriveConversationTitle trims and caps length", () => {
  assert.equal(deriveConversationTitle("   "), "New Conversation");
  assert.equal(
    deriveConversationTitle(
      "this is a very long conversation title that should be shortened",
    ),
    "this is a very long conversation title t...",
  );
});

test("formatRelativeTime formats short durations", () => {
  const now = 10_000;
  assert.equal(formatRelativeTime(9_000, now), "just now");
  assert.equal(formatRelativeTime(0, 61_000), "1m ago");
});
