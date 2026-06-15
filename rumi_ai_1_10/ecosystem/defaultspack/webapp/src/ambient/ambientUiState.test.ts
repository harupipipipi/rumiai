import test from "node:test";
import assert from "node:assert/strict";

import {
  deriveAmbientUiState,
  osPermissionBucket,
  rumiPermissionBucket,
  type AmbientRuntimeStatus,
} from "./ambientUiState";
import type { AmbientStatus } from "./ambientTriggerClient";

function status(options?: {
  rumi?: Partial<Record<string, boolean>>;
  os?: Partial<Record<string, string>>;
  enabled?: boolean;
}): AmbientStatus {
  return {
    ambient_monitor: { enabled: Boolean(options?.enabled) },
    services: {
      voice_wake_monitor: { status: options?.enabled ? "listening" : "paused" },
      gesture_wake_monitor: { status: options?.enabled ? "listening" : "paused" },
    },
    permissions: {
      rumi: {
        "microphone.capture": { granted: Boolean(options?.rumi?.["microphone.capture"]) },
        "camera.capture": { granted: Boolean(options?.rumi?.["camera.capture"]) },
        "ambient.trigger.dispatch": { granted: Boolean(options?.rumi?.["ambient.trigger.dispatch"]) },
      },
      os: {
        "microphone.capture": { status: options?.os?.["microphone.capture"] ?? "unknown" },
        "camera.capture": { status: options?.os?.["camera.capture"] ?? "unknown" },
      },
    },
  };
}

const allRumi = {
  "microphone.capture": true,
  "camera.capture": true,
  "ambient.trigger.dispatch": true,
};

const allOs = {
  "microphone.capture": "granted",
  "camera.capture": "granted",
};

test("deriveAmbientUiState guides first-run users to setup before showing off", () => {
  assert.equal(deriveAmbientUiState(status(), "off"), "setupNeeded");
});

test("deriveAmbientUiState separates Rumi permission setup from OS permission setup", () => {
  assert.equal(deriveAmbientUiState(status({ rumi: allRumi }), "off"), "osPermissionNeeded");
  assert.equal(deriveAmbientUiState(status({ os: allOs }), "off"), "rumiPermissionNeeded");
});

test("deriveAmbientUiState distinguishes off, monitoring, recording, and sending", () => {
  const ready = status({ rumi: allRumi, os: allOs });
  const cases: Array<[AmbientRuntimeStatus, string]> = [
    ["off", "readyOff"],
    ["monitoring", "monitoring"],
    ["recording", "recording"],
    ["sending", "sending"],
  ];
  for (const [runtime, expected] of cases) {
    assert.equal(deriveAmbientUiState(ready, runtime), expected);
  }
});

test("permission buckets keep denied and blocked distinct from missing setup", () => {
  const denied = status({
    rumi: allRumi,
    os: { "microphone.capture": "denied", "camera.capture": "granted" },
  });
  assert.equal(osPermissionBucket(denied, "microphone.capture"), "denied");
  assert.equal(deriveAmbientUiState(denied, "off"), "denied");

  const blocked = status({
    rumi: { ...allRumi, "camera.capture": false },
    os: allOs,
  });
  blocked.permissions.rumi["camera.capture"].status = "blocked";
  assert.equal(rumiPermissionBucket(blocked, "camera.capture"), "blocked");
  assert.equal(deriveAmbientUiState(blocked, "off"), "blocked");
});
