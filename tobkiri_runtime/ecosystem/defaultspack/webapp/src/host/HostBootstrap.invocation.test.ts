import assert from "node:assert/strict";
import test from "node:test";


test("frontend capability invocation sends only the verified binding envelope", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  let request: { input: RequestInfo | URL; init?: RequestInit } | null = null;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setTimeout,
      clearTimeout,
    },
  });
  globalThis.fetch = async (input, init) => {
    request = { input, init };
    return new Response(
      JSON.stringify({ status: "ok", data: { items: [] } }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };
  try {
    const { invokeFrontendCapability } = await import("./HostBootstrap");
    const result = await invokeFrontendCapability("profile-1", {
      contractId: "rumi.resource.workflow.list.v1",
      contributionId: "workflows.list",
      ownerPackId: "workflow-pack",
      planHash: "plan-1",
      payload: {
        operation: "query",
        input: { query: "active", limit: 50 },
      },
    });

    assert.deepEqual(result, { items: [] });
    const captured = request as unknown as {
      input: RequestInfo | URL;
      init?: RequestInit;
    };
    assert.equal(captured.input, "/api/ui/capability/invoke");
    const body = JSON.parse(String(captured.init?.body));
    assert.equal(body.profile_id, "profile-1");
    assert.equal(body.plan_hash, "plan-1");
    assert.equal(body.owner_pack_id, "workflow-pack");
    assert.equal(body.contribution_id, "workflows.list");
    assert.equal(body.contract_id, "rumi.resource.workflow.list.v1");
    assert.equal(typeof body.request_id, "string");
    assert.equal(body.payload.operation, "query");
    assert.equal("endpoint" in body, false);
    assert.equal("permissions" in body, false);
  } finally {
    globalThis.fetch = originalFetch;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: originalWindow,
    });
  }
});


test("frontend capability invocation aborts when its bounded timeout expires", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  let timeoutDelay = 0;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setTimeout: (callback: () => void, delay: number) => {
        timeoutDelay = delay;
        callback();
        return 1;
      },
      clearTimeout: () => undefined,
    },
  });
  globalThis.fetch = async (_input, init) => {
    if (init?.signal?.aborted) throw new DOMException("aborted", "AbortError");
    return new Promise<Response>(() => undefined);
  };
  try {
    const { invokeFrontendCapability } = await import("./HostBootstrap");
    await assert.rejects(
      invokeFrontendCapability("profile-1", {
        contractId: "rumi.resource.workflow.list.v1",
        contributionId: "workflows.list",
        ownerPackId: "workflow-pack",
        planHash: "plan-1",
        payload: { operation: "query", input: {} },
      }),
      (error: unknown) => error instanceof DOMException && error.name === "AbortError",
    );
    assert.equal(timeoutDelay, 15_000);
  } finally {
    globalThis.fetch = originalFetch;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: originalWindow,
    });
  }
});
