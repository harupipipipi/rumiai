import test from "node:test";
import assert from "node:assert/strict";

import {
  loadConversationForRefresh,
  replaceChatIdInUrl,
  resolveSupersededConversationRedirect,
} from "./chatRouteLoading";

function fakeRouteWindow(href: string) {
  const calls: Array<{ mode: "push" | "replace"; state: unknown; url: string }> = [];
  const location = new URL(href);
  const setLocation = (next: string | URL | null | undefined) => {
    if (!next) return;
    const url = new URL(String(next), location.origin);
    location.pathname = url.pathname;
    location.search = url.search;
    location.hash = url.hash;
    location.href = url.href;
  };
  return {
    calls,
    targetWindow: {
      location,
      history: {
        pushState: (state: unknown, _title: string, url?: string | URL | null) => {
          calls.push({ mode: "push", state, url: String(url ?? "") });
          setLocation(url);
        },
        replaceState: (state: unknown, _title: string, url?: string | URL | null) => {
          calls.push({ mode: "replace", state, url: String(url ?? "") });
          setLocation(url);
        },
      },
    },
  };
}

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
        id: "old-chat",
        metadata: {
          stale: true,
          replacement_conversation_id: "active-chat",
        },
      },
      "old-chat",
    ),
    "active-chat",
  );

  assert.equal(
    resolveSupersededConversationRedirect(
      {
        id: "active-chat",
        metadata: {
          superseded: true,
          active_conversation_id: "active-chat",
        },
      },
      "active-chat",
    ),
    null,
  );
});

test("chat URL replacement can normalize stale chat history with replaceState", () => {
  const fake = fakeRouteWindow("http://127.0.0.1:18766/chat?chat=old-chat&pending=1#panel=main");

  replaceChatIdInUrl("active-chat", false, {
    historyMode: "replace",
    targetWindow: fake.targetWindow,
  });

  assert.deepEqual(fake.calls, [{
    mode: "replace",
    state: { conversationId: "active-chat" },
    url: "/chat?chat=active-chat#panel=main",
  }]);
  assert.equal(fake.targetWindow.location.pathname, "/chat");
  assert.equal(fake.targetWindow.location.search, "?chat=active-chat");
  assert.equal(fake.targetWindow.location.hash, "#panel=main");
});

test("normal chat URL updates still use pushState and preserve pending when unspecified", () => {
  const fake = fakeRouteWindow("http://127.0.0.1:18766/chat?chat=old-chat&pending=1");

  replaceChatIdInUrl("new-chat", undefined, { targetWindow: fake.targetWindow });

  assert.deepEqual(fake.calls, [{
    mode: "push",
    state: { conversationId: "new-chat" },
    url: "/chat?chat=new-chat&pending=1",
  }]);
});
