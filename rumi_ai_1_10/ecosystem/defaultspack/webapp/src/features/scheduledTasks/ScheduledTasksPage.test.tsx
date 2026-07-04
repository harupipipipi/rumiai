import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ScheduledTasksPage } from "./ScheduledTasksPage";
import {
  confirmCloseScheduledTaskEditor,
  draftFromScheduledTask,
  filterScheduledTasks,
  normalizeScheduledTask,
  saveScheduledTaskEdit,
  setScheduledTaskEnabled,
  type ScheduledTasksApiClient,
} from "./scheduledTaskModels";

function record(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "sched-pr364",
    name: "PR364 CI follow-up",
    type: "interval",
    config: { value: 30, unit: "minutes" },
    status: "active",
    next_execution_at: "2026-07-04T12:00:00Z",
    task: {
      message: "Check PR364 CI and summarize failures",
      conversation_id: "conv-pr364",
      metadata: { context_name: "ハートビート・PR364 Cloud" },
    },
    ...overrides,
  };
}

function client(methods: Partial<ScheduledTasksApiClient>): ScheduledTasksApiClient {
  return {
    updateSchedule: async () => { throw new Error("unexpected update"); },
    pauseSchedule: async () => { throw new Error("unexpected pause"); },
    resumeSchedule: async () => { throw new Error("unexpected resume"); },
    deleteSchedule: async () => { throw new Error("unexpected delete"); },
    ...methods,
  };
}

test("ScheduledTasksPage renders the dedicated list surface", () => {
  const tasks = [
    normalizeScheduledTask(record()),
    normalizeScheduledTask(record({
      id: "sched-weekly",
      name: "Rumi defaultspack Pro/max QA follow-up",
      type: "cron",
      config: { expression: "53 2 * * 1" },
      status: "paused",
      task: { message: "Run QA follow-up", metadata: { context_name: "QA monitor" } },
    }), 1),
  ];

  const html = renderToStaticMarkup(createElement(ScheduledTasksPage, {
    autoLoad: false,
    initialTasks: tasks,
  }));

  assert.match(html, /予定済み/);
  assert.match(html, /定期的なタスク、リマインダー、モニターを管理/);
  assert.match(html, /placeholder="予定済みタスクを検索"/);
  assert.match(html, />現在</);
  assert.match(html, /PR364 CI follow-up/);
  assert.match(html, /ハートビート・PR364 Cloud/);
  assert.match(html, /30分ごと/);
  assert.match(html, /Rumi defaultspack Pro\/max QA follow-up/);
  assert.match(html, /毎週 2:53/);
  assert.match(html, />ON</);
  assert.match(html, />OFF</);
});

test("ScheduledTasksPage renders an error state", () => {
  const html = renderToStaticMarkup(createElement(ScheduledTasksPage, {
    autoLoad: false,
    initialError: "保存に失敗しました。",
  }));

  assert.match(html, /role="alert"/);
  assert.match(html, /保存に失敗しました。/);
});

test("scheduled task search matches task name, context, and prompt", () => {
  const tasks = [
    normalizeScheduledTask(record()),
    normalizeScheduledTask(record({
      id: "sched-soon",
      name: "Rumi soon Pro/CI monitor",
      type: "interval",
      config: { value: 10, unit: "minutes" },
      task: { message: "Watch release smoke status", metadata: { context_name: "Release room" } },
    }), 1),
  ];

  assert.deepEqual(filterScheduledTasks(tasks, "PR364").map((task) => task.id), ["sched-pr364"]);
  assert.deepEqual(filterScheduledTasks(tasks, "Release").map((task) => task.id), ["sched-soon"]);
  assert.deepEqual(filterScheduledTasks(tasks, "smoke").map((task) => task.id), ["sched-soon"]);
  assert.equal(filterScheduledTasks(tasks, "missing").length, 0);
});

test("setScheduledTaskEnabled stops and resumes through existing APIs", async () => {
  const active = normalizeScheduledTask(record());
  const calls: string[] = [];
  const paused = await setScheduledTaskEnabled(active, false, client({
    pauseSchedule: async (scheduleId) => {
      calls.push(`pause:${scheduleId}`);
      return { data: { ...record(), status: "paused", next_execution_at: null } };
    },
  }));

  assert.deepEqual(calls, ["pause:sched-pr364"]);
  assert.equal(paused.isEnabled, false);
  assert.equal(paused.nextRunLabel, "停止中");

  const resumed = await setScheduledTaskEnabled(paused, true, client({
    resumeSchedule: async (scheduleId) => {
      calls.push(`resume:${scheduleId}`);
      return { data: { ...record(), status: "active" } };
    },
  }));

  assert.equal(resumed.isEnabled, true);
  assert.deepEqual(calls, ["pause:sched-pr364", "resume:sched-pr364"]);
});

test("saveScheduledTaskEdit updates prompt, cadence, and OFF state immediately", async () => {
  const active = normalizeScheduledTask(record());
  const draft = {
    ...draftFromScheduledTask(active),
    name: "PR364 CI follow-up v2",
    prompt: "Check PR364 CI and include failed job links",
    intervalValue: "45",
    enabled: false,
  };
  const calls: string[] = [];

  const saved = await saveScheduledTaskEdit(active, draft, client({
    updateSchedule: async (scheduleId, payload) => {
      calls.push(`update:${scheduleId}`);
      assert.deepEqual(payload, {
        name: "PR364 CI follow-up v2",
        schedule_type: "interval",
        schedule_config: { value: 45, unit: "minutes" },
        task: { message: "Check PR364 CI and include failed job links" },
      });
      return {
        data: {
          ...record(),
          name: "PR364 CI follow-up v2",
          config: { value: 45, unit: "minutes" },
          task: { message: "Check PR364 CI and include failed job links", metadata: { context_name: "ハートビート・PR364 Cloud" } },
        },
      };
    },
    pauseSchedule: async (scheduleId) => {
      calls.push(`pause:${scheduleId}`);
      return {
        data: {
          ...record(),
          name: "PR364 CI follow-up v2",
          status: "paused",
          next_execution_at: null,
          config: { value: 45, unit: "minutes" },
          task: { message: "Check PR364 CI and include failed job links", metadata: { context_name: "ハートビート・PR364 Cloud" } },
        },
      };
    },
  }));

  assert.deepEqual(calls, ["update:sched-pr364", "pause:sched-pr364"]);
  assert.equal(saved.name, "PR364 CI follow-up v2");
  assert.equal(saved.prompt, "Check PR364 CI and include failed job links");
  assert.equal(saved.cadenceLabel, "45分ごと");
  assert.equal(saved.isEnabled, false);
});

test("saveScheduledTaskEdit exposes backend failures", async () => {
  const active = normalizeScheduledTask(record());
  await assert.rejects(
    saveScheduledTaskEdit(active, draftFromScheduledTask(active), client({
      updateSchedule: async () => { throw new Error("backend refused update"); },
    })),
    /backend refused update/,
  );
});

test("unsaved editor close asks for confirmation", () => {
  let prompt = "";

  assert.equal(confirmCloseScheduledTaskEditor(false, () => false), true);
  assert.equal(confirmCloseScheduledTaskEditor(true, (message) => {
    prompt = message;
    return false;
  }), false);
  assert.match(prompt, /未保存の変更/);
});
