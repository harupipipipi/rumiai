import test from "node:test";
import assert from "node:assert/strict";

import {
  COMPOSER_BUTTON_DROP,
  COMPOSER_PANEL_DROP,
  COMPOSER_SELECTOR_DROP,
  COMPOSER_TOGGLE_DROP,
  sortedToolGroups,
  sortedToolUiItems,
  supportedComposerDropKind,
  supportsComposerDrop,
  supportsComposerToggleDrop,
  toolGroupFor,
  toolGroupSegments,
} from "./toolUi";

test("declared tool group wins even when id has no legacy keywords", () => {
  const group = toolGroupFor({
    id: "nebula",
    label: "Nebula",
    description: "No file git coding search words here",
    tags: [],
    ui: {
      group_id: "declared_workspace",
      group_label: "Declared Workspace",
      group_icon: "terminal",
    },
  });

  assert.equal(group.id, "declared_workspace");
  assert.equal(group.label, "Declared Workspace");
  assert.equal(group.icon, "terminal");
  assert.equal(group.isDeclared, true);
});

test("hierarchical declared tool groups preserve normalized path", () => {
  const group = toolGroupFor({
    id: "coding_file_read",
    label: "Read File",
    description: "read",
    tags: [],
    ui: {
      group_id: "/coding//files/read/",
    },
  });

  assert.equal(group.id, "coding/files/read");
  assert.deepEqual(group.path, ["coding", "files", "read"]);
  assert.deepEqual(toolGroupSegments("coding/github/commit"), ["coding", "github", "commit"]);
});

test("legacy tools without declarations still fall back to heuristic grouping", () => {
  const group = toolGroupFor({
    id: "legacy_patch_writer",
    label: "Patch Writer",
    description: "write a file patch",
    tags: [],
  });

  assert.equal(group.id, "build");
  assert.equal(group.isDeclared, false);
});

test("tool groups sort by fixed workspace order instead of active or registry order", () => {
  const groups = sortedToolGroups([
    { id: "research", label: "Research", description: "", isDeclared: true, path: ["research"], items: [] },
    { id: "coding/files/write", label: "Write", description: "", isDeclared: true, path: ["coding", "files", "write"], items: [] },
    { id: "browser", label: "Browser", description: "", isDeclared: true, path: ["browser"], items: [] },
    { id: "coding/files/read", label: "Read", description: "", isDeclared: true, path: ["coding", "files", "read"], items: [] },
    { id: "computer", label: "Computer", description: "", isDeclared: true, path: ["computer"], items: [] },
  ]);

  assert.deepEqual(groups.map((group) => group.id), [
    "browser",
    "computer",
    "coding/files/read",
    "coding/files/write",
    "research",
  ]);
});

test("tool items sort by group and label", () => {
  const items = sortedToolUiItems([
    { id: "web_search", label: "Web Search", tags: ["search"] },
    { id: "coding_file_write", label: "Write File", ui: { group_id: "coding/files/write" } },
    { id: "browser_use", label: "Browser Use", ui: { group_id: "browser" } },
    { id: "coding_file_read", label: "Read File", ui: { group_id: "coding/files/read" } },
  ]);

  assert.deepEqual(items.map((item) => item.id), [
    "browser_use",
    "coding_file_read",
    "coding_file_write",
    "web_search",
  ]);
});

test("composer widget drop is exposed only when explicitly declared", () => {
  assert.equal(
    supportsComposerToggleDrop({
      id: "declared",
      label: "Declared",
      ui: {
        widget_kind: "tool_toggle",
        drop_capabilities: [COMPOSER_TOGGLE_DROP],
      },
    }),
    true,
  );

  assert.equal(
    supportsComposerToggleDrop({
      id: "legacy_file_tool",
      label: "Legacy File Tool",
      tags: ["file", "coding"],
    }),
    false,
  );

  assert.equal(
    supportsComposerToggleDrop({
      id: "half_declared",
      label: "Half Declared",
      ui: {
        drop_capabilities: [COMPOSER_TOGGLE_DROP],
      },
    }),
    false,
  );

  assert.equal(
    supportsComposerToggleDrop({
      id: "future_widget",
      label: "Future Widget",
      ui: {
        widget_kind: "panel",
        drop_capabilities: [COMPOSER_TOGGLE_DROP],
      },
    }),
    false,
  );
});

test("composer widget platform supports declared button panel and selector contracts", () => {
  assert.equal(
    supportedComposerDropKind({
      id: "status",
      label: "Status",
      ui: { widget_kind: "button", drop_capabilities: [COMPOSER_BUTTON_DROP] },
    }),
    "button",
  );
  assert.equal(
    supportedComposerDropKind({
      id: "providers",
      label: "Providers",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_PANEL_DROP] },
    }),
    "panel",
  );
  assert.equal(
    supportedComposerDropKind({
      id: "selector",
      label: "Selector",
      ui: { widget_kind: "selector", drop_capabilities: [COMPOSER_SELECTOR_DROP] },
    }),
    "selector",
  );
  assert.equal(
    supportsComposerDrop({
      id: "wrong-cap",
      label: "Wrong Capability",
      ui: { widget_kind: "button", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    }),
    false,
  );
  assert.equal(
    supportedComposerDropKind({
      id: "unknown",
      label: "Unknown",
      ui: { widget_kind: "future_widget", drop_capabilities: [COMPOSER_BUTTON_DROP] },
    }),
    null,
  );
});
