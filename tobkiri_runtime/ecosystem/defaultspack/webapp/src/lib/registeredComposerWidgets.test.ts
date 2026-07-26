import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeComposerSelectorPage,
  registeredComposerWidgetMetadata,
  resolveRegisteredComposerWidget,
} from "./registeredComposerWidgets";
import type { DroppedWidget } from "../renderers/types";

const contribution = (
  id: string,
  kind: "action" | "data_source" | "renderer",
  ownerPackId = "workflow_pack",
) => ({
  contribution_id: id,
  kind,
  mode: "declarative",
  label: id,
  priority: 1,
  owner_pack_id: ownerPackId,
  owner_pack_hash: "sha256:verified",
  build_identity: `${ownerPackId}:1`,
  resolved_profile_revision: "revision-1",
  resolved_plan_hash: "plan-1",
  descriptor_hash: "sha256:descriptor",
  action_contract: kind === "action" ? "rumi.action.workflow.select.v1" : null,
  data_source_contract: kind === "data_source" ? "rumi.resource.workflow.list.v1" : null,
  view: kind === "renderer" ? { title: "Workflow panel", body: "Verified body" } : {},
  localization: {},
  accessibility: { name: id, keyboard: true },
});

const catalog = {
  dynamic_host: {
    version: "rumi.ui.contribution.v1",
    profile_id: "profile-1",
    profile_revision: "revision-1",
    plan_hash: "plan-1",
    contributions: [
      contribution("workflows.select", "action"),
      contribution("workflows.list", "data_source"),
      contribution("workflows.panel", "renderer"),
    ],
    diagnostics: [],
    quarantined_pack_ids: [],
    catalog_hash: "catalog-1",
  },
} as any;

function selectorWidget(ownerPackId = "workflow_pack"): DroppedWidget {
  return {
    id: "workflow-selector",
    type: "selector",
    label: "Workflow",
    widgetKind: "selector",
    metadata: registeredComposerWidgetMetadata({
      action_id: "workflows.select",
      data_source: "workflows.list",
      owner_pack_id: ownerPackId,
      value_scope: "draft",
    }) ?? {},
  };
}

test("registered composer bindings resolve only from the active verified catalog", () => {
  const resolved = resolveRegisteredComposerWidget(selectorWidget(), catalog);

  assert.equal(resolved?.action?.contribution_id, "workflows.select");
  assert.equal(resolved?.dataSource?.contribution_id, "workflows.list");
  assert.equal(resolved?.planHash, "plan-1");
  assert.equal(resolved?.descriptor.requestedValueScope, "draft");
});

test("forged owners, stale profiles, stale plans, and quarantined packs fail closed", () => {
  assert.equal(resolveRegisteredComposerWidget(selectorWidget("other_pack"), catalog), null);
  const staleProfile = structuredClone(catalog);
  staleProfile.dynamic_host.contributions[0].resolved_profile_revision = "old-revision";
  assert.equal(resolveRegisteredComposerWidget(selectorWidget(), staleProfile), null);
  const stale = structuredClone(catalog);
  stale.dynamic_host.contributions[0].resolved_plan_hash = "old-plan";
  assert.equal(resolveRegisteredComposerWidget(selectorWidget(), stale), null);
  const quarantined = structuredClone(catalog);
  quarantined.dynamic_host.quarantined_pack_ids = ["workflow_pack"];
  assert.equal(resolveRegisteredComposerWidget(selectorWidget(), quarantined), null);
});

test("selector pages are bounded, normalized, and preserve disabled reasons", () => {
  const page = normalizeComposerSelectorPage({
    data: {
      items: [
        { id: "one", label: "One" },
        { id: "two", label: "Two", disabled_reason: "Unavailable" },
        { id: "one", label: "Duplicate" },
        { id: "", label: "Invalid" },
      ],
      next_cursor: "cursor-2",
    },
  });

  assert.deepEqual(page, {
    items: [
      { id: "one", label: "One", disabled: false },
      {
        id: "two",
        label: "Two",
        disabled: true,
        disabledReason: "Unavailable",
      },
    ],
    nextCursor: "cursor-2",
  });
});
