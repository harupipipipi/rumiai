import test from "node:test";
import assert from "node:assert/strict";

import type { SettingsSection } from "./api";
import { settingsFieldSearchText, settingsSectionSearchText } from "./settingsSearch";

test("settings search indexes field id label help and options", () => {
  const field: SettingsSection["fields"][number] = {
    id: "tool_assist_mode",
    label: "Tool Assist",
    type: "select",
    help: "Recommend relevant tools.",
    options: [
      { value: "all", label: "All tools" },
      { value: "vector", label: "Vector" },
    ],
  };

  const text = settingsFieldSearchText(field);

  assert.match(text, /tool_assist_mode/);
  assert.match(text, /recommend relevant tools/);
  assert.match(text, /all tools/);
});

test("settings search indexes section metadata and child fields", () => {
  const section: SettingsSection = {
    id: "models",
    label: "Models",
    description: "Model routing settings",
    fields: [
      {
        id: "model_api_routes",
        label: "Model API Priority",
        type: "textarea",
        help: "Fallback API route order",
      },
    ],
  };

  assert.match(settingsSectionSearchText(section), /fallback api route order/);
});
