import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CompanyAgentList } from "../components/company/CompanyAgentList";
import { defaultspackRendererIds, defaultspackRenderers, resolveDefaultspackRenderers } from "./defaultspackRenderers";

test("defaultspack renderer registry covers visible shell regions", () => {
  assert.deepEqual([...defaultspackRendererIds].sort(), [
    "activity_preview",
    "chat_header",
    "chat_messages",
    "composer",
    "history",
    "right_sidebar",
    "settings_modal",
    "title_bar",
  ]);
});

test("defaultspack renderer registry exposes render modules", () => {
  assert.equal(typeof defaultspackRenderers.titleBar, "function");
  assert.equal(typeof defaultspackRenderers.historyBoard, "function");
  assert.equal(typeof defaultspackRenderers.chatHeader, "function");
  assert.equal(typeof defaultspackRenderers.chatMessages, "function");
  assert.equal(typeof defaultspackRenderers.composer, "function");
  assert.equal(typeof defaultspackRenderers.toolPreviewPanel, "function");
  assert.equal(typeof defaultspackRenderers.rightSidebar, "function");
  assert.equal(typeof defaultspackRenderers.settingsModal, "function");
});

test("defaultspack renderer resolver keeps builtin fallback for untrusted modules", () => {
  const resolved = resolveDefaultspackRenderers({
    shell: {
      layout: {
        id: "test",
        regions: [
          { id: "composer", renderer: "custom_composer", enabled: true },
        ],
      },
      renderers: [
        {
          id: "custom_composer",
          component: "CustomComposer",
          module: "https://example.com/composer.js",
          trust: "local",
        },
      ],
    },
    sidebar: { filters: [], items: [] },
    settings: { sections: [], values: {} },
    chat_rendering: { renderers: [] },
    extension_points: [],
  });

  assert.equal(resolved.composer, defaultspackRenderers.composer);
});

test("company agent list renders operational role details", () => {
  const html = renderToStaticMarkup(
    createElement(CompanyAgentList, {
      agents: [
        {
          agent_id: "reviewer",
          display_name: "Reviewer",
          role_key: "reviewer",
          model: "stub/default",
          allowed_tools: ["coding_git_diff"],
          aliases: ["review"],
        },
      ],
    }),
  );

  assert.match(html, /Reviewer/);
  assert.match(html, /@review/);
});
