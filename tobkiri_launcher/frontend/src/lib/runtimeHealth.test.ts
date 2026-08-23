import assert from "node:assert/strict";
import test from "node:test";

import { describeRuntimeStatus, runtimeMonitorDelay } from "./runtimeHealth";
import {getRuntimeDispatchStatus, setRuntimeDispatchStatus} from "./runtimeDispatchGate";
import {useAppStore} from "@/src/store";

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

test("describeRuntimeStatus makes disconnected state canonical", () => {
  const status = describeRuntimeStatus({
    runtimeReady: false,
    runtimeStatus: "error",
    runtimeError: "connection lost",
    runtimeDisconnected: true,
    lastRuntimeHealthyAt: 30_000,
  });

  assert.equal(status.kind, "disconnected");
  assert.equal(status.tone, "danger");
  assert.equal(status.labelKey, "runtime.reconnecting_label");
  assert.equal(status.errorDetail, "connection lost");
});

test("describeRuntimeStatus returns localized keys for warmup copy", () => {
  const status = describeRuntimeStatus({
    runtimeReady: false,
    runtimeStatus: "starting",
    runtimeError: null,
    runtimeDisconnected: false,
    lastRuntimeHealthyAt: null,
  });

  assert.equal(status.kind, "warming");
  assert.equal(status.tone, "warning");
  assert.equal(status.titleKey, "runtime.warming_title");
});

test("reconfirmation is distinct and does not expose Host diagnostics", () => {
  const status = describeRuntimeStatus({
    runtimeReady: false,
    runtimeStatus: "profile_reconfirmation_required",
    runtimeError: "private Host diagnostic",
    runtimeDisconnected: false,
    lastRuntimeHealthyAt: null,
  });
  assert.equal(status.kind, "reconfirmation");
  assert.equal(status.tone, "warning");
  assert.equal(status.labelKey, "runtime.reconfirmation_label");
  assert.equal(status.errorDetail, null);
  assert.equal(runtimeMonitorDelay({
    runtimeReady: false,
    runtimeStatus: "profile_reconfirmation_required",
    runtimeError: null,
    runtimeDisconnected: false,
    lastRuntimeHealthyAt: null,
  }), 2_500);
});

test("the store cannot publish a contradictory health state to the dispatch gate", () => {
  const previousState = useAppStore.getState();
  const previousDispatchStatus = getRuntimeDispatchStatus();
  setRuntimeDispatchStatus("runtime_ready");

  assert.throws(() => useAppStore.getState().setRuntimeHealth({
    status: "error",
    needs_setup: false,
    panel_ready: true,
    runtime_ready: false,
    runtime_status: "runtime_ready",
    runtime_error: "denied",
  }), /contradictory/);
  assert.equal(getRuntimeDispatchStatus(), "error");
  assert.equal(useAppStore.getState().runtimeReady, false);
  assert.equal(useAppStore.getState().runtimeStatus, "error");

  useAppStore.setState(previousState, true);
  setRuntimeDispatchStatus(previousDispatchStatus);
});
