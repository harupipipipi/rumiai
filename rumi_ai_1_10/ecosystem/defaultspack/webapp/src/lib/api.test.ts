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
      attachments: [{ name: "notes.txt", content: "body", size: 4, type: "text/plain" }],
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
    attachments: [{ name: "notes.txt", content: "body", size: 4, type: "text/plain" }],
    metadata: { selected_tools: ["local_file"] },
  });
  assert.deepEqual(requestBody?.tools, ["local_file"]);
  assert.deepEqual(requestBody?.params, {
    thinking_level: "medium",
    tool_policy: { selected_tools: ["local_file"] },
  });
});
