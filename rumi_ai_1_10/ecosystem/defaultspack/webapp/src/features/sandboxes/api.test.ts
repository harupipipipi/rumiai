import test from "node:test";
import assert from "node:assert/strict";

import { sandboxesApi } from "./api";

function desktopResponse(status: "running" | "stopped") {
  return {
    seat_id: "seat-1",
    sandbox_id: "seat-1",
    name: "Ubuntu Desktop",
    status,
    provider_id: "fake-runtime",
    template_id: "desktop.ubuntu",
    resolution: { width: 800, height: 600 },
  };
}

test("stopDesktop confirms the destructive action after the UI confirmation flow", async () => {
  let requestUrl = "";
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: desktopResponse("stopped"),
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.stopDesktop("seat-1");
    assert.equal(result.status, "stopped");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/desktops/seat-1/stop");
  assert.equal(requestInit?.method, "POST");
  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.owner_id, "local-user");
  assert.equal(body.confirm_destructive, true);
  assert.match(body.request_id, /^desktop-stop-/);
});

test("deleteDesktop confirms the destructive action after the UI confirmation flow", async () => {
  let requestUrl = "";
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: { deleted: true, seat_id: "seat-1" },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.deleteDesktop("seat-1", "key-1");
    assert.deepEqual(result, { deleted: true, seat_id: "seat-1" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/desktops/seat-1");
  assert.equal(requestInit?.method, "DELETE");
  assert.equal(new Headers(requestInit?.headers).get("X-Rumi-Desktop-Access-Key"), "key-1");
  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.owner_id, "local-user");
  assert.equal(body.confirm_destructive, true);
  assert.match(body.request_id, /^desktop-delete-/);
});
