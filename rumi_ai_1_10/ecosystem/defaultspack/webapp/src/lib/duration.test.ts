import test from "node:test";
import assert from "node:assert/strict";

import { boundedDurationLabel, elapsedDurationLabel, formatCompactDuration, timestampMs } from "./duration";

test("formatCompactDuration uses d h m s units", () => {
  assert.equal(formatCompactDuration(900), "0s");
  assert.equal(formatCompactDuration(12_300), "12s");
  assert.equal(formatCompactDuration(125_000), "2m 5s");
  assert.equal(formatCompactDuration(7_260_000), "2h 1m");
  assert.equal(formatCompactDuration(93_600_000), "1d 2h");
});

test("duration helpers accept milliseconds, seconds, and date strings", () => {
  assert.equal(timestampMs(1_700_000_000), 1_700_000_000_000);
  assert.equal(timestampMs(1_700_000_000_000), 1_700_000_000_000);
  assert.equal(elapsedDurationLabel(1_000, 4_500), "3s");
  assert.equal(boundedDurationLabel("2026-05-19T00:00:00.000Z", "2026-05-19T00:01:02.000Z"), "1m 2s");
});
