import test from "node:test";
import assert from "node:assert/strict";

import { compactLogPreviewText, isCompactLogLikeMessageText, messageCopyText, shouldRenderImageBlockInChat, streamedBrowserScreenshots, summarizePendingToolNames } from "./ChatMessagesRenderer";
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

test("pending tool summary shows two names and the remaining count", () => {
  const summary = summarizePendingToolNames(["web_search", "browser", "calendar", "web_search"]);

  assert.deepEqual(summary.visibleNames, ["web_search", "browser"]);
  assert.equal(summary.hiddenCount, 1);
  assert.equal(summary.summary, "web_search、browser、その他 1 個が見込まれました");
});

test("long terminal-style output is detected for compact display", () => {
  const logText = JSON.stringify({
    tool_name: "coding_terminal_exec",
    classification: "high",
    risk_reasons: ["shell_escape"],
    cwd: "/tmp/project",
    exit_code: 0,
    stdout: Array.from({ length: 80 }, (_, index) => `pytest line ${index}`).join("\\n"),
    stderr: "",
  }).repeat(8);

  assert.equal(isCompactLogLikeMessageText(logText), true);
});

test("ordinary long markdown is not treated as a terminal log", () => {
  const prose = Array.from({ length: 80 }, (_, index) => (
    `Section ${index}: this paragraph explains architecture, tradeoffs, state transitions, UI behavior, and next steps in normal prose.`
  )).join("\n\n");

  assert.equal(isCompactLogLikeMessageText(prose), false);
});

test("compact log preview keeps head and tail while normalizing escaped newlines", () => {
  const text = `{"stdout":"${Array.from({ length: 420 }, (_, index) => `line-${index}`).join("\\n")}","exit_code":0,"classification":"high","risk_reasons":["shell_escape"],"cwd":"/tmp/project","tool_name":"coding_terminal_exec"}`;
  const preview = compactLogPreviewText(text, 800);

  assert.equal(preview.omitted, true);
  assert.match(preview.text, /line-0/);
  assert.match(preview.text, /line-419/);
  assert.match(preview.text, /chars omitted/);
  assert.equal(preview.text.includes("\\nline-"), false);
});

test("image blocks stay out of chat unless explicitly marked for display", () => {
  assert.equal(shouldRenderImageBlockInChat({ type: "image_url", url: "data:image/png;base64,abc" }), false);
  assert.equal(shouldRenderImageBlockInChat({ type: "image_url", url: "data:image/png;base64,abc", presentation: "chat" }), true);
  assert.equal(shouldRenderImageBlockInChat({ type: "image", url: "data:image/png;base64,abc", intent: "show_to_user" }), true);
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
