import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { buildVisibleModelOptions, SettingsModalRenderer } from "./SettingsModalRenderer";
import { createSettingsFieldRendererRegistry, SettingsFieldRendererHost } from "./settings/fieldRendererRegistry";
import { builtinSettingsFieldRendererEntries } from "./settings/builtinSettingsFieldRenderers";
import { apiKeySetupTargetFieldId } from "./settings/renderers/settingsFieldRendererUtils";
import type { TemplateSettingsField } from "./template/settingsFieldMetadata";
import type { SettingsSection } from "../lib/api";

function makeModelOption(index: number) {
  return {
    value: `demo/provider-model-${index}`,
    label: `Demo Provider / Model ${index}`,
    provider_id: "demo",
    provider_display_name: "Demo Provider",
    model_id: `model-${index}`,
  };
}

test("settings field renderer host falls back for unknown fields", () => {
  const registry = createSettingsFieldRendererRegistry();
  const field = {
    id: "future_field",
    label: "Future Field",
    type: "future_field",
    default: "default value",
  } as TemplateSettingsField;

  const html = renderToStaticMarkup(
    createElement(SettingsFieldRendererHost, {
      registry,
      field,
      sectionId: "demo",
      value: "fallback value",
      onChange: () => undefined,
      fallbackRenderer: ({ value }) => createElement("span", { "data-fallback": "settings" }, String(value)),
    }),
  );

  assert.match(html, /data-fallback="settings"/);
  assert.match(html, /fallback value/);
});

test("settings field renderer registry routes new field types and catalog bindings", () => {
  const registry = createSettingsFieldRendererRegistry([
    {
      id: "builtin-model-select",
      types: ["model_select"],
      render: ({ field, value }) => createElement("output", { "data-renderer": "model" }, `${field.id}:${String(value)}`),
    },
    {
      id: "api-key-setup-binding",
      component: "ApiKeySetupField",
      render: ({ field }) => createElement("output", { "data-renderer": "api-key" }, field.id),
    },
    {
      id: "provider-select-renderer",
      renderers: ["provider_select.compact"],
      render: ({ field }) => createElement("output", { "data-renderer": "provider" }, field.id),
    },
  ]);

  const modelHtml = renderToStaticMarkup(
    createElement(SettingsFieldRendererHost, {
      registry,
      field: {
        id: "preferred_model",
        label: "Preferred Model",
        type: "model_select",
      } as TemplateSettingsField,
      sectionId: "models",
      value: "google/gemini",
      onChange: () => undefined,
      fallbackRenderer: () => createElement("span", null, "fallback"),
    }),
  );
  const apiKeyHtml = renderToStaticMarkup(
    createElement(SettingsFieldRendererHost, {
      registry,
      componentBindings: [{ part_id: "api_key_setup", component: "ApiKeySetupField" }],
      field: {
        id: "provider_key",
        label: "Provider Key",
        type: "api_key_setup",
        part_id: "api_key_setup",
      } as TemplateSettingsField,
      sectionId: "providers",
      value: null,
      onChange: () => undefined,
      fallbackRenderer: () => createElement("span", null, "fallback"),
    }),
  );
  const providerHtml = renderToStaticMarkup(
    createElement(SettingsFieldRendererHost, {
      registry,
      field: {
        id: "provider",
        label: "Provider",
        type: "provider_select",
        renderer: "provider_select.compact",
      } as TemplateSettingsField,
      sectionId: "providers",
      value: "google",
      onChange: () => undefined,
      fallbackRenderer: () => createElement("span", null, "fallback"),
    }),
  );

  assert.match(modelHtml, /data-renderer="model"/);
  assert.match(modelHtml, /preferred_model:google\/gemini/);
  assert.match(apiKeyHtml, /data-renderer="api-key"/);
  assert.match(apiKeyHtml, /provider_key/);
  assert.match(providerHtml, /data-renderer="provider"/);
  assert.match(providerHtml, /provider/);
});

test("builtin settings field renderer registry resolves template model_select renderer", () => {
  const registry = createSettingsFieldRendererRegistry(builtinSettingsFieldRendererEntries);
  const match = registry.resolve({
    id: "preferred_model_template",
    label: "Preferred Model",
    type: "model_select",
  } as TemplateSettingsField);

  assert.equal(match?.entry.id, "builtin-settings-model-select");
  assert.equal(match?.key, "model_select");
});

test("api_key_setup renderer actions target the rendered template field", () => {
  assert.equal(apiKeySetupTargetFieldId({
    id: "api_key_setup_template",
    label: "API Setup",
    type: "api_key_setup",
  } as TemplateSettingsField), "api_key_setup_template");
});

test("SettingsModalRenderer renders template model_select with searchable model selector surface", () => {
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
        {
          id: "models",
          label: "Models",
          fields: [
            {
              id: "preferred_model",
              label: "Preferred Model",
              type: "model_select",
              options: [
                {
                  value: "google/gemini-2.5-flash",
                  label: "Gemini 2.5 Flash",
                  provider_id: "google",
                  model_id: "gemini-2.5-flash",
                  configured: true,
                },
              ],
            } as TemplateSettingsField,
          ] as unknown as SettingsSection["fields"],
        },
      ],
      settingsValues: {
        models: {
          preferred_model: "google/gemini-2.5-flash",
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /data-settings-renderer="model_select"/);
  assert.match(html, /Gemini 2.5 Flash/);
  assert.doesNotMatch(html, /type="text"[^>]*google\/gemini-2\.5-flash/);
});

test("SettingsModalRenderer renders template slash command registration field", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "commands",
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
          id: "commands",
          label: "Commands",
          fields: [
            {
              id: "registered_slash_commands",
              label: "Slash Commands",
              type: "slash_commands",
              renderer: "slash_commands",
              default: [],
            } as TemplateSettingsField,
          ] as unknown as SettingsSection["fields"],
        },
      ],
      settingsValues: {
        commands: {
          registered_slash_commands: [
            { name: "yolo", action: "toggle_yolo", aliases: ["go"], enabled: true },
          ],
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /data-settings-renderer="slash_commands"/);
  assert.match(html, /value="yolo"/);
  assert.match(html, /value="go"/);
  assert.match(html, /YOLO/);
});

test("SettingsModalRenderer hides ambient detail fields until finger recording is enabled", () => {
  const sections = [
    {
      id: "ambient",
      label: "Ambient",
      fields: [
        {
          id: "ambient.monitor.enabled",
          label: "指で録音",
          type: "toggle",
          default: false,
        },
        {
          id: "ambient.camera.lock",
          label: "カメラ",
          type: "device_lock",
          renderer: "device_lock",
          visible_when: { field: "ambient.monitor.enabled", truthy: true },
          lock_message: "カメラが見つかりません。",
        },
        {
          id: "ambient.routing.model",
          label: "Ambient Send Model",
          type: "model_select",
          renderer: "model_select",
          visible_when: { field: "ambient.monitor.enabled", truthy: true },
        },
      ] as unknown as SettingsSection["fields"],
    },
  ];

  const offHtml = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "ambient",
      catalog: { sidebar: { filters: [], items: [] }, settings: { sections: [], values: {} }, chat_rendering: { renderers: [] }, extension_points: [] },
      health: null,
      previewsCount: 0,
      settingsSections: sections,
      settingsValues: { ambient: { "ambient.monitor.enabled": false } },
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );
  assert.match(offHtml, /指で録音/);
  assert.doesNotMatch(offHtml, /Ambient Send Model/);
  assert.doesNotMatch(offHtml, /data-settings-renderer="device_lock"/);

  const onHtml = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "ambient",
      catalog: { sidebar: { filters: [], items: [] }, settings: { sections: [], values: {} }, chat_rendering: { renderers: [] }, extension_points: [] },
      health: null,
      previewsCount: 0,
      settingsSections: sections,
      settingsValues: { ambient: { "ambient.monitor.enabled": true } },
      onClose: () => undefined,
      onOpenSection: () => undefined,
      onSettingChange: () => undefined,
    }),
  );
  assert.match(onHtml, /Ambient Send Model/);
  assert.match(onHtml, /data-settings-renderer="device_lock"/);
});

test("SettingsModalRenderer renders template api_key_setup with setup control", () => {
  const html = renderToStaticMarkup(
    createElement(SettingsModalRenderer, {
      isOpen: true,
      activeSectionId: "apis",
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
          id: "apis",
          label: "APIs",
          fields: [
            {
              id: "api_key_setup_template",
              label: "API Key Setup",
              type: "api_key_setup",
              provider_id: "openai",
            } as TemplateSettingsField,
          ] as unknown as SettingsSection["fields"],
        },
      ],
      settingsValues: {
        apis: {
          api_keys: [
            {
              provider_id: "openai",
              label: "OpenAI",
              apis: [{ api_id: "main", name: "main", configured: true }],
            },
          ],
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /data-settings-renderer="api_key_setup"/);
  assert.match(html, /openai:main:\*\*\*/);
  assert.match(html, /placeholder="openai API key"/);
  assert.match(html, />Save</);
});

test("SettingsModalRenderer renders template model_api_routes through registered model routing renderer", () => {
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
        {
          id: "models",
          label: "Models",
          fields: [
            {
              id: "model_api_routes",
              label: "Model API Variants",
              type: "model_api_routes",
              renderer: "model_routing",
              options: [
                {
                  value: "google/gemini-2.5-flash",
                  label: "Gemini 2.5 Flash",
                  provider_id: "google",
                  model_id: "gemini-2.5-flash",
                  configured: true,
                },
              ],
              api_keys: [
                {
                  provider_id: "google",
                  label: "Google",
                  apis: [{ api_id: "main", name: "main", configured: true }],
                },
              ],
            } as TemplateSettingsField,
          ] as unknown as SettingsSection["fields"],
        },
      ],
      settingsValues: {
        models: {
          preferred_model: "google/gemini-2.5-flash",
          model_api_routes: "google/gemini-2.5-flash: google/main",
        },
      },
      onClose: () => undefined,
      onSettingChange: () => undefined,
    }),
  );

  assert.match(html, /data-settings-renderer="model_routing"/);
  assert.match(html, /Gemini 2\.5 Flash/);
  assert.match(html, /google\/main/);
});

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
