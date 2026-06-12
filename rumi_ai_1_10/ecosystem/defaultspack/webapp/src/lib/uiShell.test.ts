import test from "node:test";
import assert from "node:assert/strict";

import type { UICatalog } from "./api";
import { hasShellRegion, shellRegionById, shellRendererById, shellRendererForRegion, shellRegions, shellRegionsForSlot } from "./uiShell";

const catalog: UICatalog = {
  shell: {
    layout: {
      id: "custom",
      regions: [
        { id: "composer", renderer: "composer", slot: "bottom", order: 30 },
        { id: "history", renderer: "history_board", slot: "left", order: 10 },
        { id: "right_sidebar", renderer: "right_sidebar", slot: "right", order: 20, enabled: false },
      ],
    },
    renderers: [
      { id: "history_board", component: "HistoryBoard" },
      { id: "composer", component: "Composer" },
    ],
  },
  sidebar: { filters: [], items: [] },
  settings: { sections: [], values: {} },
  chat_rendering: { renderers: [] },
  extension_points: [],
};

test("shellRegions filters disabled regions and preserves configured order", () => {
  assert.deepEqual(shellRegions(catalog).map((region) => region.id), ["history", "composer"]);
});

test("hasShellRegion reads visible shell regions", () => {
  assert.equal(hasShellRegion(catalog, "history"), true);
  assert.equal(hasShellRegion(catalog, "right_sidebar"), false);
});

test("shellRegionsForSlot groups visible regions by slot", () => {
  assert.deepEqual(shellRegionsForSlot(catalog, "left").map((region) => region.id), ["history"]);
  assert.deepEqual(shellRegionsForSlot(catalog, "right").map((region) => region.id), []);
  assert.equal(shellRegionById(catalog, "history")?.slot, "left");
});

test("shellRendererForRegion resolves renderer metadata", () => {
  assert.equal(shellRendererForRegion(catalog, "composer")?.component, "Composer");
  assert.equal(shellRendererById(catalog, "history_board")?.component, "HistoryBoard");
  assert.equal(shellRendererForRegion(catalog, "missing"), null);
});
