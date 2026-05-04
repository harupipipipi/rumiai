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

test("classifies common tool families", () => {
  assert.equal(toolFolderFor("browser_computer").id, "browser");
  assert.equal(toolFolderFor("todo").id, "planning/todo");
  assert.equal(toolFolderFor("subagent").id, "agent/subagent");
  assert.equal(toolFolderFor("coding_terminal_exec").id, "coding/terminal");
  assert.equal(toolFolderFor("git_status").id, "coding/git");
});
