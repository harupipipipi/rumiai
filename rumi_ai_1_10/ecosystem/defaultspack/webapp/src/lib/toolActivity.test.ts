import test from "node:test";
import assert from "node:assert/strict";

import { buildToolActivityGroups, summarizeToolArguments, toolFolderFor } from "./toolActivity";

test("formats calculator arguments as a compact activity title", () => {
  assert.equal(summarizeToolArguments("calculator", { expression: "13829+12312" }), "13829+12312");
  assert.equal(summarizeToolArguments("calculator", { a: 13829, operation: "+", b: 12312 }), "13829 + 12312");
});

test("groups real tool logs into folder-like sections", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "calculator",
      arguments: { expression: "13829+12312" },
      result: { status: "ok", data: { result: 26141 } },
    },
    {
      tool_name: "web_search",
      arguments: { query: "今日の天気 東京" },
      result: { status: "ok", data: { results: [{ title: "weather" }] } },
    },
  ]);

  assert.equal(groups.length, 2);
  assert.equal(groups[0].id, "calculation");
  assert.equal(groups[0].items[0].title, "計算: 13829+12312");
  assert.equal(groups[0].items[0].detail, "26141");
  assert.equal(groups[1].id, "web/search");
  assert.equal(groups[1].items[0].title, "Webで検索: 今日の天気 東京");
});

test("polishes calculator result prose into the answer", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "calculator",
      arguments: { expression: "13829+12312" },
      result: { status: "ok", data: { output: "Calculated: 13829+12312 = 26141" } },
    },
  ]);

  assert.equal(groups[0].items[0].detail, "26141");
});

test("does not create activity from text-only claims", () => {
  assert.deepEqual(buildToolActivityGroups([], []), []);
});

test("uses running tool_call events when a log has not arrived yet", () => {
  const groups = buildToolActivityGroups([], [
    {
      type: "tool_call",
      phase: "tool_call",
      tool_name: "coding_file_list",
      arguments: { path: "src" },
      message: "coding_file_list を使用中",
    },
  ]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].id, "coding/files");
  assert.equal(groups[0].items[0].status, "running");
  assert.equal(groups[0].items[0].title, "ファイル一覧を確認: src");
});

test("summarizes terminal commands as user-facing activity", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "coding_terminal_exec",
      arguments: { command: "gh repo view --json defaultBranchRef" },
      result: { status: "ok", data: { exit_code: 0, stdout: "{\"defaultBranchRef\":{\"name\":\"main\"}}" } },
    },
  ]);

  const item = groups[0].items[0];
  assert.equal(item.title, "GitHub 情報を確認");
  assert.equal(item.detail, "終了コード 0");
  assert.equal(item.input, "gh repo view --json defaultBranchRef");
});

test("surfaces file edits without exposing the whole diff as the main activity", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "coding_file_patch",
      arguments: { path: "src/App.tsx", old: "before", new: "after" },
      result: { status: "ok", data: { path: "src/App.tsx", patched: true, diff: "-before\n+after\n" } },
    },
  ]);

  const item = groups[0].items[0];
  assert.equal(item.title, "ファイルを編集: App.tsx");
  assert.equal(item.detail, "変更しました: App.tsx");
});

test("updates streamed tool activity when a completion event arrives before the log", () => {
  const groups = buildToolActivityGroups([], [
    {
      type: "tool_call_started",
      phase: "tool_call_started",
      tool_call_id: "call_1",
      tool_name: "computer_use",
      arguments: { action: "click", app: "Notion", x: 120, y: 340 },
      message: "computer_use を使用中",
      timestamp: 1_700_000_000_000,
    },
    {
      type: "tool_call_completed",
      phase: "tool_call_completed",
      tool_call_id: "call_1",
      tool_name: "computer_use",
      arguments: { action: "click", app: "Notion", x: 120, y: 340 },
      message: "computer_use の結果を受け取りました",
      is_error: false,
      timestamp: 1_700_000_003_200,
    },
  ]);

  assert.equal(groups.length, 1);
  assert.equal(groups[0].items[0].status, "completed");
  assert.equal(groups[0].items[0].input, "click Notion (120, 340)");
  assert.equal(groups[0].items[0].durationLabel, "3s");
});

test("shows live elapsed time for running streamed tool activity", () => {
  const groups = buildToolActivityGroups([], [
    {
      type: "tool_call_started",
      phase: "tool_call_started",
      tool_call_id: "call_1",
      tool_name: "coding_file_list",
      arguments: { path: "src" },
      timestamp: 1_700_000_010_000,
    },
  ], { now: 1_700_000_072_000 });

  assert.equal(groups[0].items[0].status, "running");
  assert.equal(groups[0].items[0].durationLabel, "1m 2s");
});

test("uses streamed completion results and artifacts before final logs arrive", () => {
  const groups = buildToolActivityGroups([], [
    {
      type: "tool_call_started",
      phase: "tool_call_started",
      tool_call_id: "call_1",
      tool_name: "browser_computer",
      arguments: { action: "computer.screenshot" },
      message: "browser_computer を使用中",
    },
    {
      type: "tool_call_completed",
      phase: "tool_call_completed",
      tool_call_id: "call_1",
      tool_name: "browser_computer",
      result: {
        status: "ok",
        data: {
          summary: "Captured screen",
          widget: {
            data_url: "data:image/png;base64,aW1hZ2U=",
            screenshot_path: "/tmp/rumi/workspace/tools/browser/screen.png",
          },
        },
      },
      message: "browser_computer の結果を受け取りました",
    },
  ], { conversationId: "conv_1" });

  const item = groups[0].items[0];
  assert.equal(item.status, "completed");
  assert.equal(item.input, "computer.screenshot");
  assert.equal(item.detail, "Captured screen");
  assert.equal(item.artifacts?.some((artifact) => artifact.url?.startsWith("data:image/png")), true);
  assert.equal(item.artifacts?.some((artifact) => artifact.path.endsWith("screen.png")), true);
});

test("uses streamed display text and next step for realtime tool narration", () => {
  const groups = buildToolActivityGroups([], [
    {
      type: "tool_call_completed",
      phase: "tool_call_completed",
      tool_call_id: "call_1",
      tool_name: "browser_computer",
      arguments: { action: "computer.click" },
      display_text: "クリックしました。結果を確認しています。",
      next_step: "画面の変化をもとに次へ進みます。",
      status: "completed",
    },
  ]);

  assert.equal(groups[0].items[0].detail, "クリックしました。結果を確認しています。");
  assert.equal(groups[0].items[0].nextStep, "画面の変化をもとに次へ進みます。");
});

test("hides generic completion text for completed tool activity", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "context" },
      result: { status: "ok", data: { result: "computer_use computer.context completed; artifact: /tmp/screenshot.png" } },
    },
  ]);

  assert.equal(groups[0].items[0].status, "completed");
  assert.equal(groups[0].items[0].detail, "");
  assert.equal(groups[0].items[0].input, "context");
});

test("keeps raw json for unsupported tools", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "mystery_plugin",
      arguments: { value: "abc" },
      result: { status: "ok", data: { answer: 42 } },
    },
  ]);

  const item = groups[0].items[0];
  assert.equal(item.supported, false);
  assert.match(item.rawJson ?? "", /mystery_plugin|answer|value/);
});

test("dedupes started events when a matching completed log exists", () => {
  const groups = buildToolActivityGroups(
    [
      {
        tool_name: "coding_file_list",
        tool_call_id: "call_1",
        arguments: { path: "src" },
        result: { status: "ok", data: { files: ["a.ts"] } },
      },
    ],
    [
      {
        type: "tool_call_started",
        phase: "tool_call_started",
        tool_call_id: "call_1",
        tool_name: "coding_file_list",
        arguments: { path: "src" },
        message: "coding_file_list を使用中",
      },
    ],
  );

  assert.equal(groups.length, 1);
  assert.equal(groups[0].items.length, 1);
  assert.equal(groups[0].items[0].status, "completed");
});

test("marks nested tool errors as failed activity", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "type", text: "hello" },
      result: {
        status: "ok",
        data: {
          result: "computer_use computer.type failed",
          is_error: true,
          widget: { is_error: true },
        },
      },
    },
  ]);

  assert.equal(groups[0].items[0].status, "failed");
});

test("attaches tool artifact files to the matching activity item", () => {
  const path = "/tmp/rumi/workspace/tools/computer/click-1.png";
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      tool_call_id: "call_1",
      arguments: { action: "click", x: 12, y: 34 },
      result: {
        status: "ok",
        data: {
          widget: {
            path,
            model_image_path: "/tmp/rumi/workspace/tools/computer/click-1-model.jpg",
          },
        },
      },
    },
  ], [], { conversationId: "conv_1" });

  const artifact = groups[0].items[0].artifacts?.[0];
  assert.equal(groups[0].items[0].toolCallId, "call_1");
  assert.equal(artifact?.kind, "image");
  assert.equal(artifact?.name, "click-1-model.jpg");
  assert.match(artifact?.url ?? "", /\/api\/chat\/conversations\/conv_1\/artifact-file/);
});

test("classifies common tool families", () => {
  assert.equal(toolFolderFor("browser_companion").id, "browser");
  assert.equal(toolFolderFor("browser_computer").id, "browser");
  assert.equal(toolFolderFor("todo").id, "planning/todo");
  assert.equal(toolFolderFor("subagent").id, "agent/delegation");
  assert.equal(toolFolderFor("coding_terminal_exec").id, "coding/terminal");
  assert.equal(toolFolderFor("git_status").id, "coding/git");
});
