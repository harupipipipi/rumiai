import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type {
  RuntimeProviderStatus,
  SandboxTemplate,
} from "../../features/sandboxes/types";
import { DesktopCreateDialog } from "./DesktopCreateDialog";

const templates: SandboxTemplate[] = [
  {
    template_id: "desktop.linux_native",
    name: "Linux Native Desktop",
    provider_requirements: [
      "sandbox.desktop",
      "sandbox.desktop_input",
      "sandbox.snapshot",
    ],
  },
];

const providers: RuntimeProviderStatus[] = [
  {
    provider_id: "linux_native",
    status: "ready",
    ready: true,
    capabilities: [
      "sandbox.desktop",
      "sandbox.desktop_input",
      "sandbox.snapshot",
    ],
  },
];

function renderDialog(
  overrides: Partial<{
    templates: SandboxTemplate[];
    providers: RuntimeProviderStatus[];
    selectedProviderId: string | null;
  }> = {},
): string {
  return renderToStaticMarkup(
    createElement(DesktopCreateDialog, {
      isOpen: true,
      templates: overrides.templates ?? templates,
      providers: overrides.providers ?? providers,
      selectedProviderId: overrides.selectedProviderId ?? "linux_native",
      onClose: () => undefined,
      onCreate: () => undefined,
    }),
  );
}

test("desktop create dialog keeps workspace unmounted by default", () => {
  const html = renderDialog();

  assert.match(html, /<span>Workspace access<\/span>/);
  assert.match(html, /<option value="none" selected="">None<\/option>/);
  assert.match(html, /<option value="read_only">Read only<\/option>/);
  assert.doesNotMatch(html, /read_write/);
});

test("desktop create dialog exposes request-required access policy", () => {
  const html = renderDialog();

  assert.match(html, /<option value="shared_link">Shared link<\/option>/);
  assert.match(html, /<option value="request_required">Request required<\/option>/);
});

test("desktop create dialog hides app provisioning for desktop-only templates", () => {
  const html = renderDialog();

  assert.doesNotMatch(html, /<span>Apps<\/span>/);
  assert.doesNotMatch(html, /<span>MCP servers<\/span>/);
});

test("desktop create dialog shows app provisioning for guest runtime templates", () => {
  const html = renderDialog({
    templates: [
      {
        template_id: "desktop.coding",
        name: "Coding Desktop",
        provider_requirements: [
          "sandbox.exec",
          "sandbox.files",
          "sandbox.resource_limits",
          "sandbox.desktop",
          "sandbox.desktop_input",
          "sandbox.snapshot",
        ],
        provisioning: {
          apps: ["google-chrome-stable"],
          mcp_servers: ["playwright"],
        },
      },
    ],
    providers: [
      {
        provider_id: "mac_lima",
        label: "Mac Lima",
        status: "ready",
        ready: true,
        capabilities: [
          "sandbox.exec",
          "sandbox.files",
          "sandbox.resource_limits",
          "sandbox.desktop",
          "sandbox.desktop_input",
          "sandbox.snapshot",
        ],
      },
    ],
    selectedProviderId: "mac_lima",
  });

  assert.match(html, /<span>Apps<\/span>/);
  assert.match(html, /<span>MCP servers<\/span>/);
  assert.match(html, /placeholder="google-chrome-stable"/);
  assert.match(html, /placeholder="playwright"/);
});

test("desktop create dialog honors template default starter", () => {
  const html = renderDialog({
    templates: [
      {
        template_id: "desktop.browser",
        name: "Browser Desktop",
        provider_requirements: [
          "sandbox.desktop",
          "sandbox.desktop_input",
          "sandbox.snapshot",
        ],
        desktop: {
          enabled: true,
          starter: "browser",
        },
      },
    ],
  });

  assert.match(
    html,
    /<option value="template_default" selected="">Template default \(Browser\)<\/option>/,
  );
});

test("desktop create dialog disables creation for a detected provider that is not ready", () => {
  const html = renderDialog({
    providers: [
      {
        provider_id: "linux_native",
        status: "needs_setup",
        available: true,
        installed: false,
        ready: false,
        capabilities: [
          "sandbox.desktop",
          "sandbox.desktop_input",
          "sandbox.snapshot",
        ],
      },
    ],
    selectedProviderId: "linux_native",
  });

  assert.match(
    html,
    /<option value="linux_native" disabled="">linux native<\/option>/,
  );
  assert.match(html, /<button type="submit" disabled=""/);
});

test("desktop create dialog does not fall back to incompatible templates for exec-only providers", () => {
  const html = renderDialog({
    providers: [
      {
        provider_id: "docker",
        label: "Docker",
        status: "ready",
        available: true,
        installed: true,
        ready: true,
        capabilities: ["sandbox.exec", "sandbox.files"],
      },
    ],
    selectedProviderId: "docker",
  });

  assert.match(
    html,
    /No desktop templates match the selected runtime provider/,
  );
  assert.doesNotMatch(html, /Linux Native Desktop<\/option>/);
  assert.match(html, /<option value="docker" disabled="">Docker<\/option>/);
  assert.match(html, /<button type="submit" disabled=""/);
});
