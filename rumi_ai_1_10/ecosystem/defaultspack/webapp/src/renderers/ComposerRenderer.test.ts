import test from "node:test";
import assert from "node:assert/strict";

import { filterAtMentionFiles, insertAtMentionText, resolveComposerWidgetDrop } from "./ComposerRenderer";
import { COMPOSER_BUTTON_DROP, COMPOSER_PANEL_DROP, COMPOSER_SELECTOR_DROP, COMPOSER_TOGGLE_DROP } from "../lib/toolUi";

test("composer file mention filters string context files", () => {
  const files = ["README.md", "src/App.tsx", "docs/context.md"];

  assert.deepEqual(filterAtMentionFiles(files, "md"), ["README.md", "docs/context.md"]);
  assert.equal(typeof filterAtMentionFiles(files, "")[0], "string");
});

test("composer file mention insertion keeps @ text for workspace attachment flow", () => {
  const result = insertAtMentionText("please @REA now", 11, "README.md");

  assert.deepEqual(result, {
    value: "please @README.md  now",
    cursor: 18,
  });
});

test("composer model drop selects the model instead of creating a widget chip", () => {
  const action = resolveComposerWidgetDrop(
    { id: "openai/gpt-4.1", type: "model", label: "GPT 4.1" },
    [],
  );

  assert.deepEqual(action, { type: "select_model", profileId: "openai/gpt-4.1" });
});

test("composer widget drop requires explicit kind capability contract", () => {
  const toolItems = [
    {
      id: "coding_file_read",
      label: "Read File",
      ui: { widget_kind: "tool_toggle", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
    {
      id: "git_status",
      label: "Git Status",
      ui: { widget_kind: "button", drop_capabilities: [COMPOSER_BUTTON_DROP] },
    },
    {
      id: "provider-catalog",
      label: "Providers",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_PANEL_DROP] },
    },
    {
      id: "model-selector",
      label: "Model Selector",
      ui: { widget_kind: "selector", drop_capabilities: [COMPOSER_SELECTOR_DROP] },
    },
    {
      id: "bad-panel",
      label: "Bad Panel",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
  ];

  assert.equal(resolveComposerWidgetDrop({ id: "coding_file_read", type: "tool", label: "Read" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "git_status", type: "button", label: "Git", widgetKind: "button" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "provider-catalog", type: "panel", label: "Providers", widgetKind: "panel" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "model-selector", type: "selector", label: "Models", widgetKind: "selector" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "bad-panel", type: "panel", label: "Bad", widgetKind: "panel" }, toolItems).type, "ignore");
  assert.equal(resolveComposerWidgetDrop({ id: "unknown", type: "button", label: "Unknown" }, toolItems).type, "ignore");
});
