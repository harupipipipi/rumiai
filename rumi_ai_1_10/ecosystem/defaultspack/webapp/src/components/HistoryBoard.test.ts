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
