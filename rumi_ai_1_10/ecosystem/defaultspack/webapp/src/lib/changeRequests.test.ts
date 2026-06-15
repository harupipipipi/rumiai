import test from "node:test";
import assert from "node:assert/strict";

import {
  createChangeRequest,
  getChangeRequest,
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
            file_stats: [
              { path: "notes.md", status: "untracked", additions: 1, deletions: 0 },
            ],
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

test("listChangeRequests normalizes persisted summaries without nested snapshots", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    status: "ok",
    data: {
      change_requests: [
        {
          id: "cr_summary",
          status: "open",
          working_tree_hash: "sha256:summary",
          normalized_patch: "diff --git a/app.ts b/app.ts\n--- a/app.ts\n+++ b/app.ts\n@@\n-old\n+new\n",
          file_stats: [
            { path: "app.ts", status: "modified", additions: 1, deletions: 1 },
          ],
        },
      ],
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  try {
    const result = await listChangeRequests();
    assert.deepEqual(result.reviews[0]?.files?.map((file) => [file.path, file.status]), [
      ["app.ts", "modified"],
    ]);
    assert.equal(result.reviews[0]?.snapshot?.signature, "sha256:summary");
    assert.match(result.reviews[0]?.snapshot?.diff ?? "", /diff --git/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("getChangeRequest hydrates detail records and drift state", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    requestUrl = String(input);
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "cr hydrate",
        status: "open",
        is_stale: true,
        latest_snapshot: {
          working_tree_hash: "sha256:snapshot",
          normalized_patch: "diff --git a/src/app.ts b/src/app.ts\n--- a/src/app.ts\n+++ b/src/app.ts\n@@\n-old\n+new\n",
          file_stats: [{ path: "src/app.ts", status: "modified", additions: 1, deletions: 1 }],
        },
        drift: {
          changed: true,
          previous_working_tree_hash: "sha256:snapshot",
          current_working_tree_hash: "sha256:current",
          changed_paths: ["src/app.ts"],
        },
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await getChangeRequest("cr hydrate");
    assert.equal(requestUrl, "/api/change-requests/cr%20hydrate");
    assert.equal(result?.is_stale, true);
    assert.equal(result?.drift?.current_working_tree_hash, "sha256:current");
    assert.deepEqual(result?.files?.map((file) => file.path), ["src/app.ts"]);
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
