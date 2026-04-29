import test from "node:test";
import assert from "node:assert/strict";

import type { UICatalog } from "./api";
import { hasShellRegion, shellRendererForRegion, shellRegions } from "./uiShell";

const catalog: UICatalog = {
  shell: {
    layout: {
      id: "custom",
      regions: [
        { id: "composer", renderer: "composer", order: 30 },
        { id: "history", renderer: "history_board", order: 10 },
        { id: "right_sidebar", renderer: "right_sidebar", order: 20, enabled: false },
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

test("shellRendererForRegion resolves renderer metadata", () => {
  assert.equal(shellRendererForRegion(catalog, "composer")?.component, "Composer");
  assert.equal(shellRendererForRegion(catalog, "missing"), null);
});
