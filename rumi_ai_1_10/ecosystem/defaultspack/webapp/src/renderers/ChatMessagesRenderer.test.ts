import test from "node:test";
import assert from "node:assert/strict";

import { messageCopyText, streamedBrowserScreenshots } from "./ChatMessagesRenderer";
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

test("streamed browser screenshots include explicit screenshot events", () => {
  const screenshots = streamedBrowserScreenshots(message({
    id: "optimistic-assistant-1",
    events: [
      {
        type: "browser_screenshot",
        tool_call_id: "call_1",
        data_url: "data:image/png;base64,abc",
        action: "computer.screenshot",
        image_size: { width: 800, height: 600 },
      },
    ],
  }));

  assert.equal(screenshots.length, 1);
  assert.equal(screenshots[0].data_url, "data:image/png;base64,abc");
  assert.equal(screenshots[0].action, "computer.screenshot");
  assert.deepEqual(screenshots[0].image_size, { width: 800, height: 600 });
});

test("streamed browser screenshots include nested tool result artifacts", () => {
  const screenshots = streamedBrowserScreenshots(message({
    id: "optimistic-assistant-2",
    events: [
      {
        type: "tool_result",
        tool_name: "browser_companion",
        tool_call_id: "call_2",
        result: {
          data: {
            screenshot: {
              data_url: "data:image/png;base64,def",
              marker: { x: 10, y: 12 },
            },
          },
        },
      },
    ],
  }));

  assert.equal(screenshots.length, 1);
  assert.equal(screenshots[0].tool_call_id, "call_2");
  assert.equal(screenshots[0].tool_name, "browser_companion");
  assert.equal(screenshots[0].data_url, "data:image/png;base64,def");
  assert.deepEqual(screenshots[0].marker, { x: 10, y: 12 });
});
