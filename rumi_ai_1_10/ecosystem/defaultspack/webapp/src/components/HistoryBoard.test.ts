import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCalendarMonthDays,
  buildGroupsFromChats,
  buildHistoryCalendarSummary,
  type ChatItem,
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

  assert.deepEqual(groups.map((group) => group.title), ["Pinned", "Company", "Coding", "Tags", "Recent"]);
  assert.deepEqual(groups[0]?.chats.map((chat) => chat.id), ["pinned-1"]);
  assert.deepEqual(groups[1]?.chats.map((chat) => chat.id), ["company-1"]);
  assert.deepEqual(groups[2]?.chats.map((chat) => chat.id), ["coding-1"]);
  assert.equal(groups[3]?.subGroups[0]?.title, "#design");
  assert.deepEqual(groups[3]?.subGroups[0]?.chats.map((chat) => chat.id), ["tagged-1"]);
  assert.deepEqual(groups[4]?.chats.map((chat) => chat.id), ["plain-1"]);
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
