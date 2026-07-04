import test from "node:test";
import assert from "node:assert/strict";

import {
  initialActiveWorkspaceTabIdForPathname,
  initialWorkspaceTabsForPathname,
  workspaceKindForPathname,
  workspaceUrlForKind,
} from "./workspaceRouting";
import { loadConversationForRefresh, resolveSupersededConversationRedirect } from "./chatRouteLoading";

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

test("refresh conversation loading prefers an explicit URL chat over existing active state", async () => {
  const loaded: Array<string | null> = [];

  await loadConversationForRefresh({
    preferredId: null,
    activeConversationId: "active-chat",
    locationChatId: "url-chat",
    listedConversations: [{ id: "active-chat" }, { id: "url-chat" }],
    loadConversation: async (conversationId) => {
      loaded.push(conversationId);
    },
  });

  assert.deepEqual(loaded, ["url-chat"]);
});

test("superseded conversations redirect to active MiMo company conversation", () => {
  assert.equal(
    resolveSupersededConversationRedirect(
      {
        id: "stale-chat",
        metadata: {
          superseded: true,
          active_conversation_id: "live-chat",
        },
      },
      "stale-chat",
    ),
    "live-chat",
  );

  assert.equal(
    resolveSupersededConversationRedirect(
      {
        id: "live-chat",
        metadata: {
          superseded: true,
          active_conversation_id: "live-chat",
        },
      },
      "live-chat",
    ),
    null,
  );
});

test("workspace routing opens desktops route as the desktops workspace", () => {
  const tabs = initialWorkspaceTabsForPathname("/desktops", 1234);

  assert.equal(workspaceKindForPathname("/desktops"), "desktops");
  assert.equal(initialActiveWorkspaceTabIdForPathname("/desktops"), "workspace-tab-route-desktops");
  assert.deepEqual(tabs.map((tab) => tab.kind), ["chat", "desktops"]);
  assert.equal(tabs[1].id, "workspace-tab-route-desktops");
});

test("workspace routing opens calendar route as the calendar workspace", () => {
  const tabs = initialWorkspaceTabsForPathname("/calendar", 1234);

  assert.equal(workspaceKindForPathname("/calendar"), "calendar");
  assert.equal(initialActiveWorkspaceTabIdForPathname("/calendar"), "workspace-tab-route-calendar");
  assert.deepEqual(tabs.map((tab) => tab.kind), ["chat", "calendar"]);
  assert.equal(tabs[1].id, "workspace-tab-route-calendar");
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

test("workspace routing keeps calendar URL separate from stale chat conversations", () => {
  assert.equal(
    workspaceUrlForKind("calendar", "http://127.0.0.1:8766/chat?chat=abc&pending=1#panel", "abc"),
    "/calendar#panel",
  );
  assert.equal(
    workspaceUrlForKind("chat", "http://127.0.0.1:8766/calendar#panel", "abc"),
    "/chat?chat=abc#panel",
  );
});
