import test from "node:test";
import assert from "node:assert/strict";

import { AUTHORITY_FOLLOWUP_TEXT, compactLogPreviewText, formatMessageTimestamp, hasRunningToolActivityGroups, isAuthorityWaitingMessage, isCompactLogLikeMessageText, isHiddenAuthorityFollowupMessage, messageCopyText, shouldRenderImageBlockInChat, shouldShowEmptyResponseWarning, streamedBrowserScreenshots, summarizePendingToolNames, summarizeToolActivityGroups, visibleChatMessages } from "./ChatMessagesRenderer";
import type { ChatUiMessage } from "./types";

const RISKY_AUTHORITY_FOLLOWUP_PHRASES = [
  "Thank you for granting",
  "approved provider",
  "approved model",
  "I can now use",
  "使用を許可しました",
];

function message(overrides: Partial<ChatUiMessage>): ChatUiMessage {
  return {
    id: "message-1",
    role: "agent",
    content: [],
    rawText: "",
    ...overrides,
  };
}

function assertNoRiskyAuthorityFollowupPhrases(text: string): void {
  for (const phrase of RISKY_AUTHORITY_FOLLOWUP_PHRASES) {
    assert.equal(text.includes(phrase), false, `unexpected risky phrase: ${phrase}`);
  }
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

test("formatMessageTimestamp shows the conversation day and time", () => {
  const label = formatMessageTimestamp(Date.UTC(2026, 5, 4, 3, 5));

  assert.match(label, /2026/);
  assert.match(label, /06/);
  assert.match(label, /04/);
  assert.match(label, /03|12/);
  assert.match(label, /05/);
});

test("pending tool summary shows two names and the remaining count", () => {
  const summary = summarizePendingToolNames(["web_search", "browser", "calendar", "web_search"]);

  assert.deepEqual(summary.visibleNames, ["web_search", "browser"]);
  assert.equal(summary.hiddenCount, 1);
  assert.equal(summary.summary, "web_search、browser、その他 1 個が見込まれました");
});

test("completed tool activity summary uses elapsed work span", () => {
  const summary = summarizeToolActivityGroups([
    {
      id: "files",
      label: "ファイル",
      items: [
        {
          id: "item-1",
          toolName: "coding_file_list",
          folder: "coding/files",
          folderLabel: "ファイル",
          input: "src",
          title: "ファイル / coding_file_list: src",
          detail: "Listed 2 files",
          durationLabel: "3s",
          status: "completed",
          timestamp: 10_000,
          supported: true,
        },
      ],
    },
  ]);

  assert.equal(summary.label, "3s作業しました");
  assert.equal(summary.itemCount, 1);
  assert.equal(summary.runningCount, 0);
  assert.equal(summary.failedCount, 0);
});

test("running tool activity summary remains openable as active work", () => {
  const groups = [
    {
      id: "browser",
      label: "ブラウザ",
      items: [
        {
          id: "item-1",
          toolName: "browser_use",
          folder: "browser",
          folderLabel: "ブラウザ",
          input: "東京 今日の天気",
          title: "ブラウザ / browser_use: 東京 今日の天気",
          detail: "使用中",
          durationLabel: "7s",
          status: "running" as const,
          timestamp: 10_000,
          supported: true,
        },
      ],
    },
  ];

  assert.equal(hasRunningToolActivityGroups(groups), true);
  assert.equal(summarizeToolActivityGroups(groups).label, "7s作業中");
});

test("empty response warning waits until streaming draft is finalized", () => {
  const streaming = message({ metadata: { thinkingLabel: "streaming" } });
  const running = message({ metadata: { thinkingLabel: "running" } });

  assert.equal(shouldShowEmptyResponseWarning(streaming, false), false);
  assert.equal(shouldShowEmptyResponseWarning(running, false), false);
});

test("empty response warning only appears for finalized agent messages without activity", () => {
  const emptyCompleted = message({ metadata: { thinkingLabel: "completed" } });
  const textCompleted = message({ rawText: "done", metadata: { thinkingLabel: "completed" } });

  assert.equal(shouldShowEmptyResponseWarning(emptyCompleted, false), true);
  assert.equal(shouldShowEmptyResponseWarning(textCompleted, false), false);
  assert.equal(shouldShowEmptyResponseWarning(emptyCompleted, true), false);
});

test("authority approval followup is hidden while waiting response remains passive", () => {
  assert.equal(AUTHORITY_FOLLOWUP_TEXT, "Internal authority resume.");
  assertNoRiskyAuthorityFollowupPhrases(AUTHORITY_FOLLOWUP_TEXT);

  const waiting = message({
    id: "authority-waiting",
    rawText: "モデル/API の使用許可が必要です。承認後に続行します。",
    content: [{ type: "text", text: "モデル/API の使用許可が必要です。承認後に続行します。" }],
    metadata: {
      pendingAuthorityApproval: {
        request_id: "approval-1",
        permission_id: "model.invoke",
      },
    },
  });
  const followup = message({
    id: "authority-followup",
    role: "user",
    rawText: AUTHORITY_FOLLOWUP_TEXT,
    content: [{ type: "text", text: AUTHORITY_FOLLOWUP_TEXT }],
    metadata: {
      authorityFollowup: {
        request_id: "approval-1",
        permission_id: "model.invoke",
        hidden: true,
      },
      chatDisplay: {
        hidden: true,
        reason: "authority_followup",
      },
    },
  });

  assert.equal(isAuthorityWaitingMessage(waiting), true);
  assert.equal(isHiddenAuthorityFollowupMessage(followup), true);
  assert.deepEqual(visibleChatMessages([waiting, followup]).map((item) => item.id), ["authority-waiting"]);
});

test("authority waiting message is not replaced by the settled assistant continuation", () => {
  assertNoRiskyAuthorityFollowupPhrases(AUTHORITY_FOLLOWUP_TEXT);

  const waiting = message({
    id: "authority-waiting",
    rawText: "モデル/API の使用許可が必要です。承認後に続行します。",
    content: [{ type: "text", text: "モデル/API の使用許可が必要です。承認後に続行します。" }],
    metadata: {
      pendingAuthorityApproval: {
        request_id: "approval-1",
        permission_id: "model.invoke",
      },
    },
  });
  const followup = message({
    id: "authority-followup",
    role: "user",
    rawText: AUTHORITY_FOLLOWUP_TEXT,
    content: [{ type: "text", text: AUTHORITY_FOLLOWUP_TEXT }],
    metadata: {
      authorityFollowup: {
        request_id: "approval-1",
        permission_id: "model.invoke",
        hidden: true,
      },
      chatDisplay: {
        hidden: true,
        reason: "authority_followup",
      },
    },
  });
  const continuation = message({
    id: "authority-continuation",
    rawText: "Hello! How can I assist you today?",
    content: [{ type: "text", text: "Hello! How can I assist you today?" }],
    metadata: { thinkingLabel: "completed" },
  });

  assert.deepEqual(visibleChatMessages([waiting, followup, continuation]).map((item) => item.id), ["authority-waiting", "authority-continuation"]);
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
