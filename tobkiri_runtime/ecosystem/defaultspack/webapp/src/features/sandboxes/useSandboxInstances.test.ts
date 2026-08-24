import test from "node:test";
import assert from "node:assert/strict";

import type { DesktopInstance } from "./types";
import {
  desktopRefreshFailed,
  desktopRefreshSucceeded,
} from "./useSandboxInstances";

function desktop(seatId: string): DesktopInstance {
  return {
    seat_id: seatId,
    name: `Desktop ${seatId}`,
    status: "running",
    provider_id: "linux_native",
  };
}

test("initial desktop failure is identified without inventing an empty success", () => {
  const snapshot = desktopRefreshFailed([], new Error("Backend unavailable."));

  assert.deepEqual(snapshot.desktops, []);
  assert.match(snapshot.error ?? "", /^Unable to load desktop seats\./);
  assert.match(snapshot.error ?? "", /Backend unavailable\./);
  assert.doesNotMatch(snapshot.error ?? "", /last available snapshots/);
});

test("refresh failure preserves seats and explains that snapshots are retained", () => {
  const previous = [desktop("seat-live")];
  const snapshot = desktopRefreshFailed(previous, new Error("Refresh timed out."), {
    hasSuccessfulRequest: true,
  });

  assert.equal(snapshot.desktops, previous);
  assert.match(snapshot.error ?? "", /^Unable to refresh desktop seats\./);
  assert.match(snapshot.error ?? "", /Showing the last available snapshots\./);
});

test("successful retry publishes fresh seats and clears the prior error", () => {
  const failed = desktopRefreshFailed([], new Error("Backend unavailable."));
  assert.notEqual(failed.error, null);

  const recovered = desktopRefreshSucceeded([desktop("seat-live")]);

  assert.equal(recovered.desktops[0]?.seat_id, "seat-live");
  assert.equal(recovered.error, null);
});

test("failed refresh after a successful empty result is not relabeled as bootstrap", () => {
  const snapshot = desktopRefreshFailed([], new Error("Refresh timed out."), {
    hasSuccessfulRequest: true,
  });

  assert.deepEqual(snapshot.desktops, []);
  assert.match(snapshot.error ?? "", /^Unable to refresh desktop seats\./);
  assert.match(snapshot.error ?? "", /last completed snapshot was empty/);
});

test("repeated bootstrap failures remain initial-load failures until a snapshot succeeds", () => {
  const firstFailure = desktopRefreshFailed([], new Error("First failure."));
  const repeatedFailure = desktopRefreshFailed([], new Error("Second failure."));

  assert.match(firstFailure.error ?? "", /^Unable to load desktop seats\./);
  assert.match(repeatedFailure.error ?? "", /^Unable to load desktop seats\./);
  assert.doesNotMatch(repeatedFailure.error ?? "", /Unable to refresh/);
});

test("successful empty response is distinct from a pending or failed request", () => {
  const snapshot = desktopRefreshSucceeded([]);

  assert.deepEqual(snapshot, { desktops: [], error: null });
});
