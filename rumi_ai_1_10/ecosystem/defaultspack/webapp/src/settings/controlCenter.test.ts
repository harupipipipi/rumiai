import test from "node:test";
import assert from "node:assert/strict";

import type { SettingsSection } from "../lib/api";
import {
  buildControlCenterSections,
  controlCenterSectionForField,
  safeSettingsLabel,
} from "./controlCenter";

test("settings control center keeps the required section order", () => {
  const sections = buildControlCenterSections([]);
  assert.deepEqual(sections.map((section) => section.label), [
    "Quick Setup",
    "Models & API",
    "Accounts & Connections",
    "Tools & MCP",
    "Computer & Automation",
    "Workspace & UI",
    "Profiles",
    "Privacy & Security",
    "Packs & Extensions",
    "Advanced",
    "Diagnostics",
  ]);
});

test("settings control center separates computer control from tools", () => {
  const source = {
    id: "tools",
    label: "Tools",
    fields: [
      { id: "computer_approval_mode", label: "Computer approval mode", type: "select" },
      { id: "mcp_servers", label: "MCP servers", type: "textarea" },
    ],
  } as SettingsSection;

  assert.equal(controlCenterSectionForField(source, source.fields[0]), "computer_automation");
  assert.equal(controlCenterSectionForField(source, source.fields[1]), "tools_mcp");
});

test("settings control center removes raw labels from normal UI", () => {
  assert.equal(safeSettingsLabel("mimo"), "Mimo model preset");
  assert.equal(safeSettingsLabel("computer_use_gradient"), "Automation visual indicator");

  const sections = buildControlCenterSections([
    {
      id: "models",
      label: "Models",
      fields: [
        {
          id: "model_preset",
          label: "mimo",
          type: "select",
          options: [{ value: "openrouter_auto", label: "openrouter_auto" }],
        },
      ],
    },
  ]);
  const modelField = sections.find((section) => section.id === "models_api")?.fields[0];
  assert.equal(modelField?.label, "Mimo model preset");
  assert.equal(modelField?.options?.[0]?.label, "OpenRouter auto routing");
});
