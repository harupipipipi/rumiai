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

test("sendMessage preserves an empty selected tools filter", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m-empty-tools",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.sendMessage("c1", "hello", {
      tools: [],
      tool_policy: { selected_tools: [] },
      metadata: { selected_tools: [] },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody?.tools, []);
  assert.deepEqual(requestBody?.params?.tool_policy, { selected_tools: [] });
  assert.deepEqual(requestBody?.message?.metadata, { selected_tools: [] });
});

test("saveProviderApiKey serializes named API metadata", async () => {
  let requestBody: any = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body ?? "{}"));
    return new Response(JSON.stringify({
      status: "ok",
      data: { provider_id: "google", configured: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.saveProviderApiKey("google", "secret", { apiId: "main", name: "Main" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody, {
    provider_id: "google",
    value: "secret",
    api_id: "main",
    name: "Main",
  });
});

test("streamMessage parses SSE deltas and final message", async () => {
  const originalFetch = globalThis.fetch;
  const events: string[] = [];
  let finalId = "";
  globalThis.fetch = (async () => {
    const body = [
      'data: {"type":"delta","delta":"he"}\n\n',
      'data: {"type":"delta","delta":"llo"}\n\n',
      'data: {"type":"message","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"hello"}],"created_at":1,"conversation_id":"c1"}}\n\n',
      'data: {"type":"done","message":{"id":"m2","role":"assistant","content":[{"type":"text","text":"hello"}],"created_at":1,"conversation_id":"c1"}}\n\n',
    ].join("");
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    });
  }) as typeof fetch;

  try {
    const final = await api.streamMessage("c1", "hello", undefined, {
      onDelta(delta) {
        events.push(delta);
      },
      onMessage(message) {
        finalId = message.id;
      },
    });
    assert.equal(final?.id, "m2");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(events, ["he", "llo"]);
  assert.equal(finalId, "m2");
});

test("streamMessage forwards abort signal to fetch", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let seenSignal: AbortSignal | undefined;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    seenSignal = init?.signal ?? undefined;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        id: "m3",
        role: "assistant",
        content: "ok",
        created_at: 1,
        conversation_id: "c1",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.streamMessage("c1", "hello", undefined, { signal: controller.signal });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seenSignal, controller.signal);
});

test("coding context, branch, and workspace read helpers use existing API routes", async () => {
  const seen: Array<{ input: string; body?: unknown }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push({ input: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify({
      status: "ok",
      data: String(input).includes("/api/coding/context")
        ? { branch: "main", root_folder: "/repo", directory: "src", files: [], entries: [], git: null }
        : String(input).includes("/api/coding/files/read")
          ? { path: "README.md", content: "hello", size: 5, encoding: "utf-8" }
          : { branch: "feature", branches: ["main", "feature"], switched: true, created: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    await api.getCodingContext({ directory: "src" });
    await api.switchGitBranch("feature", true);
    await api.readWorkspaceFile("README.md");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen[0].input, "/api/coding/context?directory=src");
  assert.deepEqual(seen[1], {
    input: "/api/coding/git/branch",
    body: { action: "switch", branch: "feature", create: true },
  });
  assert.deepEqual(seen[2], {
    input: "/api/coding/files/read",
    body: { path: "README.md" },
  });
});
