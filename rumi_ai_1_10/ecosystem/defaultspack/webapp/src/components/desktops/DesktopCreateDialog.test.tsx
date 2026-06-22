import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { RuntimeProviderStatus, SandboxTemplate } from "../../features/sandboxes/types";
import { DesktopCreateDialog } from "./DesktopCreateDialog";

const templates: SandboxTemplate[] = [{
  template_id: "desktop.linux_native",
  name: "Linux Native Desktop",
  provider_requirements: ["sandbox.desktop", "sandbox.desktop_input", "sandbox.snapshot"],
}];

const providers: RuntimeProviderStatus[] = [{
  provider_id: "linux_native",
  status: "ready",
  ready: true,
  capabilities: ["sandbox.desktop", "sandbox.desktop_input", "sandbox.snapshot"],
}];

function renderDialog(): string {
  return renderToStaticMarkup(
    createElement(DesktopCreateDialog, {
      isOpen: true,
      templates,
      providers,
      selectedProviderId: "linux_native",
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
