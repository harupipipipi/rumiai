import test from "node:test";
import assert from "node:assert/strict";

import {
  AMBIENT_CAMERA_PERMISSION,
  AMBIENT_MIC_PERMISSION,
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
        [AMBIENT_MIC_PERMISSION]: { granted: Boolean(options?.rumi?.[AMBIENT_MIC_PERMISSION]) },
        [AMBIENT_CAMERA_PERMISSION]: { granted: Boolean(options?.rumi?.[AMBIENT_CAMERA_PERMISSION]) },
        "ambient.trigger.dispatch": { granted: Boolean(options?.rumi?.["ambient.trigger.dispatch"]) },
      },
      os: {
        [AMBIENT_MIC_PERMISSION]: { status: options?.os?.[AMBIENT_MIC_PERMISSION] ?? "unknown" },
        [AMBIENT_CAMERA_PERMISSION]: { status: options?.os?.[AMBIENT_CAMERA_PERMISSION] ?? "unknown" },
      },
    },
  };
}

const allRumi = {
  [AMBIENT_MIC_PERMISSION]: true,
  [AMBIENT_CAMERA_PERMISSION]: true,
  "ambient.trigger.dispatch": true,
};

const allOs = {
  [AMBIENT_MIC_PERMISSION]: "granted",
  [AMBIENT_CAMERA_PERMISSION]: "granted",
};

test("deriveAmbientUiState guides first-run users to setup before showing off", () => {
  assert.equal(deriveAmbientUiState(status(), "off"), "setupNeeded");
});

test("deriveAmbientUiState separates Rumi permission setup from OS permission setup", () => {
  assert.equal(deriveAmbientUiState(status({ rumi: allRumi }), "off"), "osPermissionNeeded");
  assert.equal(deriveAmbientUiState(status({ os: allOs }), "off"), "rumiPermissionNeeded");
});

test("deriveAmbientUiState keeps first-run setup visible even when browser OS permission is denied", () => {
  const firstRunWithDeniedBrowserPermission = status({
    os: { [AMBIENT_MIC_PERMISSION]: "denied", [AMBIENT_CAMERA_PERMISSION]: "denied" },
  });

  assert.equal(deriveAmbientUiState(firstRunWithDeniedBrowserPermission, "off"), "setupNeeded");
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
    os: { [AMBIENT_MIC_PERMISSION]: "denied", [AMBIENT_CAMERA_PERMISSION]: "granted" },
  });
  assert.equal(osPermissionBucket(denied, AMBIENT_MIC_PERMISSION), "denied");
  assert.equal(deriveAmbientUiState(denied, "off"), "denied");

  const blocked = status({
    rumi: { ...allRumi, [AMBIENT_CAMERA_PERMISSION]: false },
    os: allOs,
  });
  blocked.permissions.rumi[AMBIENT_CAMERA_PERMISSION].status = "blocked";
  assert.equal(rumiPermissionBucket(blocked, AMBIENT_CAMERA_PERMISSION), "blocked");
  assert.equal(deriveAmbientUiState(blocked, "off"), "blocked");
});
