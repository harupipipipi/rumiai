import test from "node:test";
import assert from "node:assert/strict";

import { mergeDesktopLeaseRenewal } from "./useDesktopControlLease";

test("mergeDesktopLeaseRenewal preserves the acquire-only lease token", () => {
  const merged = mergeDesktopLeaseRenewal(
    {
      seat_id: "seat-1",
      lease_id: "lease-1",
      lease_token: "secret-token",
      expires_at: "2026-01-01T00:00:00Z",
    },
    {
      seat_id: "seat-1",
      lease_id: "lease-1",
      expires_at: "2026-01-01T00:00:10Z",
    },
  );

  assert.equal(merged?.lease_token, "secret-token");
  assert.equal(merged?.expires_at, "2026-01-01T00:00:10Z");
});
