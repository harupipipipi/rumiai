import test from "node:test";
import assert from "node:assert/strict";

import { authorityApprovalTitle } from "./authorityApproval";

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
