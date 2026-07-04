import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DashboardHealthWidget, ToolFilterLogWidget, ToolManagerWidget } from "./ToolStatusWidgets";

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

test("DashboardHealthWidget renders approval and provider failure primitives", () => {
  const html = renderToStaticMarkup(
    createElement(DashboardHealthWidget, {
      health: {
        provider: {
          count: 1,
          configured_count: 0,
          providers: [
            {
              provider_id: "openai",
              label: "OpenAI",
              configured: false,
              auth_mode: "api_key",
              key_source: "missing",
              failure: {
                code: "PROVIDER_AUTH_MISSING",
                message: "Provider credentials are not configured.",
              },
            },
          ],
        },
        approval: { pending: 2, denied: 1, risky: 1, replayed: 0 },
        gateway: { local_url: "http://127.0.0.1", tunnel_url: "missing", webhook_url: "configured", active_devices: 1 },
        runtime: { status: "DEGRADED", probe_count: 1 },
      },
    }),
  );

  assert.match(html, /PROVIDER_AUTH_MISSING/);
  assert.match(html, /Approval center/);
  assert.match(html, /denied 1/);
  assert.doesNotMatch(html, /sk-/);
});
