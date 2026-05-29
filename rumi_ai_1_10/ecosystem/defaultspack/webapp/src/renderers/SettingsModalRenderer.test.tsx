import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { SettingsModalRenderer } from "./SettingsModalRenderer";

test("Settings > Tools contains detailed tool settings", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "tools",
      catalog: {
        sidebar: {
          filters: [],
          items: [
            {
              id: "vision_tool",
              label: "Vision Tool",
              category: "tool",
              description: "Inspect images",
              tool_info: {
                requires_approval: true,
                requires_model_capabilities: ["model.image_input"],
                attachment_policy: "images_only",
              },
            },
          ],
        },
        settings: { sections: [], values: {} },
        chat_rendering: { renderers: [] },
        extension_points: [],
      },
      health: null,
      previewsCount: 0,
      settingsSections: [
        {
          id: "tools",
          label: "Tools",
          fields: [
            { id: "keep_selected_tools_after_send", label: "Keep Selected Tools", type: "toggle", default: true },
          ],
        },
      ],
      settingsValues: {
        tools: {
          keep_selected_tools_after_send: true,
          disabled_tool_ids: [],
          hidden_tool_ids: [],
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /Tool details/);
  assert.match(html, /Vision Tool/);
  assert.match(html, /model.image_input/);
});

test("settings surface pinned placements render in the modal", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "models",
      catalog: {
        sidebar: { filters: [], items: [] },
        settings: { sections: [], values: {} },
        chat_rendering: { renderers: [] },
        extension_points: [],
      },
      health: null,
      previewsCount: 0,
      settingsSections: [
        { id: "models", label: "Models", description: "Model settings", fields: [] },
      ],
      settingsValues: {
        sidebar: {
          ui_placements: [{ id: "settings-section:models", surface: "settings" }],
        },
      },
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /Pinned placements/);
  assert.match(html, /Models/);
  assert.match(html, /このセクションを開く/);
});

test("settings system info renders viewer version and macOS permissions", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "system_info",
      catalog: {
        sidebar: { filters: [], items: [] },
        settings: { sections: [], values: {} },
        chat_rendering: { renderers: [] },
        extension_points: [],
      },
      health: null,
      previewsCount: 0,
      settingsSections: [
        { id: "system_info", label: "System Info", description: "Version and permission status", fields: [] },
      ],
      settingsValues: {},
      desktopSystemInfo: {
        app_name: "Rumi AI",
        display_version: "beta 1.0.0",
        viewer_version: "1.0.0-beta.1",
        build_channel: "beta",
        platform: "macos",
        platform_release: "15.0",
        permissions: [
          {
            id: "screen_recording",
            label: "Screen Recording",
            status: "missing",
            granted: false,
            detail: "Allows screen capture.",
            settings_hint: "System Settings > Privacy & Security > Screen Recording",
          },
        ],
      },
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /beta 1\.0\.0/);
  assert.match(html, /1\.0\.0-beta\.1/);
  assert.match(html, /macOS Permissions/);
  assert.match(html, /Screen Recording/);
  assert.match(html, /Missing/);
});

test("settings system info shows browser context message when info is null", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "system_info",
      catalog: {
        sidebar: { filters: [], items: [] },
        settings: { sections: [], values: {} },
        chat_rendering: { renderers: [] },
        extension_points: [],
      },
      health: null,
      previewsCount: 0,
      settingsSections: [
        { id: "system_info", label: "System Info", description: "Version and permission status", fields: [] },
      ],
      settingsValues: {},
      desktopSystemInfo: null,
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /承認状態を取得できませんでした/);
  assert.match(html, /外部ブラウザ/);
});
