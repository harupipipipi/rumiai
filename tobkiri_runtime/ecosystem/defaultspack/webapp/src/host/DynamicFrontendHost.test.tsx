import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  DynamicFrontendHost,
  ISOLATED_FRONTEND_SANDBOX,
  ISOLATED_FRAME_RESPONSE_TARGET_ORIGIN,
  buildFrontendComponentRegistry,
  contributionsForRoute,
  frontendActionErrorMessage,
  isolatedFrontendFrameUrl,
  parseIsolatedCapabilityRequest,
  quarantineFrontendContribution,
  resetFrontendHostQuarantineForTests,
  synchronizeFrontendHostQuarantine,
} from "./DynamicFrontendHost";
import {
  FRONTEND_COMPONENT_API_VERSION,
  UNSUPPORTED_COMPONENT_ID,
} from "./frontendComponentRegistry";
import type {
  FrontendCapabilityClient,
  FrontendCatalog,
  VerifiedFrontendContribution,
} from "./frontendContracts";

const contribution = (
  overrides: Partial<VerifiedFrontendContribution> = {},
): VerifiedFrontendContribution => ({
  contribution_id: "feature.route",
  kind: "route",
  mode: "declarative",
  label: "Feature",
  priority: 0,
  owner_pack_id: "feature-pack",
  owner_pack_hash: `sha256:${"1".repeat(64)}`,
  build_identity: "fixture",
  resolved_profile_revision: "r1",
  resolved_plan_hash: "plan-1",
  descriptor_hash: `sha256:${"2".repeat(64)}`,
  route: "/feature",
  view: { title: "Dynamic feature" },
  localization: {},
  accessibility: { name: "Dynamic feature", keyboard: true },
  ...overrides,
});

const catalog = (items: VerifiedFrontendContribution[]): FrontendCatalog => ({
  version: "rumi.ui.contribution.v1",
  profile_id: "fixture",
  profile_revision: "r1",
  plan_hash: "plan-1",
  contributions: items,
  diagnostics: [],
  quarantined_pack_ids: [],
  catalog_hash: `sha256:${"3".repeat(64)}`,
});

const capabilities: FrontendCapabilityClient = {
  invokeAction: async () => ({ ok: true }),
  readDataSource: async () => ({ ok: true }),
};

test("route visibility follows the active resolved plan", () => {
  resetFrontendHostQuarantineForTests();
  const current = catalog([contribution()]);

  assert.equal(contributionsForRoute(current, "/feature", "plan-1").length, 1);
  assert.deepEqual(contributionsForRoute(current, "/feature", "plan-2"), []);
});

test("renders a declarative route without importing a product screen", () => {
  resetFrontendHostQuarantineForTests();
  const markup = renderToStaticMarkup(
    <DynamicFrontendHost
      catalog={catalog([contribution()])}
      route="/feature"
      activePlanHash="plan-1"
      capabilities={capabilities}
    />,
  );

  assert.match(markup, /<h2>Dynamic feature<\/h2>/);
  assert.doesNotMatch(markup, /iframe/);
});

test("renders a registry-backed generic component without a product import", () => {
  resetFrontendHostQuarantineForTests();
  const item = contribution({
    view: {
      type: "component",
      component_id: "rumi.ui.status_surface",
      api_version: FRONTEND_COMPONENT_API_VERSION,
      slot: "route",
      props: { title: "Pack-owned workflow", body: "Ready", tone: "success" },
    },
  });

  const markup = renderToStaticMarkup(
    <DynamicFrontendHost
      catalog={catalog([item])}
      route="/feature"
      activePlanHash="plan-1"
      capabilities={capabilities}
    />,
  );

  assert.match(markup, /data-frontend-component-id="rumi.ui.status_surface"/);
  assert.match(markup, /Pack-owned workflow/);
  assert.match(markup, /data-status-tone="success"/);
});

test("component registry fails closed for unknown ids, slots, props, and contracts", () => {
  const registry = buildFrontendComponentRegistry(catalog([]));
  const base = {
    componentId: "rumi.ui.status_surface",
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    slot: "route",
    props: { title: "Ready" },
  };

  assert.equal(registry.resolve({ ...base, componentId: "pack.ui.unknown" }).diagnostic?.code, "frontend_component_unknown");
  assert.equal(registry.resolve({ ...base, apiVersion: "rumi.frontend.component.v2" }).diagnostic?.code, "frontend_component_version_mismatch");
  assert.equal(registry.resolve({ ...base, slot: "secret_overlay" }).diagnostic?.code, "frontend_component_slot_mismatch");
  assert.equal(registry.resolve({ ...base, props: { title: "Ready", secret: "no" } }).diagnostic?.code, "frontend_component_props_invalid");
  assert.equal(registry.resolve({ ...base, actionContract: "rumi.action.secret.read.v1" }).diagnostic?.code, "frontend_component_action_contract_mismatch");
  assert.equal(registry.resolve({ ...base, dataContract: "rumi.resource.secret.read.v1" }).diagnostic?.code, "frontend_component_data_contract_mismatch");
});

test("unknown component ids render a visible deterministic fallback", () => {
  const item = contribution({
    view: {
      type: "component",
      component_id: "pack.ui.missing",
      api_version: FRONTEND_COMPONENT_API_VERSION,
      slot: "route",
      props: {},
    },
  });

  const markup = renderToStaticMarkup(
    <DynamicFrontendHost
      catalog={catalog([item])}
      route="/feature"
      activePlanHash="plan-1"
      capabilities={capabilities}
    />,
  );

  assert.match(markup, /data-frontend-component-fallback="true"/);
  assert.match(markup, /data-component-diagnostic="frontend_component_unknown"/);
  assert.match(markup, /Unsupported component/);
});

test("verified pack component registration follows catalog replacement and detects collisions", () => {
  const packComponent = contribution({
    contribution_id: "pack-a.component.card",
    kind: "component",
    mode: "same_origin_builtin",
    route: null,
    view: null,
    component_id: "pack.ui.card",
    api_version: FRONTEND_COMPONENT_API_VERSION,
    supported_slots: ["workspace"],
    props_schema: {
      type: "object",
      required: ["title"],
      additionalProperties: false,
      properties: { title: { type: "string" } },
    },
    fallback_component_id: UNSUPPORTED_COMPONENT_ID,
    module: {
      path: "/static/packs/feature-pack/component.js",
      export: "Component",
      content_hash: `sha256:${"4".repeat(64)}`,
    },
  });
  const binding = {
    componentId: "pack.ui.card",
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    slot: "workspace",
    props: { title: "Card" },
  };
  const withPack = buildFrontendComponentRegistry(catalog([packComponent]));
  const withoutPack = buildFrontendComponentRegistry(catalog([]));

  assert.equal(withPack.resolve(binding).registration.ownerPackId, "feature-pack");
  assert.equal(withoutPack.resolve(binding).diagnostic?.code, "frontend_component_unknown");

  const collision = contribution({
    ...packComponent,
    contribution_id: "pack-b.component.card",
    owner_pack_id: "pack-b",
    module: {
      ...packComponent.module!,
      path: "/static/packs/pack-b/component.js",
    },
  });
  const collided = buildFrontendComponentRegistry(catalog([packComponent, collision]));
  assert.equal(collided.diagnostics()[0]?.code, "frontend_component_collision");
});

test("missing pack contribution has a generic isolated fallback", () => {
  resetFrontendHostQuarantineForTests();
  const markup = renderToStaticMarkup(
    <DynamicFrontendHost
      catalog={catalog([])}
      route="/feature"
      activePlanHash="plan-1"
      capabilities={capabilities}
    />,
  );

  assert.match(markup, /role="status"/);
  assert.match(markup, /not available/);
});

test("isolated contribution URLs are owner-bound and receive an opaque frame sandbox", () => {
  const isolated = contribution({
    mode: "isolated",
    isolated: {
      path: "/isolated/packs/feature-pack/index.html",
      rpc_contracts: ["rumi.resource.feature.read.v1"],
    },
  });

  assert.equal(ISOLATED_FRONTEND_SANDBOX, "allow-scripts");
  assert.equal(ISOLATED_FRAME_RESPONSE_TARGET_ORIGIN, "*");
  assert.equal(
    isolatedFrontendFrameUrl(
      isolated,
      "profile-1",
      "nonce-1",
      "https://tobkiri.local",
    ),
    "/isolated/packs/feature-pack/index.html?profile_id=profile-1#rumi_rpc_nonce=nonce-1",
  );
  assert.equal(
    isolatedFrontendFrameUrl(
      contribution({
        mode: "isolated",
        isolated: {
          path: "/isolated/packs/other-pack/index.html",
          rpc_contracts: [],
        },
      }),
      "profile-1",
      "nonce-1",
      "https://tobkiri.local",
    ),
    null,
  );
});

test("isolated frame RPC accepts only a bounded contract request envelope", () => {
  assert.deepEqual(
    parseIsolatedCapabilityRequest({
      type: "rumi.capability.request",
      requestId: "request-1",
      nonce: "nonce-1",
      contractId: "rumi.resource.feature.read.v1",
      payload: { operation: "read", input: { id: "feature" } },
    }),
    {
      requestId: "request-1",
      nonce: "nonce-1",
      contractId: "rumi.resource.feature.read.v1",
      payload: { operation: "read", input: { id: "feature" } },
    },
  );
  assert.equal(
    parseIsolatedCapabilityRequest({
      type: "rumi.capability.request",
      requestId: "request-1",
      nonce: "nonce-1",
      contractId: "rumi.resource.feature.read.v1",
      payload: { operation: "read", input: [] },
    }),
    null,
  );
});

test("catalog synchronization releases obsolete contribution quarantines", () => {
  resetFrontendHostQuarantineForTests();
  const failed = contribution();
  quarantineFrontendContribution(failed);
  assert.equal(contributionsForRoute(catalog([failed]), "/feature", "plan-1").length, 0);

  const replacement = contribution({
    descriptor_hash: `sha256:${"4".repeat(64)}`,
  });
  synchronizeFrontendHostQuarantine(catalog([replacement]));

  assert.equal(contributionsForRoute(catalog([failed]), "/feature", "plan-1").length, 1);
});

test("capability action errors preserve stale-catalog recovery guidance", () => {
  assert.equal(
    frontendActionErrorMessage({ code: "STALE_CATALOG" }),
    "This screen is out of date and is refreshing. Try the action again.",
  );
  assert.equal(
    frontendActionErrorMessage(new Error("Action denied")),
    "Action denied",
  );
});
