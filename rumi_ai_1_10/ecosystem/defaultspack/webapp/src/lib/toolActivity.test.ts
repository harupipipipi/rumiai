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
  assert.equal(groups[0].items[0].title, "計算 / calculator: 13829+12312");
  assert.equal(groups[0].items[0].detail, "26141");
  assert.equal(groups[1].id, "web/search");
  assert.equal(groups[1].items[0].title, "Web検索 / web_search: 今日の天気 東京");
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

test("summarizes computer screenshots without leaking giant absolute paths into the card", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "computer.screenshot" },
      result: {
        status: "ok",
        data: {
          action: "computer.screenshot",
          path: "/Users/haru/Desktop/puroguramukei/rumi_ai_mac/rumi_ai_1_10/ecosystem/defaultspack/user_data/shared/screenshot-177.png",
        },
      },
    },
  ]);

  assert.equal(groups[0].items[0].input, "スクリーンショット");
  assert.equal(groups[0].items[0].detail, "画面を取得 · screenshot-177.png");
});

test("summarizes computer clicks as useful compact activity", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "computer.click", x: 840, y: 620 },
      result: {
        status: "ok",
        data: {
          action: "computer.click",
          click_history_visual_path: "/Users/haru/Desktop/project/screenshot-clicks.png",
        },
      },
    },
  ]);

  assert.equal(groups[0].items[0].input, "クリック (840, 620)");
  assert.equal(groups[0].items[0].detail, "クリック位置を記録 · screenshot-clicks.png");
});

test("shows zoom failures instead of pretending they completed", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "zoom",
      arguments: { x: 0, y: 700, width: 1000, height: 300 },
      result: {
        status: "ok",
        data: {
          result: "zoom computer.zoom completed",
          widget: {
            type: "zoom",
            action: "computer.zoom",
            status: "error",
            error: { message: "zoom requires source_path" },
          },
        },
      },
    },
  ]);

  assert.equal(groups[0].items[0].input, "ズーム");
  assert.equal(groups[0].items[0].status, "failed");
  assert.equal(groups[0].items[0].detail, "失敗 · zoom requires source_path");
});

test("marks approval requests as pending instead of completed", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "click", x: 20, y: 30 },
      result: {
        status: "ok",
        data: {
          widget: {
            type: "computer_use",
            action: "computer.click",
            requires_approval: true,
            risk_reason: "state_changing_action",
          },
        },
      },
    },
  ]);

  assert.equal(groups[0].items[0].status, "approval");
  assert.equal(groups[0].items[0].detail, "承認待ち · state_changing_action");
});

test("uses central approval status for stale computer approval cards", () => {
  const groups = buildToolActivityGroups([
    {
      tool_name: "computer_use",
      arguments: { action: "click", x: 20, y: 30 },
      result: {
        status: "ok",
        data: {
          widget: {
            type: "computer_use",
            action: "computer.click",
            requires_approval: true,
            approval_id: "appr_1",
            risk_reason: "state_changing_action",
          },
        },
      },
    },
  ], [], { appr_1: "approved" });

  assert.equal(groups[0].items[0].status, "completed");
  assert.equal(groups[0].items[0].detail, "承認済み · 実行待ち");
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
  assert.equal(groups[0].items[0].title, "ファイル / coding_file_list: src");
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

test("classifies common tool families", () => {
  assert.equal(toolFolderFor("browser_computer").id, "browser");
  assert.equal(toolFolderFor("todo").id, "planning/todo");
  assert.equal(toolFolderFor("subagent").id, "agent/subagent");
  assert.equal(toolFolderFor("coding_terminal_exec").id, "coding/terminal");
  assert.equal(toolFolderFor("git_status").id, "coding/git");
});
