import test from "node:test";
import assert from "node:assert/strict";

import type { SettingsSection, UICatalog } from "./api";
import { resolveSettingsState } from "./settingsState";

function coreSettingsSections(): SettingsSection[] {
  return [
    {
      id: "models",
      label: "Models",
      fields: [{ id: "preferred_model", label: "Preferred Model", type: "text" }],
    },
    {
      id: "apis",
      label: "API Tokens",
      fields: [{ id: "api_keys", label: "API Tokens", type: "readonly", default: "configured" }],
    },
    {
      id: "tools",
      label: "Tools",
      fields: [{ id: "default_tool_mode", label: "Tool Mode", type: "select", options: [{ value: "auto", label: "Auto" }] }],
    },
    {
      id: "general",
      label: "General",
      fields: [{ id: "language", label: "Language", type: "text", default: "ja" }],
    },
  ];
}

function catalogWithSettings(sections: SettingsSection[]): UICatalog {
  return {
    sidebar: { filters: [], items: [] },
    settings: {
      sections,
      values: {
        models: { preferred_model: "local/default" },
        general: { language: "ja" },
      },
    },
    chat_rendering: { renderers: [] },
    extension_points: [],
    parts: [],
  };
}

test("settings state falls back to catalog sections when registered metadata is empty", () => {
  const resolved = resolveSettingsState({ sections: [], values: {} }, catalogWithSettings(coreSettingsSections()));

  assert.equal(resolved.sectionsSource, "catalog");
  assert.deepEqual(resolved.sections.map((section) => section.label), [
    "Models",
    "API Tokens",
    "Tools",
    "General",
  ]);
  assert.equal(resolved.valuesSource, "catalog");
  assert.equal(resolved.values.models?.preferred_model, "local/default");
});

test("settings state prefers real settings endpoint sections when available", () => {
  const resolved = resolveSettingsState(
    {
      sections: [{ id: "models", label: "Live Models", fields: [] }],
      values: { models: { preferred_model: "live/model" } },
    },
    catalogWithSettings(coreSettingsSections()),
  );

  assert.equal(resolved.sectionsSource, "settings");
  assert.deepEqual(resolved.sections.map((section) => section.label), ["Live Models"]);
  assert.equal(resolved.valuesSource, "settings");
  assert.equal(resolved.values.models?.preferred_model, "live/model");
});
