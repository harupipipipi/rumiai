import test from "node:test";
import assert from "node:assert/strict";

import { messageCopyText } from "./ChatMessagesRenderer";
import type { ChatUiMessage } from "./types";

function message(overrides: Partial<ChatUiMessage>): ChatUiMessage {
  return {
    id: "message-1",
    role: "agent",
    content: [],
    rawText: "",
    ...overrides,
  };
}

test("message copy text includes visible text and code blocks", () => {
  assert.equal(messageCopyText(message({
    content: [
      { type: "markdown", text: "hello" },
      { type: "code", text: "const ok = true;" },
    ],
  })), "hello\n\nconst ok = true;");
});

test("message copy text falls back to raw text", () => {
  assert.equal(messageCopyText(message({ rawText: "fallback text" })), "fallback text");
});
