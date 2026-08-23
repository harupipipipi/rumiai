import test from "node:test";
import assert from "node:assert/strict";

import type { UICatalog } from "./api";
import {
  ENTITY_PICKER_API_VERSION,
  ENTITY_PICKER_ACTION_CONTRACT,
  ENTITY_PICKER_DATA_SOURCE_CONTRACT,
  entityPickerForCommand,
  entityPickersForPresentation,
  filterEntityPickerItems,
  normalizeEntityPickerItems,
  readEntityPickerPath,
  resolveEntityPickers,
} from "./entityPicker";

function catalog(overrides: Partial<UICatalog>): UICatalog {
  const planHash = "sha256:resolved-plan";
  const contribution = (
    item: Record<string, unknown>,
    kind: "action" | "data_source",
    id: string,
  ) => ({
    contribution_id: String(
      item.contribution_id
        ?? (item.source_pack_id
          ? `pack.${String(item.source_pack_id)}.${String(item.operation_id ?? item.function_id ?? id)}`
          : id),
    ),
    kind,
    mode: "declarative" as const,
    label: id,
    priority: 0,
    owner_pack_id: String(item.source_pack_id ?? "test-pack"),
    owner_pack_hash: "sha256:pack",
    build_identity: "sha256:build",
    resolved_profile_revision: "sha256:profile",
    resolved_plan_hash: planHash,
    descriptor_hash: "sha256:descriptor",
    operation_id: String(item.operation_id ?? item.function_id ?? id),
    action_contract: kind === "action" ? ENTITY_PICKER_ACTION_CONTRACT : null,
    data_source_contract: kind === "data_source" ? ENTITY_PICKER_DATA_SOURCE_CONTRACT : null,
    localization: {},
    accessibility: { name: id, keyboard: true },
  });
  const sourceContributions = (overrides.data_sources ?? []).flatMap((item) => {
    const id = String(item.data_source ?? item.id ?? "");
    return id ? [contribution(item, "data_source", id)] : [];
  });
  const actionContributions = (overrides.actions ?? []).flatMap((item) => {
    const id = String(item.action_id ?? item.id ?? "");
    return id ? [contribution(item, "action", id)] : [];
  });
  return {
    sidebar: { filters: [], items: [] },
    settings: { sections: [], values: {} },
    chat_rendering: { renderers: [] },
    extension_points: [],
    dynamic_host: {
      version: "rumi.ui.contribution.v1",
      profile_id: "profile:test",
      profile_revision: "sha256:profile",
      plan_hash: planHash,
      catalog_hash: "sha256:catalog",
      contributions: [...sourceContributions, ...actionContributions],
      diagnostics: [],
      quarantined_pack_ids: [],
    },
    ...overrides,
  } as UICatalog;
}

const executableActions = [
  { action_id: "profiles.select", execution: { type: "rumi_function", qualified_name: "test:profiles.select" } },
  { action_id: "profiles.create", execution: { type: "rumi_function", qualified_name: "test:profiles.create" } },
  { action_id: "branches.load", execution: { type: "rumi_function", qualified_name: "test:branches.load" } },
];

test("resolves unrelated local and remote pickers from registered catalog declarations", () => {
  const resolved = resolveEntityPickers(catalog({
    actions: executableActions,
    data_sources: [
      {
        data_source: "agent_profiles",
        revision: "profiles-r4",
        snapshot: {
          items: [
            { key: "reviewer", display: { name: "Reviewer", summary: "Checks diffs" }, team: "Quality", starred: true, tags: ["safe"] },
            { key: "builder", display: { name: "Builder" }, team: "Delivery", recent: true, blocked: true, why: "Unavailable offline" },
          ],
        },
      },
      { data_source: "branches", remote: true, load_action_id: "branches.load", snapshot: { items: [] }, next_cursor: "page-2" },
    ],
    entity_pickers: [
      {
        picker_id: "agent_profile",
        api_version: ENTITY_PICKER_API_VERSION,
        label: "Agent profile",
        trigger_command: "/agent-profile",
        data_source: "agent_profiles",
        id_path: "key",
        label_path: "display.name",
        description_path: "display.summary",
        group_by_path: "team",
        badges_path: "tags",
        favorite_path: "starred",
        recent_path: "recent",
        disabled_path: "blocked",
        disabled_reason_path: "why",
        selection_mode: "multi",
        value_scope: "workspace",
        on_select_action_id: "profiles.select",
        fixed_entries: [{ id: "inherit", label: "Inherit" }, { id: "none", label: "None" }],
        create_item: { label: "Create profile", action_id: "profiles.create" },
      },
      {
        picker_id: "branch",
        label: "Branch",
        data_source: "branches",
        remote: true,
        load_action_id: "branches.load",
        presentation: "status_surface",
      },
      {
        picker_id: "composer_profile",
        label: "Composer profile",
        data_source: "agent_profiles",
        presentation: "inline",
      },
      {
        picker_id: "settings_profile",
        label: "Settings profile",
        data_source: "agent_profiles",
        presentation: "settings",
      },
    ],
  }));

  assert.equal(resolved.length, 4);
  const profiles = resolved[0]!;
  assert.equal(profiles.unsupported, false);
  assert.equal(profiles.triggerCommand, "agent-profile");
  assert.equal(profiles.selectionMode, "multi");
  assert.equal(profiles.optimistic, false);
  assert.equal(profiles.sourceRevision, "profiles-r4");
  assert.equal(profiles.remote, false);
  assert.equal(profiles.dataSourceCapability, undefined);
  assert.deepEqual(profiles.items.map((item) => item.id), ["__create__", "inherit", "none", "reviewer", "builder"]);
  assert.deepEqual(profiles.items[3], {
    id: "reviewer",
    label: "Reviewer",
    description: "Checks diffs",
    icon: undefined,
    group: "Quality",
    badges: ["safe"],
    disabled: false,
    disabledReason: undefined,
    favorite: true,
    recent: false,
  });
  assert.equal(profiles.items[4]?.disabledReason, "Unavailable offline");
  assert.equal(resolved[1]?.presentation, "status_surface");
  assert.deepEqual(entityPickersForPresentation(resolved, "status_surface").map((picker) => picker.id), ["branch"]);
  assert.deepEqual(entityPickersForPresentation(resolved, "inline").map((picker) => picker.id), ["composer_profile"]);
  assert.deepEqual(entityPickersForPresentation(resolved, "settings").map((picker) => picker.id), ["settings_profile"]);
  assert.equal(resolved[1]?.remote, true);
  assert.equal(resolved[1]?.dataSourceCapability?.contributionId, "branches");
  assert.equal(resolved[1]?.nextCursor, "page-2");
  assert.equal(entityPickerForCommand(resolved, { id: "agent-profile", name: "agent-profile" })?.id, "agent_profile");
  assert.equal(entityPickerForCommand(resolved, { id: "alias", name: "alias", aliases: ["agent-profile"] })?.id, "agent_profile");
});

test("fails closed for URLs, unsafe paths, unregistered sources, actions, and versions", () => {
  const resolved = resolveEntityPickers(catalog({
    data_sources: [{ data_source: "safe_source", snapshot: { items: [] } }],
    entity_pickers: [
      { picker_id: "url", data_source: "https://example.test/items" },
      { picker_id: "path", data_source: "safe_source", label_path: "constructor.name" },
      { picker_id: "missing", data_source: "not_registered" },
      { picker_id: "persistent", data_source: "safe_source", value_scope: "settings", on_select_action_id: "missing.action" },
      { picker_id: "future", api_version: "rumi.entity_picker.v99", data_source: "safe_source" },
    ],
  }));

  assert.equal(resolved.length, 5);
  assert.ok(resolved.every((picker) => picker.unsupported));
  assert.deepEqual(
    resolved.map((picker) => picker.diagnostics[0]?.code),
    [
      "entity_picker.invalid_data_source",
      "entity_picker.invalid_path",
      "entity_picker.unregistered_data_source",
      "entity_picker.unregistered_action",
      "entity_picker.incompatible_version",
    ],
  );
  assert.equal(readEntityPickerPath({ constructor: { name: "leak" } }, "constructor.name"), undefined);
});

test("normalization is bounded, deduplicated, opaque, and filter ordering is deterministic", () => {
  const picker = {
    itemPaths: { id: "id", label: "label", favorite: "favorite", recent: "recent", group: "group", badges: "badges" },
    maxItems: 4,
  } as const;
  const items = normalizeEntityPickerItems(picker, [
    { id: "z", label: "Zulu", group: "B", recent: true },
    { id: "a", label: "Alpha", group: "A", favorite: true, badges: ["primary"] },
    { id: "a", label: "Duplicate" },
    { id: "https://bad", label: "Rejected" },
    { id: "after-bound", label: "Not read" },
  ]);

  assert.deepEqual(items.map((item) => item.id), ["z", "a"]);
  assert.deepEqual(filterEntityPickerItems(items, "primary").map((item) => item.id), ["a"]);
  assert.deepEqual(filterEntityPickerItems(items, "").map((item) => item.id), ["a", "z"]);
});

test("disabled packs disappear without stale picker state", () => {
  const picker = { picker_id: "artifact", label: "Artifact", data_source: "artifacts" };
  const base = catalog({
    data_sources: [{ data_source: "artifacts", snapshot: { items: [{ id: "one", label: "One" }] } }],
    entity_pickers: [picker],
  });
  assert.equal(resolveEntityPickers(base).length, 1);
  assert.equal(resolveEntityPickers({ ...base, entity_pickers: [{ ...picker, enabled: false }] }).length, 0);
});

test("ephemeral scopes remain local while persistent scopes require registered actions", () => {
  const resolved = resolveEntityPickers(catalog({
    data_sources: [{ data_source: "items", snapshot: { items: [{ id: "one", label: "One" }] } }],
    entity_pickers: [
      { picker_id: "draft", data_source: "items", value_scope: "draft" },
      { picker_id: "conversation", data_source: "items", value_scope: "conversation" },
      { picker_id: "run", data_source: "items", value_scope: "run" },
      { picker_id: "settings", data_source: "items", value_scope: "settings" },
    ],
  }));

  assert.deepEqual(resolved.slice(0, 3).map((picker) => picker.unsupported), [false, false, false]);
  assert.ok(resolved.slice(0, 3).every((picker) => picker.optimistic));
  assert.equal(resolved[3]?.unsupported, true);
  assert.equal(resolved[3]?.diagnostics[0]?.code, "entity_picker.unregistered_action");
});

test("local snapshots stay local while remote sources require an active v4 capability", () => {
  const local = resolveEntityPickers(catalog({
    dynamic_host: null,
    data_sources: [{ data_source: "items", snapshot: { items: [{ id: "one", label: "One" }] } }],
    entity_pickers: [{ picker_id: "items", data_source: "items" }],
  }));
  const remote = resolveEntityPickers(catalog({
    dynamic_host: null,
    data_sources: [{ data_source: "items", remote: true, snapshot: { items: [] } }],
    entity_pickers: [{ picker_id: "items", data_source: "items", remote: true }],
  }));

  assert.equal(local[0]?.unsupported, false);
  assert.equal(local[0]?.remote, false);
  assert.equal(remote[0]?.unsupported, true);
  assert.equal(remote[0]?.diagnostics[0]?.code, "entity_picker.unbound_capability");
});

test("sibling-pack action metadata resolves only its exact captured operation", () => {
  const resolved = resolveEntityPickers(catalog({
    data_sources: [{
      data_source: "profiles",
      source_pack_id: "profiles-pack",
      snapshot: { items: [{ id: "reviewer", label: "Reviewer" }] },
    }],
    actions: [{
      action_id: "profiles.select",
      operation_id: "profiles.select",
      source_pack_id: "profiles-pack",
      execution: { type: "rumi_function", qualified_name: "profiles:select" },
    }],
    entity_pickers: [{
      picker_id: "profiles",
      data_source: "profiles",
      value_scope: "workspace",
      on_select_action_id: "profiles.select",
      source_pack_id: "profiles-pack",
    }],
  }));

  assert.equal(resolved[0]?.unsupported, false);
  assert.equal(
    resolved[0]?.selectActionCapability?.contributionId,
    "pack.profiles-pack.profiles.select",
  );
});
