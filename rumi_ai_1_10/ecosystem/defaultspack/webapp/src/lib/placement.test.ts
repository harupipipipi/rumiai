import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBuiltinPlacementManifests,
  filterPlacementCandidates,
  readPinnedPlacements,
  resolvePlacementHtmlRendering,
  togglePinnedPlacement,
  withPinnedPlacements,
  writePinnedPlacements,
  type PlacementManifest,
} from "./placement";

test("placement filtering respects surface orientation and settings_only", () => {
  const manifests: PlacementManifest[] = [
    {
      id: "horizontal",
      label: "Horizontal",
      source: { type: "custom" },
      renderer: { kind: "component" },
      placements: [{ surface: "top_bar", orientation: "horizontal" }],
    },
    {
      id: "vertical",
      label: "Vertical",
      source: { type: "custom" },
      renderer: { kind: "component" },
      placements: [{ surface: "right_sidebar", orientation: "vertical" }],
      constraints: { settings_only: true },
    },
    {
      id: "both",
      label: "Both",
      source: { type: "custom" },
      renderer: { kind: "component" },
      placements: [{ surface: "right_sidebar", orientation: "both" }],
    },
  ];

  assert.deepEqual(
    filterPlacementCandidates(manifests, { surface: "top_bar", orientation: "horizontal" }).map((item) => item.id),
    ["horizontal"],
  );
  assert.deepEqual(
    filterPlacementCandidates(manifests, { surface: "right_sidebar", orientation: "vertical" }).map((item) => item.id),
    ["both"],
  );
  assert.deepEqual(
    filterPlacementCandidates(manifests, { surface: "settings", orientation: "vertical" }).map((item) => item.id),
    [],
  );
});

test("pinned placements persist through storage helpers", () => {
  const store = new Map<string, string>();
  const storage = {
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
  };
  const next = togglePinnedPlacement([], { id: "yolo-switch", surface: "right_sidebar" });
  writePinnedPlacements(storage, next);

  assert.deepEqual(readPinnedPlacements(storage), [{ id: "yolo-switch", surface: "right_sidebar" }]);
});

test("pinned placements update the sidebar without dropping other settings", () => {
  const current = {
    sidebar: {
      pinned_item_ids: ["terminal"],
      ui_placements: [{ id: "runtime-status", surface: "right_sidebar" }],
    },
    tools: { disabled_tool_ids: ["dangerous-tool"] },
  };

  const next = withPinnedPlacements(current, [
    { id: "runtime-status", surface: "right_sidebar" },
    { id: "tool-filter-log", surface: "right_sidebar" },
  ]);

  assert.deepEqual(next.sidebar.ui_placements, [
    { id: "runtime-status", surface: "right_sidebar" },
    { id: "tool-filter-log", surface: "right_sidebar" },
  ]);
  assert.deepEqual(next.sidebar.pinned_item_ids, ["terminal"]);
  assert.deepEqual(next.tools, current.tools);
  assert.notEqual(next, current);
  assert.notEqual(next.sidebar, current.sidebar);
});

test("builtin placements include yolo switch and model manager", () => {
  const ids = buildBuiltinPlacementManifests([{ id: "tools", label: "Tools", fields: [] }]).map((item) => item.id);
  assert.ok(ids.includes("yolo-switch"));
  assert.ok(ids.includes("model-manager"));
});

test("html placements resolve to sandboxed iframe rendering", () => {
  const rendering = resolvePlacementHtmlRendering({
    id: "html-test",
    label: "HTML",
    source: { type: "custom" },
    renderer: { kind: "html", html: "<script>alert(1)</script>" },
    placements: [{ surface: "right_sidebar", orientation: "vertical" }],
  });

  assert.equal(rendering.kind, "html_iframe");
  assert.equal(rendering.sandbox, "allow-same-origin");
});
