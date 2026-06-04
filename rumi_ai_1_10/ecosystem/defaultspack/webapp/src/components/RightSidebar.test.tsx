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

test("right sidebar initially focuses the rail on tools", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [
        { id: "tool_a", label: "Tool A", category: "tool" },
        { id: "widget_a", label: "Widget A", category: "widget" },
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

  assert.match(html, /title="Filter: Tools"/);
  assert.match(html, /title="other \(1\)"/);
  assert.doesNotMatch(html, /title="Widget A"/);
});

test("right sidebar keeps initial tool groups compact", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: Array.from({ length: 12 }, (_value, index) => ({
        id: `tool_${index}`,
        label: `Tool ${index}`,
        category: "tool" as const,
        ui: { group_id: `group-${String(index).padStart(2, "0")}`, group_label: `Group ${index}` },
      })),
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

  assert.match(html, /title="More tools \(4 groups\)"/);
  assert.doesNotMatch(html, /title="Group 11 \(1\)"/);
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

test("right sidebar exposes workspace tabs as a vertical switcher widget", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [],
      settingsValues: {
        sidebar: { pinned_item_ids: [], starred_item_ids: [], custom_tool_tags: {}, ui_placements: [] },
        tools: { disabled_tool_ids: [], hidden_tool_ids: [] },
      },
      settingsSections: [],
      selectedToolIds: [],
      workspaceTabs: [
        { id: "tab-chat", kind: "chat", title: "Planning", conversationId: "conv-1", createdAt: 1 },
        { id: "tab-calendar", kind: "calendar", title: "Calendar", createdAt: 2 },
      ],
      activeWorkspaceTabId: "tab-chat",
      onSettingChange: noop,
      onOpenSettings: noop,
      onWorkspaceTabSelect: noop,
      onWorkspaceTabClose: noop,
      onWorkspaceTabCreate: noop,
    }),
  );

  assert.match(html, /title="Workspace tabs"/);
  assert.match(html, /aria-label="Workspace tabs"/);
  assert.match(html, />2</);
});
