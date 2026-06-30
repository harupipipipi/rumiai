import test from "node:test";
import assert from "node:assert/strict";

import type { SettingsSection } from "../lib/api";
import {
  buildCodexAppServerPrelude,
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

test("account connection prelude shows Cloudflare fallback when provider exists without client config", () => {
  const cards = buildAccountConnectionPrelude({
    accounts_connections: {
      providers: {
        cloudflare: {
          supported: true,
          backend_supported: false,
          client_configured: false,
          connect_enabled: false,
          connection_status: "needs_official_app",
          status_label: "Official app required",
          disabled_reason: "Official app required",
        },
      },
    },
  });

  const cloudflare = cards.find((card) => card.providerId === "cloudflare");
  assert.equal(cloudflare?.label, "Cloudflare");
  assert.equal(cloudflare?.canConnect, false);
  assert.equal(cloudflare?.connectAction, undefined);
  assert.equal(cloudflare?.statusLabel, "Official app required");
  assert.match(cloudflare?.officialAppDescription ?? "", /Official app required/);
  assert.match(cloudflare?.selfHostDescription ?? "", /Self-host OAuth remains available/);
});

test("account connection prelude gives Google explicit OAuth scope mode actions", () => {
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
            scope_mode: "google_gmail_labels",
            scope_modes: [
              {
                id: "google_identity",
                label: "Google identity",
                description: "Basic identity",
                scopes: ["openid", "email", "profile"],
                services: ["identity"],
              },
              {
                id: "google_drive",
                label: "Google Drive selected files",
                description: "Drive file",
                scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.file"],
                services: ["identity", "drive_file"],
              },
              {
                id: "google_gmail_labels",
                label: "Gmail labels",
                description: "Labels only",
                scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.labels"],
                services: ["identity", "gmail_labels"],
              },
              {
                id: "google_gmail_metadata",
                label: "Gmail metadata/search",
                description: "Metadata",
                scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.metadata"],
                services: ["identity", "gmail_metadata"],
                restricted: true,
                warning: "Restricted Gmail scopes require explicit review.",
              },
            ],
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
  assert.deepEqual(google?.connectAction, { providerId: "google", scopeMode: "google_gmail_labels", services: ["identity", "gmail_labels"] });
  assert.equal(google?.scopeMode, "google_gmail_labels");
  assert.ok(google?.scopes.includes("https://www.googleapis.com/auth/gmail.labels"));
  assert.equal(google?.scopeModes.length, 4);
  assert.ok(google?.scopeModes.some((mode) => mode.id === "google_drive"));
  assert.ok(google?.scopeModes.some((mode) => mode.id === "google_gmail_metadata" && mode.restricted));
  assert.match(google?.scopeModes.find((mode) => mode.id === "google_gmail_metadata")?.warning ?? "", /Restricted Gmail/);
});

test("account connection prelude treats Codex as a redacted credential", () => {
  const rawToken = ["codex", "raw", "token"].join("-");
  const cards = buildAccountConnectionPrelude({
    accounts_connections: {
      providers: {
        codex: {
          connected: true,
          configured: true,
          token_configured: true,
          can_clear: true,
          connection_status: "connected",
          status_label: "Token saved",
          access_token: rawToken,
        },
      },
    },
  });

  const codex = cards.find((card) => card.providerId === "codex");
  assert.equal(codex?.label, "Codex");
  assert.equal(codex?.canConnect, false);
  assert.equal(codex?.connectAction, undefined);
  assert.equal(codex?.credential?.kind, "codex_access_token");
  assert.equal(codex?.credential?.configured, true);
  assert.equal(codex?.credential?.canClear, true);
  assert.doesNotMatch(JSON.stringify(codex), new RegExp(rawToken));
});

test("Codex App Server prelude maps safe Tools & MCP status", () => {
  const prelude = buildCodexAppServerPrelude({
    tools_mcp: {
      codex_app_server: {
        configured: true,
        enabled: true,
        transport: "websocket_remote",
        connection_status: "blocked_auth_required",
        status_label: "Auth required",
        blocked_reason: "Configure a Codex App Server WS token or shared secret before using a non-loopback endpoint.",
        base_url: "https://codex-app.example.test",
        websocket_url: "wss://codex-app.example.test/ws",
        unix_socket_path: "",
        loopback: false,
        auth_required: true,
        auth_configured: false,
        auth_source: "missing",
        auth_kind: "",
        ws_token_file: "/Users/haru/.config/rumi/codex-app-server.token",
        shared_secret_file: "",
        tool_source: { status: "blocked_auth_required" },
        automation_endpoint: { status: "disabled" },
      },
    },
  });

  assert.equal(prelude.configured, true);
  assert.equal(prelude.enabled, true);
  assert.equal(prelude.transport, "websocket_remote");
  assert.equal(prelude.status, "blocked_auth_required");
  assert.equal(prelude.statusLabel, "Auth required");
  assert.equal(prelude.loopback, false);
  assert.equal(prelude.authRequired, true);
  assert.equal(prelude.authSource, "missing");
  assert.equal(prelude.wsTokenFile, "/Users/haru/.config/rumi/codex-app-server.token");
  assert.equal(prelude.authConfigured, false);
  assert.equal(prelude.toolSourceStatus, "blocked_auth_required");
  assert.equal(prelude.automationEndpointStatus, "disabled");
});
