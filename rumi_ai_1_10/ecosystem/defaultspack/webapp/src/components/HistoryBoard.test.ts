import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCalendarMonthDays,
  buildCompactHistoryRailItems,
  buildGroupsFromChats,
  buildHistoryCalendarSummary,
  loadCustomGroups,
  type ChatItem,
  type CustomGroupInfo,
} from "./HistoryBoard";
import { droppedWidgetFromHistoryChat, historyChatDragPayload, parseHistoryChatDrop } from "../lib/historyComposer";

test("buildGroupsFromChats places LINE conversations into a dedicated group", () => {
  const chats: ChatItem[] = [
    {
      id: "line-1",
      title: "LINE Cgroup",
      date: "Today",
      type: "chat",
      sectionId: "integration-line",
      sectionTitle: "LINE",
    },
    {
      id: "chat-1",
      title: "hello",
      date: "Today",
      type: "chat",
    },
  ];

  const groups = buildGroupsFromChats(chats);

  assert.equal(groups[0]?.title, "LINE");
  assert.deepEqual(groups[0]?.chats.map((chat) => chat.id), ["line-1"]);
  assert.equal(groups[1]?.title, "Today");
  assert.deepEqual(groups[1]?.chats.map((chat) => chat.id), ["chat-1"]);
});

test("buildGroupsFromChats groups metadata chats in compact workspace buckets", () => {
  const chats: ChatItem[] = [
    {
      id: "pinned-1",
      title: "Critical handoff",
      date: "Today",
      type: "chat",
      isPinned: true,
    },
    {
      id: "company-1",
      title: "Operations company",
      date: "Today",
      type: "chat",
      conversationKind: "operations_company",
      tags: ["operations-company"],
      metadata: { company_id: "operations-company" },
    },
    {
      id: "company-2",
      title: "MiMo company",
      date: "Today",
      type: "chat",
      conversationKind: "mimo_coding_company",
      tags: ["mimo-coding-company"],
      metadata: { company_id: "mimo-coding-company" },
    },
    {
      id: "coding-1",
      title: "Fix renderer",
      date: "Today",
      type: "chat",
      tags: ["coding"],
      metadata: { workspace_id: "ws1", mode: "coding" },
    },
    {
      id: "tagged-1",
      title: "Design note",
      date: "Today",
      type: "chat",
      tags: ["design"],
    },
    {
      id: "plain-1",
      title: "hello",
      date: "Today",
      type: "chat",
    },
  ];

  const groups = buildGroupsFromChats(chats);

  assert.deepEqual(groups.map((group) => group.title), ["Pinned", "Team", "Coding", "Tags", "Recent"]);
  assert.deepEqual(groups[0]?.chats.map((chat) => chat.id), ["pinned-1"]);
  assert.deepEqual(groups[1]?.chats.map((chat) => chat.id), ["company-1", "company-2"]);
  assert.deepEqual(groups[2]?.chats.map((chat) => chat.id), ["coding-1"]);
  assert.equal(groups[3]?.subGroups[0]?.title, "#design");
  assert.deepEqual(groups[3]?.subGroups[0]?.chats.map((chat) => chat.id), ["tagged-1"]);
  assert.deepEqual(groups[4]?.chats.map((chat) => chat.id), ["plain-1"]);
});

test("buildGroupsFromChats keeps custom group workspace metadata and matching chats", () => {
  const chats: ChatItem[] = [
    {
      id: "group-chat",
      title: "Group coding task",
      date: "Today",
      type: "chat",
      metadata: { group_id: "group-1", workspace_id: "ws-main", mode: "coding" },
    },
    {
      id: "plain-chat",
      title: "Plain task",
      date: "Today",
      type: "chat",
    },
  ];
  const customGroups: CustomGroupInfo[] = [{
    id: "group-1",
    title: "Main Repo",
    workspaceId: "ws-main",
    workspaceLabel: "Main",
    workspaceRoot: "/repo/main",
    rumiDataPath: "/repo/main/.rumiDP",
  }];

  const groups = buildGroupsFromChats(chats, customGroups);

  assert.equal(groups[0]?.id, "group-1");
  assert.equal(groups[0]?.workspaceId, "ws-main");
  assert.equal(groups[0]?.workspaceLabel, "Main");
  assert.equal(groups[0]?.workspaceRoot, "/repo/main");
  assert.equal(groups[0]?.rumiDataPath, "/repo/main/.rumiDP");
  assert.deepEqual(groups[0]?.chats.map((chat) => chat.id), ["group-chat"]);
  assert.equal(groups.find((group) => group.title === "Recent")?.chats[0]?.id, "plain-chat");
});

test("loadCustomGroups migrates legacy and snake_case workspace records", () => {
  const previousDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  values.set("rumi-history-custom-groups", JSON.stringify([
    { id: "legacy", title: "Legacy" },
    { id: "snake", title: "Snake", workspace_id: "ws1", workspace_label: "Repo", workspace_root: "/repo", rumi_data_path: "/repo/.rumiDP" },
    { id: "", title: "ignored" },
  ]));
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    },
  });

  try {
    assert.deepEqual(loadCustomGroups(), [
      { id: "legacy", title: "Legacy", workspaceId: null, workspaceLabel: null, workspaceRoot: null, rumiDataPath: null },
      { id: "snake", title: "Snake", workspaceId: "ws1", workspaceLabel: "Repo", workspaceRoot: "/repo", rumiDataPath: "/repo/.rumiDP" },
    ]);
  } finally {
    if (previousDescriptor) {
      Object.defineProperty(globalThis, "localStorage", previousDescriptor);
    } else {
      Reflect.deleteProperty(globalThis, "localStorage");
    }
  }
});

test("history calendar summary counts visible chat buckets and highlights", () => {
  const chats: ChatItem[] = [
    { id: "today", title: "Today", date: "Today", type: "chat", isPinned: true },
    { id: "recent", title: "Recent", date: "Previous 7 Days", type: "chat", isStarred: true },
    { id: "old", title: "Older", date: "2026-04-01", type: "chat" },
  ];

  assert.deepEqual(buildHistoryCalendarSummary(chats), {
    total: 3,
    today: 1,
    recent: 1,
    older: 1,
    pinned: 1,
    starred: 1,
  });

  const cells = buildCalendarMonthDays(new Date(2026, 4, 19));
  assert.equal(cells.filter(Boolean).length, 31);
  assert.equal(cells.find((cell) => cell?.day === 1)?.day, 1);
});

test("compact history rail keeps group entries and respects collapsed groups", () => {
  const groups = buildGroupsFromChats([
    { id: "chat-1", title: "Pinned task", date: "Today", type: "chat", isPinned: true },
    { id: "chat-2", title: "Coding task", date: "Today", type: "chat", tags: ["coding"] },
  ]).map((group) => group.id === "group-coding" ? { ...group, isCollapsed: true } : group);

  const railItems = buildCompactHistoryRailItems(groups);

  assert.deepEqual(
    railItems.map((item) => `${item.type}:${item.id}`),
    ["group:group-pinned", "chat:chat-1", "group:group-coding"],
  );
  assert.equal(railItems.find((item) => item.id === "group-coding")?.type, "group");
});

test("history chat drag payload becomes composer metadata widget", () => {
  const chat: ChatItem = {
    id: "conv-1",
    title: "Planning chat",
    date: "Today",
    type: "chat",
    conversationKind: "coding",
    tags: ["coding"],
  };
  const payload = historyChatDragPayload(chat);
  const widget = droppedWidgetFromHistoryChat(payload);
  const parsed = parseHistoryChatDrop(JSON.stringify(payload));

  assert.equal(widget.type, "conversation");
  assert.equal(widget.widgetKind, "history_context");
  assert.deepEqual(widget.metadata, {
    conversation_id: "conv-1",
    title: "Planning chat",
    conversation_kind: "coding",
    tags: ["coding"],
  });
  assert.deepEqual(parsed, widget);
});
