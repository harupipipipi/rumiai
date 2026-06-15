import test from "node:test";
import assert from "node:assert/strict";

import {
  createChangeRequest,
  listChangeRequests,
  refreshChangeRequest,
} from "./changeRequests";

test("listChangeRequests uses canonical endpoint and normalizes backend snapshots", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestCache: RequestCache | undefined;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestCache = init?.cache;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        change_requests: [
          {
            id: "cr_1",
            status: "open",
            title: "Review workspace",
            latest_snapshot: {
              working_tree_hash: "sha256:abc",
              normalized_patch: "diff --git a/notes.md b/notes.md\nnew file mode 100644\n--- /dev/null\n+++ b/notes.md\n@@\n+hello\n",
              file_stats: [
                { path: "notes.md", status: "untracked", additions: 1, deletions: 0 },
                { path: "src/app.ts", status: "modified", additions: 2, deletions: 1 },
              ],
            },
          },
          { id: "cr_2", status: "closed" },
        ],
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await listChangeRequests({ workspace_id: "ws_1" });
    assert.equal(requestUrl, "/api/change-requests?workspace_id=ws_1");
    assert.equal(requestCache, "no-store");
    assert.equal(result.apiAvailable, true);
    assert.deepEqual(result.open.map((review) => review.id), ["cr_1"]);
    assert.deepEqual(result.closed.map((review) => review.id), ["cr_2"]);
    assert.deepEqual(result.reviews[0]?.files?.map((file) => [file.path, file.status]), [
      ["notes.md", "untracked"],
      ["src/app.ts", "modified"],
    ]);
    assert.equal(result.reviews[0]?.snapshot?.signature, "sha256:abc");
    assert.match(result.reviews[0]?.snapshot?.diff ?? "", /new file mode 100644/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("create and refresh change requests use read-only canonical routes", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; method?: string; body?: unknown }> = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        change_request: {
          id: calls.length === 1 ? "cr_create" : "cr_refresh",
          status: "open",
        },
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const created = await createChangeRequest({ workspace_id: "ws_1" });
    const refreshed = await refreshChangeRequest("cr create", { workspace_id: "ws_1" });

    assert.equal(created?.id, "cr_create");
    assert.equal(refreshed?.id, "cr_refresh");
    assert.deepEqual(calls, [
      {
        url: "/api/change-requests",
        method: "POST",
        body: { domain: "change_request", source: "working_tree", workspace_id: "ws_1" },
      },
      {
        url: "/api/change-requests/cr%20create/refresh",
        method: "POST",
        body: { workspace_id: "ws_1" },
      },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
