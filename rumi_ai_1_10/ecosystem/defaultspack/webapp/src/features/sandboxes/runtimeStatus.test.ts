import test from "node:test";
import assert from "node:assert/strict";

import { runtimeAvailability } from "./runtimeStatus";
import { normalizeDesktopStatus } from "./types";

test("runtimeAvailability does not treat available provider as ready without ready flag", () => {
  const availability = runtimeAvailability(
    {
      providers: [{
        provider_id: "linux_native",
        status: "available",
        available: true,
        installed: true,
        ready: false,
      }],
      selected_provider_id: "linux_native",
    },
    null,
    null,
  );

  assert.equal(availability.status, "unavailable");
});

test("runtimeAvailability selects a ready provider when the preferred provider still needs setup", () => {
  const availability = runtimeAvailability(
    {
      providers: [
        {
          provider_id: "linux_native",
          status: "needs_setup",
          available: true,
          installed: false,
          ready: false,
        },
        {
          provider_id: "docker",
          label: "Docker",
          status: "ready",
          available: true,
          installed: true,
          ready: true,
        },
      ],
      selected_provider_id: "linux_native",
    },
    null,
    null,
  );

  assert.equal(availability.status, "ready");
  assert.equal(availability.selectedProvider?.provider_id, "docker");
  assert.equal(availability.message, "Docker is ready.");
});

test("normalizeDesktopStatus maps sandbox ready and busy states to running", () => {
  assert.equal(normalizeDesktopStatus("ready"), "running");
  assert.equal(normalizeDesktopStatus("busy"), "running");
  assert.equal(normalizeDesktopStatus("not-a-status"), "unknown");
});
