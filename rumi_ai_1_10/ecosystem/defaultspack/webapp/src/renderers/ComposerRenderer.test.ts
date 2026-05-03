import test from "node:test";
import assert from "node:assert/strict";

import { filterAtMentionFiles, resolveComposerWidgetDrop } from "./ComposerRenderer";
import { COMPOSER_TOGGLE_DROP } from "../lib/toolUi";

test("composer file mention filters string context files", () => {
  const files = ["README.md", "src/App.tsx", "docs/context.md"];

  assert.deepEqual(filterAtMentionFiles(files, "md"), ["README.md", "docs/context.md"]);
  assert.equal(typeof filterAtMentionFiles(files, "")[0], "string");
});

test("composer model drop selects the model instead of creating a widget chip", () => {
  const action = resolveComposerWidgetDrop(
    { id: "openai/gpt-4.1", type: "model", label: "GPT 4.1" },
    [],
  );

  assert.deepEqual(action, { type: "select_model", profileId: "openai/gpt-4.1" });
});

test("composer tool drop requires explicit toggle capability", () => {
  const toolItems = [
    {
      id: "coding_file_read",
      label: "Read File",
      ui: { widget_kind: "tool_toggle", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
    {
      id: "future_panel",
      label: "Future Panel",
      ui: { widget_kind: "panel", drop_capabilities: [COMPOSER_TOGGLE_DROP] },
    },
  ];

  assert.equal(resolveComposerWidgetDrop({ id: "coding_file_read", type: "tool", label: "Read" }, toolItems).type, "drop_widget");
  assert.equal(resolveComposerWidgetDrop({ id: "future_panel", type: "tool", label: "Future" }, toolItems).type, "ignore");
  assert.equal(resolveComposerWidgetDrop({ id: "unknown", type: "button", label: "Unknown" }, toolItems).type, "ignore");
});
