import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { buildVisibleModelOptions, SettingsModalRenderer } from "./SettingsModalRenderer";

function makeModelOption(index: number) {
  return {
    value: `demo/provider-model-${index}`,
    label: `Demo Provider / Model ${index}`,
    provider_id: "demo",
    provider_display_name: "Demo Provider",
    model_id: `model-${index}`,
  };
}

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

test("preferred model visibility keeps configured models beyond the old first-40 cutoff", () => {
  const filler = Array.from({ length: 45 }, (_, index) => makeModelOption(index));
  const zenOption = {
    value: "opencode-zen/minimax-m3-free",
    label: "OpenCode Zen / MiniMax M3 Free via OpenCode Zen",
    provider_id: "opencode-zen",
    provider_display_name: "OpenCode Zen",
    model_id: "minimax-m3-free",
    configured: true,
    supports_tool_calling: true,
    supports_thinking: true,
    supports_vision: true,
  };

  const visible = buildVisibleModelOptions({
    options: [...filler, zenOption],
    selected: null,
    remoteOptions: [],
    query: "",
  });

  assert.equal(visible.length, 46);
  assert(visible.some((option) => option.value === zenOption.value));
});

test("operations company model allowlist renders as an addable selection list", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "operations_company",
      catalog: {
        sidebar: { filters: [], items: [] },
        settings: { sections: [], values: {} },
        chat_rendering: { renderers: [] },
        extension_points: [],
      },
      health: null,
      previewsCount: 0,
      settingsSections: [
        {
          id: "operations_company",
          label: "Operations Company",
          fields: [
            {
              id: "model_allowlist",
              label: "Model Allowlist",
              type: "textarea",
              default: "stub/default\ngoogle/gemini-2.5-flash",
            },
          ],
        },
      ],
      settingsValues: {
        operations_company: {
          model_allowlist: "stub/default\ngoogle/gemini-2.5-flash",
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /モデルを追加/);
  assert.match(html, /stub\/default/);
  assert.match(html, /google\/gemini-2.5-flash/);
  assert.doesNotMatch(html, /<textarea[^>]*>stub\/default/);
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
        source: "viewer_tauri",
        reliable: true,
        app_name: "Rumi AI",
        display_version: "beta 1.0.0",
        viewer_version: "1.0.0-beta.1",
        build_channel: "beta",
        platform: "macos",
        platform_release: "15.0",
        permission_subject: "Rumi Viewer",
        host_broker: {
          enabled: true,
          available: true,
          status: "running",
        },
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
  assert.match(html, /macOSの承認対象は Rumi Viewer です/);
  assert.match(html, /macOS Permissions/);
  assert.match(html, /Screen Recording/);
  assert.match(html, /Missing/);
});

test("settings system info does not show missing permissions when viewer state is unreliable", () => {
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
        source: "fallback",
        reliable: false,
        app_name: "Rumi AI",
        display_version: "",
        viewer_version: "",
        build_channel: "beta",
        platform: "darwin",
        platform_release: "15.0",
        permission_subject: "Rumi Viewer",
        host_broker: {
          enabled: false,
          available: false,
          status: "unavailable",
        },
        permissions: [
          {
            id: "viewer_host",
            label: "Rumi Viewer",
            status: "missing",
            granted: false,
            detail: "Fallback row should not be rendered.",
            settings_hint: "Open Rumi Viewer.",
          },
        ],
      },
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /Viewer permission status is unverified/);
  assert.doesNotMatch(html, /macOS Permissions/);
  assert.doesNotMatch(html, /Missing/);
  assert.doesNotMatch(html, /Fallback row should not be rendered/);
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

  assert.match(html, /権限状態を取得できませんでした/);
  assert.match(html, /Rumi Viewerを起動し/);
  assert.doesNotMatch(html, /Rumi Defaultspack\.app/);
});
