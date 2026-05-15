import test from "node:test";
import assert from "node:assert/strict";

import { buildGroupsFromChats, type ChatItem } from "./HistoryBoard";

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
