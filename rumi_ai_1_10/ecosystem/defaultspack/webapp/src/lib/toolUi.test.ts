import test from "node:test";
import assert from "node:assert/strict";

import { COMPOSER_TOGGLE_DROP, supportsComposerToggleDrop, toolGroupFor, toolGroupSegments } from "./toolUi";

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
