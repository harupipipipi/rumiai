import test from "node:test";
import assert from "node:assert/strict";

import {
  initialActiveWorkspaceTabIdForPathname,
  initialWorkspaceTabsForPathname,
  workspaceKindForPathname,
  workspaceUrlForKind,
} from "./workspaceRouting";
import { loadConversationForRefresh } from "./chatRouteLoading";

test("refresh conversation loading honors URL chat id missing from the conversation list", async () => {
  const loaded: Array<string | null> = [];

  await loadConversationForRefresh({
    preferredId: null,
    activeConversationId: null,
    locationChatId: "old-chat",
    listedConversations: [{ id: "recent-chat" }],
    loadConversation: async (conversationId) => {
      loaded.push(conversationId);
    },
  });

  assert.deepEqual(loaded, ["old-chat"]);
});

test("refresh conversation loading falls back when direct URL chat load fails", async () => {
  const loaded: Array<string | null> = [];

  await loadConversationForRefresh({
    preferredId: null,
    activeConversationId: null,
    locationChatId: "missing-chat",
    listedConversations: [{ id: "recent-chat" }],
    loadConversation: async (conversationId) => {
      loaded.push(conversationId);
      if (conversationId === "missing-chat") {
        throw new Error("HTTP 404");
      }
    },
  });

  assert.deepEqual(loaded, ["missing-chat", "recent-chat"]);
});

test("workspace routing opens desktops route as the desktops workspace", () => {
  const tabs = initialWorkspaceTabsForPathname("/desktops", 1234);

  assert.equal(workspaceKindForPathname("/desktops"), "desktops");
  assert.equal(initialActiveWorkspaceTabIdForPathname("/desktops"), "workspace-tab-route-desktops");
  assert.deepEqual(tabs.map((tab) => tab.kind), ["chat", "desktops"]);
  assert.equal(tabs[1].id, "workspace-tab-route-desktops");
});

test("workspace routing keeps desktops URL separate from chat conversations", () => {
  assert.equal(
    workspaceUrlForKind("desktops", "http://127.0.0.1:8766/chat?chat=abc&pending=1#panel", "abc"),
    "/desktops#panel",
  );
  assert.equal(
    workspaceUrlForKind("chat", "http://127.0.0.1:8766/desktops#panel", "abc"),
    "/chat?chat=abc#panel",
  );
});
