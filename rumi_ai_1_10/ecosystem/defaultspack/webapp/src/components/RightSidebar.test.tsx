import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { getRailFloatingMenuPosition, RightSidebar } from "./RightSidebar";
import { PromptSidebarWidget } from "./prompts/PromptSidebarWidget";

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

  assert.match(html, /title="Filter: 機能"/);
  assert.match(html, /title="other \(1\)"/);
  assert.doesNotMatch(html, /title="Widget A"/);
});

test("right sidebar does not auto-open the workroom on initial render", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [],
      settingsValues: {
        sidebar: { pinned_item_ids: [], starred_item_ids: [], custom_tool_tags: {}, ui_placements: [] },
        tools: { disabled_tool_ids: [], hidden_tool_ids: [] },
      },
      settingsSections: [],
      selectedToolIds: [],
      companyPanel: createElement("div", null, "Workroom content"),
      onSettingChange: noop,
      onOpenSettings: noop,
    }),
  );

  assert.match(html, /title="Workroom"/);
  assert.doesNotMatch(html, /Workroom content/);
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

  assert.match(html, /title="その他の機能 \(4 groups\)"/);
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

test("right sidebar exposes current prompts as a rail widget", () => {
  const html = renderToStaticMarkup(
    createElement(RightSidebar, {
      items: [],
      settingsValues: {
        sidebar: { pinned_item_ids: [], starred_item_ids: [], custom_tool_tags: {}, ui_placements: [] },
        tools: { disabled_tool_ids: [], hidden_tool_ids: [] },
      },
      settingsSections: [],
      selectedToolIds: [],
      promptUsage: {
        active_count: 2,
        token_estimate: { total: 155 },
        segments: [
          { id: "default_chat", prompt_id: "default_chat", label: "default_chat", status: "active", tokens: 124 },
          { id: "calculator", prompt_id: "calculator", label: "calculator", status: "active", tokens: 31 },
        ],
      },
      onLoadPromptActive: async () => ({ segments: [] }),
      onTogglePromptEdge: async () => ({ segments: [] }),
      onSettingChange: noop,
      onOpenSettings: noop,
    }),
  );

  assert.match(html, /title="Current prompts"/);
  assert.match(html, /aria-label="Current prompts"/);
  assert.match(html, />2</);
});

test("prompt sidebar widget lists prompt name and token count before details", () => {
  const html = renderToStaticMarkup(
    createElement(PromptSidebarWidget, {
      profileId: "default-profile",
      conversationId: "conversation-1",
      initialUsage: {
        active_count: 1,
        token_estimate: { total: 124 },
        segments: [
          {
            id: "default_chat",
            prompt_id: "default_chat",
            label: "default_chat",
            kind: "pack",
            status: "active",
            tokens: 124,
            reason: "Selected by the active profile.",
          },
        ],
      },
      loadPromptActive: async () => ({ segments: [] }),
      togglePromptEdge: async () => ({ segments: [] }),
      onOpenStudio: noop,
    }),
  );

  assert.match(html, /現在のプロンプト/);
  assert.match(html, /default_chat/);
  assert.match(html, /124/);
  assert.match(html, /Prompt Studio/);
  assert.doesNotMatch(html, /Selected by the active profile/);
});

test("prompt sidebar widget exposes chat prompt disclosure toggle", () => {
  const html = renderToStaticMarkup(
    createElement(PromptSidebarWidget, {
      profileId: "default-profile",
      initialUsage: {
        active_count: 0,
        token_estimate: { total: 0 },
        segments: [],
      },
      loadPromptActive: async () => ({ segments: [] }),
      togglePromptEdge: async () => ({ segments: [] }),
      showChatPromptUsage: false,
      onToggleChatPromptUsage: noop,
      onOpenStudio: noop,
    }),
  );

  assert.match(html, /チャット内の Prompt used/);
  assert.match(html, /メッセージ下では非表示/);
  assert.match(html, /aria-pressed="false"/);
  assert.match(html, />Off</);
});

test("right sidebar floating menus clamp to the viewport", () => {
  assert.deepEqual(
    getRailFloatingMenuPosition(
      { left: 1238, top: 627 },
      { width: 224, height: 360, viewportWidth: 1280, viewportHeight: 720 },
    ),
    { top: 352, right: 50 },
  );

  assert.deepEqual(
    getRailFloatingMenuPosition(
      { left: 8, top: -40 },
      { width: 224, height: 360, viewportWidth: 320, viewportHeight: 480 },
    ),
    { top: 8, right: 88 },
  );
});
