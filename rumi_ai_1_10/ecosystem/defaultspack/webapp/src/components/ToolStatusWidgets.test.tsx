import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ToolFilterLogWidget, ToolManagerWidget } from "./ToolStatusWidgets";

test("blocked vision tool shows reason in ToolManagerWidget", () => {
  const html = renderToStaticMarkup(
    createElement(ToolManagerWidget, {
      tools: [{ id: "vision_tool", label: "Vision Tool", category: "tool" }],
      disabledToolIds: [],
      hiddenToolIds: [],
      filterEntries: [
        {
          tool_name: "vision_tool",
          status: "blocked",
          reason_code: "model_unsupported",
          required: { model_capabilities: ["model.image_input"] },
        },
      ],
    }),
  );

  assert.match(html, /現在のモデルでは使えません/);
  assert.match(html, /Vision対応モデルに切り替えると使えます/);
});

test("ToolFilterLogWidget shows blocked tools", () => {
  const html = renderToStaticMarkup(
    createElement(ToolFilterLogWidget, {
      entries: [
        {
          tool_name: "vision_tool",
          status: "blocked",
          reason_code: "model_unsupported",
          required: { model_capabilities: ["model.image_input"] },
        },
      ],
    }),
  );

  assert.match(html, /vision_tool/);
  assert.match(html, /現在のモデルでは使えません/);
});

test("ToolFilterLogWidget shows hidden tools as hidden", () => {
  const html = renderToStaticMarkup(
    createElement(ToolFilterLogWidget, {
      entries: [
        {
          tool_name: "secret_tool",
          status: "hidden",
        },
      ],
    }),
  );

  assert.match(html, /secret_tool/);
  assert.match(html, /現在は非表示です/);
  assert.match(html, /現在の表示設定では非表示です/);
});
