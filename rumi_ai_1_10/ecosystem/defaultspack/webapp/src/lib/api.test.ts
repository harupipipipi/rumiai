import test from "node:test";
import assert from "node:assert/strict";
import { api } from "./api";

test("sendMessage serializes attachments and selected tools", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m1",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.sendMessage("c1", "hello", {
      thinking_level: "medium",
      attachments: [
        { name: "notes.txt", content: "body", size: 4, type: "text/plain" },
        { name: "photo.png", size: 1024, type: "image/png", truncated: false },
      ],
      tools: ["local_file"],
      tool_policy: { selected_tools: ["local_file"] },
      metadata: { selected_tools: ["local_file"] },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.message, {
    role: "user",
    content: "hello",
    attachments: [
      { name: "notes.txt", content: "body", size: 4, type: "text/plain" },
      { name: "photo.png", size: 1024, type: "image/png", truncated: false },
    ],
    metadata: { selected_tools: ["local_file"] },
  });
  assert.deepEqual(requestBody?.tools, ["local_file"]);
  assert.deepEqual(requestBody?.params, {
    thinking_level: "medium",
    tool_policy: { selected_tools: ["local_file"] },
  });
});

test("coding context and branch helpers use existing API routes", async () => {
  const seen: Array<{ input: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({ input: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/api/coding/context")
        ? { branch: "main", root_folder: "/repo", directory: "src", files: [], entries: [], git: null }
        : { branch: "feature", branches: ["main", "feature"], switched: true, created: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.getCodingContext({ directory: "src" });
    await api.switchGitBranch("feature", true);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen[0].input, "/api/coding/context?directory=src");
  assert.deepEqual(seen[1], {
    input: "/api/coding/git/branch",
    body: { action: "switch", branch: "feature", create: true },
  });
});
