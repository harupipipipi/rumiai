import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  CommandResultNotice,
  statusCommandResultMessage,
} from "./CommandResultNotice";

test("status command result includes model mode tools and context", () => {
  const message = statusCommandResultMessage({
    mode: "coding",
    modelLabel: "Tobkiri Test Model",
    thinkingLevel: "medium",
    deepthinkEnabled: false,
    yoloMode: true,
    ultraYoloMode: false,
    selectedToolLabels: ["Terminal", "Git"],
    contextUsage: {
      usedTokens: 1200,
      maxContext: 8000,
      ratio: 0.15,
      label: "15%",
    },
  });

  assert.match(message, /^status:/);
  assert.match(message, /mode=coding/);
  assert.match(message, /model=Tobkiri Test Model/);
  assert.match(message, /thinking=medium/);
  assert.match(message, /tools=2 selected \(Terminal, Git\)/);
  assert.match(message, /context=1200 \/ 8000 tokens \(15%\)/);
});

test("status command result describes empty and unknown values", () => {
  const message = statusCommandResultMessage({
    mode: "agent",
    modelLabel: " ",
    thinkingLevel: null,
    deepthinkEnabled: true,
    yoloMode: false,
    ultraYoloMode: false,
    selectedToolLabels: ["", "  "],
    contextUsage: { usedTokens: 0, maxContext: 0, ratio: 0, label: "?" },
  });

  assert.match(message, /model=unknown/);
  assert.match(message, /thinking=none/);
  assert.match(message, /deepthink=on/);
  assert.match(message, /tools=0 selected/);
  assert.match(message, /context=0 tokens \/ unknown/);
});

test("command result notice is a polite persistent status with an accessible dismiss control", () => {
  const html = renderToStaticMarkup(createElement(CommandResultNotice, {
    message: "status:\nmode=agent",
    onDismiss: () => undefined,
  }));

  assert.match(html, /role="status"/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /aria-atomic="true"/);
  assert.match(html, /data-command-result-notice="status"/);
  assert.match(html, /status:/);
  assert.match(html, /mode=agent/);
  assert.match(html, /aria-label="ステータス結果を閉じる"/);
});
