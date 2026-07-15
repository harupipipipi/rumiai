import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { layerClassName } from "../../ui/layers/layerTokens";

test("notification center keeps filter, search, navigation, mark-all, and toast layer contracts", () => {
  const source = readFileSync(new URL("./AgentNotificationCenter.tsx", import.meta.url), "utf8");
  assert.match(source, /label: "見るべき"/);
  assert.match(source, /placeholder="タイトル・内容・toolで検索"/);
  assert.match(source, /window\.location\.assign/);
  assert.match(source, /onClick=\{markAllRead\}/);
  assert.match(source, /layerClassName\.toast/);
  assert.match(source, /mx-3 mt-3 flex/);
  assert.doesNotMatch(source, /absolute right-3 top-/);
  assert.match(source, /listAgentNotifications/);
  assert.match(source, /30_000/);
  assert.doesNotMatch(source, /rumi-pending-chat-requests/);
  assert.match(source, /READ_STATE_STORAGE_KEY}:\$\{storageNamespace/);
  assert.equal(layerClassName.toast, "rumi-layer-toast");
});
