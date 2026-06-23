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

test("createDesktop sends owner-bound access policy for request-required desktops", async () => {
  let requestUrl = "";
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: desktopResponse("running"),
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.createDesktop({
      name: "Owner desktop",
      template_id: "desktop.ubuntu",
      resolution: { width: 1280, height: 800 },
      starter: "empty",
      workspace_access: "none",
      access: { mode: "request_required" },
    });
    assert.equal(result.status, "running");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/desktops");
  assert.equal(requestInit?.method, "POST");
  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.owner_id, "local-user");
  assert.equal(body.access.mode, "request_required");
  assert.equal(body.access.owner_id, "local-user");
  assert.match(body.request_id, /^desktop-create-/);
});

test("createDesktop preserves generated shared-link access token from backend", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    status: "ok",
    data: {
      ...desktopResponse("running"),
      access_key: "generated-link-token",
      access_key_hint: "ends:oken",
      access_policy: {
        mode: "shared_link",
        link_enabled: true,
        key_hint: "ends:oken",
      },
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  try {
    const result = await sandboxesApi.createDesktop({
      name: "Shared desktop",
      template_id: "desktop.ubuntu",
      resolution: { width: 1280, height: 800 },
      starter: "empty",
      workspace_access: "none",
      access: { mode: "shared_link" },
    });

    assert.equal(result.access_key, "generated-link-token");
    assert.equal(result.access_policy?.mode, "shared_link");
    assert.equal(result.access_policy?.link_enabled, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("requestDesktopAccess sends requester identity without claiming owner authority", async () => {
  let requestUrl = "";
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        seat_id: "seat-1",
        request_id: "dreq-1",
        requester_id: "local-user",
        reason: "Need access",
        status: "pending",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.requestDesktopAccess("seat-1", "Need access");
    assert.equal(result.status, "pending");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/desktops/seat-1/access-requests");
  assert.equal(requestInit?.method, "POST");
  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.requester_id, "local-user");
  assert.equal(body.owner_id, undefined);
  assert.equal(body.reason, "Need access");
  assert.match(body.request_id, /^desktop-access-/);
});

test("listDesktops normalizes unknown provisioning status to the explicit fallback", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    status: "ok",
    data: {
      desktops: [
        {
          ...desktopResponse("running"),
          provisioning: {
            apps: ["google-chrome-stable"],
            mcp_servers: ["playwright"],
            status: "provider-specific-status",
          },
        },
      ],
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  try {
    const result = await sandboxesApi.listDesktops();
    assert.equal(result.desktops[0].provisioning?.status, "unknown");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

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

test("grantDesktopAccess sends owner approval to the request grant endpoint", async () => {
  let requestUrl = "";
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requestUrl = String(input);
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        seat_id: "seat-1",
        request_id: "dreq-1",
        status: "approved",
        access_key: "secret-key",
        access_key_hint: "ends:-key",
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.grantDesktopAccess("seat-1", "dreq-1");
    assert.equal(result.access_key, "secret-key");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestUrl, "/api/desktops/seat-1/access-requests/dreq-1/grant");
  assert.equal(requestInit?.method, "POST");
  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.owner_id, "local-user");
  assert.equal(body.approved, true);
  assert.match(body.request_id, /^desktop-access-grant-/);
});

test("desktop control acquire normalizes epoch lease expiry to an ISO string", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    status: "ok",
    data: {
      seat_id: "seat-1",
      lease_id: "lease-1",
      lease_token: "secret-token",
      expires_at: 1767225600,
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  try {
    const result = await sandboxesApi.acquireDesktopControl("seat-1");
    assert.equal(result.expires_at, "2026-01-01T00:00:00.000Z");
    assert.equal(result.lease_token, "secret-token");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("desktop control renew normalizes expiry without requiring a lease token in the response", async () => {
  let requestInit: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    requestInit = init;
    return new Response(JSON.stringify({
      status: "ok",
      data: {
        seat_id: "seat-1",
        lease_id: "lease-1",
        expires_at: 1767225610,
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const result = await sandboxesApi.renewDesktopControl("seat-1", "secret-token");
    assert.equal(result.expires_at, "2026-01-01T00:00:10.000Z");
    assert.equal("lease_token" in result, false);
  } finally {
    globalThis.fetch = originalFetch;
  }

  const body = JSON.parse(String(requestInit?.body));
  assert.equal(body.lease_token, "secret-token");
  assert.match(body.request_id, /^desktop-control-renew-/);
});
