import test from "node:test";
import assert from "node:assert/strict";

import type { SettingsSection } from "../lib/api";
import {
  buildAccountConnectionPrelude,
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
  assert.equal(safeSettingsLabel("mimo_model_preset"), "Mimo model preset");
  assert.equal(safeSettingsLabel("computer_use_gradient"), "Automation visual indicator");
  assert.equal(safeSettingsLabel("computer_use_gradient_enabled"), "Automation visual indicator");
  assert.equal(safeSettingsLabel("openrouter_auto_mode"), "OpenRouter auto routing");

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

test("account connection prelude disables unsupported Cloudflare backend", () => {
  const cards = buildAccountConnectionPrelude({
    apis: {
      api_keys: [
        {
          provider_id: "cloudflare",
          oauth: {
            backend_supported: false,
            connect_enabled: false,
            connection_status: "missing_scope_config",
            status_label: "Missing scope config",
            disabled_reason: "Configure self-host OAuth",
          },
        },
      ],
    },
  });

  const cloudflare = cards.find((card) => card.providerId === "cloudflare");
  assert.equal(cloudflare?.canConnect, false);
  assert.equal(cloudflare?.connectAction, undefined);
  assert.equal(cloudflare?.status, "missing_scope_config");
  assert.equal(cloudflare?.disabledReason, "Configure self-host OAuth");
  assert.match(cloudflare?.officialAppDescription ?? "", /Official app required/);
});

test("account connection prelude gives Google a real Workspace OAuth action when connectable", () => {
  const cards = buildAccountConnectionPrelude({
    apis: {
      api_keys: [
        {
          provider_id: "google",
          oauth: {
            supported: true,
            backend_supported: true,
            client_configured: true,
            connect_enabled: true,
            connection_status: "not_connected",
            status_label: "Ready to connect",
            scopes: [
              "openid",
              "email",
              "profile",
              "https://www.googleapis.com/auth/drive.file",
              "https://www.googleapis.com/auth/gmail.labels",
            ],
          },
        },
      ],
    },
  });

  const google = cards.find((card) => card.providerId === "google");
  assert.equal(google?.canConnect, true);
  assert.deepEqual(google?.connectAction, { providerId: "google", scopeMode: "google_workspace" });
  assert.equal(google?.scopeMode, "google_workspace");
  assert.ok(google?.scopes.includes("https://www.googleapis.com/auth/drive.file"));
  assert.ok(google?.scopes.includes("https://www.googleapis.com/auth/gmail.labels"));
});
