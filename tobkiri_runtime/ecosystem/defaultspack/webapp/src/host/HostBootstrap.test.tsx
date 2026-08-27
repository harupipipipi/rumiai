import assert from "node:assert/strict";
import test from "node:test";

import {
  FrontendCapabilityError,
  fetchDynamicCatalog,
  invokeCapability,
} from "./HostBootstrap";
import type { FrontendCatalog, Sha256Digest } from "./frontendContracts";

const PLAN_HASH: Sha256Digest = `sha256:${"a".repeat(64)}`;
const CATALOG_HASH: Sha256Digest = `sha256:${"1".repeat(64)}`;

const catalog: FrontendCatalog = {
  version: "tobkiri.ui.contribution.v1",
  profile_id: "defaults",
  profile_revision: "profile-1",
  plan_hash: PLAN_HASH,
  contributions: [],
  diagnostics: [],
  quarantined_pack_ids: [],
  catalog_hash: CATALOG_HASH,
};

test("HostBootstrap accepts the canonical PackAPI success envelope", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => new Response(JSON.stringify({
    success: true,
    data: { dynamic_host: catalog },
    error: null,
  }), { status: 200 });

  assert.deepEqual(await fetchDynamicCatalog(), catalog);
});

test("HostBootstrap rejects catalogs without canonical typed hashes", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => new Response(JSON.stringify({
    success: true,
    data: {
      dynamic_host: { ...catalog, plan_hash: "plan-1" },
    },
  }), { status: 200 });

  await assert.rejects(
    fetchDynamicCatalog(),
    (error: unknown) => error instanceof Error
      && error.message === "dynamic_frontend_catalog_unavailable",
  );
});

test("HostBootstrap returns capability data from the canonical PackAPI envelope", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => new Response(JSON.stringify({
    success: true,
    data: { content: [{ type: "text", text: "Ready" }] },
    error: null,
  }), { status: 200 });

  assert.deepEqual(
    await invokeCapability("defaults", {
      contractId: "conversation.turn.v1",
      payload: { messages: [{ role: "user", content: "Hello" }] },
      contributionId: "defaults.conversation.complete",
      ownerPackId: "defaultspack",
      planHash: PLAN_HASH,
      catalogHash: catalog.catalog_hash,
    }),
    { content: [{ type: "text", text: "Ready" }] },
  );
});

test("HostBootstrap preserves typed PackAPI failure codes for stale refresh", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => new Response(JSON.stringify({
    success: false,
    data: { code: "STALE_CATALOG" },
    error: "The catalog changed",
  }), { status: 409 });

  await assert.rejects(
    invokeCapability("defaults", {
      contractId: "conversation.turn.v1",
      payload: { messages: [{ role: "user", content: "Hello" }] },
      contributionId: "defaults.conversation.complete",
      ownerPackId: "defaultspack",
      planHash: PLAN_HASH,
      catalogHash: catalog.catalog_hash,
    }),
    (error: unknown) => error instanceof FrontendCapabilityError
      && error.code === "STALE_CATALOG"
      && error.message === "The catalog changed",
  );
});
