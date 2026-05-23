import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RightSidebar } from "./RightSidebar";

const noop = () => undefined;

test("left sidebar default does not render every tool detail panel", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [
        { id: "vision_tool", label: "Vision Tool", category: "tool", description: "Detail panel text" },
      ],
      settingsValues: {
        sidebar: { pinned_item_ids: [], starred_item_ids: [], custom_tool_tags: {}, ui_placements: [] },
        tools: { disabled_tool_ids: [], hidden_tool_ids: [] },
      },
      settingsSections: [],
      selectedToolIds: [],
      onSettingChange: noop,
      onOpenSettings: noop,
    }),
  );

  assert.doesNotMatch(html, /Detail panel text/);
});

test("YOLO switch and Model Manager can be pinned", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [],
      settingsValues: {
        sidebar: {
          pinned_item_ids: [],
          starred_item_ids: [],
          custom_tool_tags: {},
          ui_placements: [
            { id: "yolo-switch", surface: "right_sidebar" },
            { id: "model-manager", surface: "right_sidebar" },
          ],
        },
        tools: { disabled_tool_ids: [], hidden_tool_ids: [] },
      },
      settingsSections: [{ id: "models", label: "Models", fields: [] }],
      selectedToolIds: [],
      yoloMode: true,
      onSettingChange: noop,
      onOpenSettings: noop,
      onToggleYolo: noop,
      onOpenSettingsSection: noop,
    }),
  );

  assert.match(html, /title="YOLO Switch"/);
  assert.match(html, /title="Model Manager"/);
});
