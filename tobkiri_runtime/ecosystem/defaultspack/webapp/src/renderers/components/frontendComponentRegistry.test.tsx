import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { createBuiltinFrontendComponentRegistry } from "./builtinFrontendComponents";
import {
  createFrontendComponentRegistry,
  FRONTEND_COMPONENT_API_VERSION,
  FrontendComponentErrorBoundary,
  FrontendComponentHost,
  type FrontendComponentDefinition,
  type FrontendComponentRenderProps,
} from "./frontendComponentRegistry";
import {
  createSettingsFieldRendererRegistry,
  SettingsFieldRendererHost,
  type SettingsFieldRendererProps,
} from "../settings/fieldRendererRegistry";

function PackComponent({ props }: FrontendComponentRenderProps) {
  return <div data-pack-component="yes">{String(props.label ?? "")}</div>;
}

function definition(overrides: Partial<FrontendComponentDefinition> = {}): FrontendComponentDefinition {
  return {
    componentId: "pack.ui.card",
    apiVersion: FRONTEND_COMPONENT_API_VERSION,
    supportedSlots: ["workspace"],
    propsSchema: {
      type: "object",
      properties: { label: { type: "string", maxLength: 30 } },
      required: ["label"],
      additionalProperties: false,
    },
    render: PackComponent,
    ...overrides,
  };
}

const approval = {
  sourcePackId: "fixture_pack",
  approved: true,
  bundleVerified: true,
  declaredSlots: ["workspace"],
  grantedPermissions: ["ui.read"],
};

test("registered generic builtin resolves and renders without a feature map", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const resolution = registry.resolve({
    componentId: "rumi.ui.text",
    slot: "settings_field",
    props: { text: "Sibling pack text" },
    templateId: "fixture.template",
  });

  assert.equal(resolution.ok, true);
  const html = renderToStaticMarkup(
    createElement(FrontendComponentHost, {
      registry,
      request: {
        componentId: "rumi.ui.text",
        slot: "settings_field",
        props: { text: "Sibling pack text" },
      },
    }),
  );
  assert.match(html, /data-frontend-component="rumi.ui.text"/);
  assert.match(html, /Sibling pack text/);
});

test("unknown component fails closed with visible deterministic fallback", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const resolution = registry.resolve({ componentId: "feature.ui.missing", slot: "workspace" });

  assert.equal(resolution.ok, false);
  assert.equal(resolution.entry.componentId, "rumi.ui.unsupported");
  assert.equal(resolution.diagnostics[0].code, "frontend.component.unknown_id");
  const html = renderToStaticMarkup(
    createElement(FrontendComponentHost, {
      registry,
      request: { componentId: "feature.ui.missing", slot: "workspace" },
    }),
  );
  assert.match(html, /role="alert"/);
  assert.match(html, /feature.ui.missing/);
});

test("API version, slot, and props are validated before render", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const version = registry.resolve({
    componentId: "rumi.ui.text",
    apiVersion: "rumi.frontend.component.v999",
    slot: "workspace",
    props: { text: "ok" },
  });
  const slot = registry.resolve({
    componentId: "rumi.ui.text",
    slot: "authority_decision",
    props: { text: "ok" },
  });
  const props = registry.resolve({
    componentId: "rumi.ui.text",
    slot: "workspace",
    props: { text: "ok", endpoint: "https://attacker.invalid" },
  });

  assert.equal(version.diagnostics[0].code, "frontend.component.api_version_mismatch");
  assert.equal(slot.diagnostics[0].code, "frontend.component.incompatible_slot");
  assert.equal(props.diagnostics[0].code, "frontend.component.invalid_props");
  assert.match(props.diagnostics[0].message, /endpoint is not allowed/);
});

test("data sources and actions require registered contract IDs", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const diagnostics = registry.registerApprovedPack(
    definition({
      allowedDataSourceIds: ["fixture.status"],
      allowedActionIds: ["fixture.refresh"],
      dataContract: { type: "object" },
      actionContract: { type: "object" },
    }),
    approval,
  );
  assert.deepEqual(diagnostics, []);

  const denied = registry.resolve({
    componentId: "pack.ui.card",
    slot: "workspace",
    props: { label: "Card" },
    dataSourceIds: ["secrets.read"],
    actions: { run: { actionId: "authority.approve" } },
  });
  assert.equal(denied.ok, false);
  assert.deepEqual(
    denied.diagnostics.map((item) => item.code),
    [
      "frontend.component.data_source_not_registered",
      "frontend.component.action_not_registered",
    ],
  );
});

test("pack registration requires approval, verified bundle, slots, and permissions", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const diagnostics = registry.registerApprovedPack(
    definition({ requiredPermissions: ["ui.read", "filesystem.read"] }),
    {
      ...approval,
      approved: false,
      bundleVerified: false,
      declaredSlots: ["sidebar"],
    },
  );

  assert.deepEqual(
    diagnostics.map((item) => item.code),
    [
      "frontend.component.pack_bundle_not_approved",
      "frontend.component.undeclared_slot",
      "frontend.component.permission_not_granted",
    ],
  );
  assert.equal(registry.get("pack.ui.card"), null);
});

test("component IDs are opaque and cannot be module paths", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const diagnostics = registry.registerApprovedPack(
    definition({ componentId: "../../evil.js" }),
    approval,
  );

  assert.equal(diagnostics[0].code, "frontend.component.invalid_id");
  assert.equal(registry.entries().some((entry) => entry.componentId.includes("evil")), false);
});

test("self-referential fallback is rejected before registration", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const diagnostics = registry.registerApprovedPack(
    definition({ fallbackComponentId: "pack.ui.card" }),
    approval,
  );

  assert.equal(diagnostics[0].code, "frontend.component.self_fallback");
  assert.equal(registry.get("pack.ui.card"), null);
});

test("collisions fail closed and retain the first owner", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  assert.deepEqual(registry.registerApprovedPack(definition(), approval), []);
  const collision = registry.registerApprovedPack(definition(), {
    ...approval,
    sourcePackId: "other_pack",
  });

  assert.equal(collision[0].code, "frontend.component.registration_collision");
  assert.equal(registry.get("pack.ui.card")?.sourcePackId, "fixture_pack");
});

test("pack disable or uninstall removes only its registered components", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  registry.registerApprovedPack(definition(), approval);

  assert.equal(registry.unregisterSourcePack("fixture_pack"), 1);
  assert.equal(registry.get("pack.ui.card"), null);
  assert.notEqual(registry.get("rumi.ui.text"), null);
  assert.equal(
    registry.resolve({ componentId: "pack.ui.card", slot: "workspace" }).diagnostics[0].code,
    "frontend.component.unknown_id",
  );
});

test("settings surface resolves catalog component binding through generic registry", () => {
  const registry = createBuiltinFrontendComponentRegistry();
  const fallback = ({ field }: SettingsFieldRendererProps) => <span>{field.label}</span>;
  const html = renderToStaticMarkup(
    createElement(SettingsFieldRendererHost, {
      registry: createSettingsFieldRendererRegistry(),
      frontendComponentRegistry: registry,
      componentBindings: [
        {
          part_id: "fixture_field",
          component: "rumi.ui.text",
          component_id: "rumi.ui.text",
          api_version: FRONTEND_COMPONENT_API_VERSION,
          slot: "settings_field",
          props: { text: "Rendered from sibling catalog" },
          template_id: "fixture.template",
        },
      ],
      fallbackRenderer: fallback,
      sectionId: "fixture",
      field: { id: "fixture_field", label: "Fallback", type: "custom" },
      value: "",
      onChange: () => undefined,
    }),
  );

  assert.match(html, /Rendered from sibling catalog/);
  assert.doesNotMatch(html, />Fallback</);
});

test("error boundary deterministically swaps to fallback state", () => {
  const boundary = new FrontendComponentErrorBoundary({
    children: <span>child</span>,
    fallback: <span>fallback</span>,
  });
  boundary.state = FrontendComponentErrorBoundary.getDerivedStateFromError();

  const html = renderToStaticMarkup(boundary.render());
  assert.match(html, /fallback/);
  assert.doesNotMatch(html, /child/);
});

test("builtins and approved pack components share the same resolution contract", () => {
  const registry = createFrontendComponentRegistry();
  registry.registerBuiltin(
    definition({ componentId: "rumi.ui.fixture", supportedSlots: ["workspace"] }),
  );
  registry.registerApprovedPack(definition(), approval);

  for (const componentId of ["rumi.ui.fixture", "pack.ui.card"]) {
    const result = registry.resolve({
      componentId,
      slot: "workspace",
      props: { label: "Shared" },
    });
    assert.equal(result.ok, true);
  }
});
