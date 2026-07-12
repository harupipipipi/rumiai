import assert from "node:assert/strict";
import test from "node:test";

import { describeRuntimeBadge, describeRuntimeBanner, runtimeMonitorDelay } from "./runtimeHealth";

test("runtimeMonitorDelay polls slowly when the runtime is stable", () => {
  assert.equal(runtimeMonitorDelay({
    runtimeReady: true,
    runtimeStatus: "runtime_ready",
    runtimeError: null,
    runtimeDisconnected: false,
    lastRuntimeHealthyAt: 1,
  }), 15_000);
});

test("runtimeMonitorDelay polls quickly while recovering from a disconnect", () => {
  assert.equal(runtimeMonitorDelay({
    runtimeReady: false,
    runtimeStatus: "error",
    runtimeError: "connection lost",
    runtimeDisconnected: true,
    lastRuntimeHealthyAt: 1,
  }), 2_500);
});

test("describeRuntimeBadge highlights reconnecting state with an offline badge", () => {
  const badge = describeRuntimeBadge({
    runtimeReady: false,
    runtimeStatus: "error",
    runtimeError: "connection lost",
    runtimeDisconnected: true,
    lastRuntimeHealthyAt: 30_000,
  }, 90_000);

  assert.equal(badge.tone, "danger");
  assert.equal(badge.label, "Reconnecting");
  assert.equal(badge.showOfflineBadge, true);
  assert.match(badge.detail, /最後に安定していた/);
});

test("describeRuntimeBanner returns crafted warmup copy", () => {
  const banner = describeRuntimeBanner({
    runtimeReady: false,
    runtimeStatus: "starting",
    runtimeError: null,
    runtimeDisconnected: false,
    lastRuntimeHealthyAt: null,
  });

  assert.equal(banner.tone, "warning");
  assert.match(banner.title, /静かに起動中/);
});
