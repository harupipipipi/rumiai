import test from "node:test";
import assert from "node:assert/strict";

import { authorityApprovalConfig, authorityApprovalRiskTone, authorityApprovalTitle } from "./authorityApproval";

test("authority approval title describes app provider key and endpoint without duplicating provider", () => {
  const title = authorityApprovalTitle({
    permissionId: "model.invoke",
    resource: {
      app_display_name: "defaultspack v2",
      provider_display_name: "OpenCode Go provider",
      model_display_name: "DeepSeek V4 Pro via OpenCode Go",
      credential_label: "OpenCode Go API key",
      endpoint_url: "https://opencode.ai/zen/go/v1/chat/completions",
    },
  });

  assert.equal(
    title,
    "defaultspack v2 / OpenCode Go provider に OpenCode Go API key の使用と https://opencode.ai/zen/go/v1/chat/completions へのアクセスを許可しますか？",
  );
  assert.equal(title.includes("provider provider"), false);
});

test("authority approval config accumulates distinct host action aliases", () => {
  assert.deepEqual(
    authorityApprovalConfig({
      permissionId: "host.process.open_url",
      resource: {
        host_action: "host.process.open_url",
        operation: "host.process.open_url.preview",
      },
    }),
    {
      host_actions: ["host.process.open_url", "host.process.open_url.preview"],
    },
  );
});

test("authority approval config dedupes matching host action aliases", () => {
  assert.deepEqual(
    authorityApprovalConfig({
      permissionId: "host.process.open_url",
      resource: {
        host_action: "host.process.open_url",
        operation: "host.process.open_url",
      },
    }),
    {
      host_actions: ["host.process.open_url"],
    },
  );
});

test("authority approval risk tones render critical and high as danger", () => {
  assert.match(authorityApprovalRiskTone("critical"), /red-600/);
  assert.match(authorityApprovalRiskTone("critical"), /ring-red/);
  assert.match(authorityApprovalRiskTone("high"), /red-500/);
  assert.doesNotMatch(authorityApprovalRiskTone("critical"), /sky/);
  assert.doesNotMatch(authorityApprovalRiskTone("high"), /sky/);
});
