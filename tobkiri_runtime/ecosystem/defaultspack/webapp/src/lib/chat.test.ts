import test from "node:test";
import assert from "node:assert/strict";
import {
  contentBlocksToText,
  deriveConversationTitle,
  formatRelativeTime,
  inspectConversationIntegrity,
  messageToText,
  orderConversationMessages,
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

test("orderConversationMessages restores chronological sequence and removes duplicate finals", () => {
  const user = {
    id: "user-1",
    role: "user",
    content: [{ type: "text", text: "weather" }],
    raw_text: "weather",
    created_at: 1000,
    conversation_id: "c1",
    sequence_number: 1,
  } satisfies ChatMessage;
  const assistant = {
    id: "assistant-1",
    role: "assistant",
    content: [{ type: "text", text: "searched" }],
    raw_text: "searched",
    created_at: 1010,
    conversation_id: "c1",
    sequence_number: 2,
    events: [{ type: "tool_call_completed", tool_name: "browser_use" }],
  } satisfies ChatMessage;
  const duplicateDone = {
    ...assistant,
    events: [{ type: "tool_call_completed", tool_name: "browser_use", message: "done" }],
  } satisfies ChatMessage;

  const ordered = orderConversationMessages([assistant, user, duplicateDone]);

  assert.deepEqual(ordered.map((message) => message.id), ["user-1", "assistant-1"]);
  assert.deepEqual(ordered[1].events, duplicateDone.events);
});

test("orderConversationMessages collapses duplicate sequence finals even when ids differ", () => {
  const assistantA = {
    id: "assistant-1",
    role: "assistant",
    content: [{ type: "text", text: "draft" }],
    raw_text: "draft",
    created_at: 1010,
    conversation_id: "c1",
    sequence_number: 2,
  } satisfies ChatMessage;
  const assistantB = {
    ...assistantA,
    id: "assistant-2",
    raw_text: "final",
    content: [{ type: "text", text: "final" }],
  } satisfies ChatMessage;

  const ordered = orderConversationMessages([assistantA, assistantB]);
  const diagnostics = inspectConversationIntegrity([assistantA, assistantB]);

  assert.equal(ordered.length, 1);
  assert.equal(ordered[0]?.raw_text, "final");
  assert.equal(diagnostics.collapsedCount, 1);
  assert.equal(diagnostics.duplicateSequenceCount, 1);
});
