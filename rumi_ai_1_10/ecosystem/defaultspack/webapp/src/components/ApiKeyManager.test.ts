import test from "node:test";
import assert from "node:assert/strict";

import { apiKeySortKey, safeApiKeyDisplay } from "./ApiKeyManager";
import type { ApiKeySummary } from "../lib/api";

test("api key display never exposes raw-looking configured values", () => {
  const rawLookingKey = {
    id: "k1",
    provider_id: "openrouter",
    configured: true,
    redacted: "sk-or-v1-secret",
  } satisfies ApiKeySummary;

  assert.equal(safeApiKeyDisplay(rawLookingKey), "Saved");
  assert.equal(safeApiKeyDisplay({ ...rawLookingKey, redacted: "sk-or****abcd" }), "sk-or****abcd");
  assert.equal(safeApiKeyDisplay({ ...rawLookingKey, configured: false }), "Not set");
});

test("configured api keys sort before missing keys", () => {
  const configured = apiKeySortKey({ id: "a", provider_id: "google", configured: true });
  const missing = apiKeySortKey({ id: "b", provider_id: "google", configured: false });

  assert.equal(configured < missing, true);
});
