import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { UICatalog } from "./api";
import { hasShellRegion, shellRendererForRegion, shellRegions } from "./uiShell";

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function readSource(relativePath: string): string {
  return fs.readFileSync(path.join(sourceRoot, relativePath), "utf8");
}

function cssBlock(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

const catalog: UICatalog = {
  shell: {
    layout: {
      id: "custom",
      regions: [
        { id: "composer", renderer: "composer", order: 30 },
        { id: "history", renderer: "history_board", order: 10 },
        { id: "right_sidebar", renderer: "right_sidebar", order: 20, enabled: false },
      ],
    },
    renderers: [
      { id: "history_board", component: "HistoryBoard" },
      { id: "composer", component: "Composer" },
    ],
  },
  sidebar: { filters: [], items: [] },
  settings: { sections: [], values: {} },
  chat_rendering: { renderers: [] },
  extension_points: [],
};

test("shellRegions filters disabled regions and preserves configured order", () => {
  assert.deepEqual(shellRegions(catalog).map((region) => region.id), ["history", "composer"]);
});

test("hasShellRegion reads visible shell regions", () => {
  assert.equal(hasShellRegion(catalog, "history"), true);
  assert.equal(hasShellRegion(catalog, "right_sidebar"), false);
});

test("shellRendererForRegion resolves renderer metadata", () => {
  assert.equal(shellRendererForRegion(catalog, "composer")?.component, "Composer");
  assert.equal(shellRendererForRegion(catalog, "missing"), null);
});

test("defaultspack scroll contract keeps document fallback outside pane scrollers", () => {
  const css = readSource("index.css");
  const bodyBlock = cssBlock(css, "body");

  assert.match(bodyBlock, /overflow-y:\s*auto/);
  assert.doesNotMatch(bodyBlock, /overflow:\s*hidden/);
  assert.match(css, /\.rumi-app-shell,\s*\.rumi-page-shell\s*\{[^}]*height:\s*100dvh[^}]*overflow-y:\s*auto/s);
  assert.match(css, /Defaultspack scroll ownership contract/);
});

test("top-level defaultspack route shells use the shared scroll contract", () => {
  const app = readSource("App.tsx");
  const promptStudio = readSource("pages/PromptStudio.tsx");
  const hostPermissions = readSource("hostPermissions/HostPermissionsPage.tsx");
  const ambient = readSource("ambient/AmbientTriggerPanel.tsx");
  const consoleWindow = readSource("ambient/DefaultsConsoleWindow.tsx");
  const chatMessages = readSource("renderers/ChatMessagesRenderer.tsx");

  assert.match(app, /rumi-app-shell/);
  assert.doesNotMatch(app, /flex flex-col h-screen w-full[^"]*overflow-hidden/);
  assert.match(app, /rumi-workspace-main[^"]*min-h-0/);
  assert.match(app, /rumi-chat-pane[^"]*min-h-0/);

  for (const source of [promptStudio, hostPermissions, ambient, consoleWindow]) {
    assert.match(source, /rumi-page-shell/);
  }

  assert.match(chatMessages, /rumi-chat-scroll-pane[^"]*overflow-y-auto/);
});
