import test from "node:test";
import assert from "node:assert/strict";

import { browserProfileKey, formatBytes, summarizeBrowserProfile } from "./BrowserProfileManager";

test("browser profile helpers normalize ids and active profile state", () => {
  const profile = {
    id: "internal",
    profile_id: "default",
    label: "Default",
    cookie_count: 3,
    cache_bytes: 2048,
  };

  assert.equal(browserProfileKey(profile), "default");
  assert.deepEqual(summarizeBrowserProfile(profile, "default"), {
    id: "default",
    label: "Default",
    active: true,
    storageLabel: "2.0 KB",
    cookiesLabel: "3 cookies",
  });
});

test("browser profile byte labels stay compact", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(1536), "1.5 KB");
  assert.equal(formatBytes(2 * 1024 * 1024), "2.0 MB");
});
