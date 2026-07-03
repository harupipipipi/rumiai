import test from "node:test";
import assert from "node:assert/strict";

import { diagnosticsText, runtimeAvailability } from "./runtimeStatus";
import { normalizeDesktopStatus } from "./types";

test("runtimeAvailability does not treat available provider as ready without ready flag", () => {
  const availability = runtimeAvailability(
    {
      providers: [
        {
          provider_id: "linux_native",
          status: "available",
          available: true,
          installed: true,
          ready: false,
        },
      ],
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
          provider_id: "mac_lima",
          label: "Mac Lima",
          status: "ready",
          available: true,
          installed: true,
          ready: true,
          capabilities: [
            "sandbox.desktop",
            "sandbox.desktop_input",
            "sandbox.snapshot",
          ],
        },
      ],
      selected_provider_id: "linux_native",
    },
    null,
    null,
  );

  assert.equal(availability.status, "ready");
  assert.equal(availability.selectedProvider?.provider_id, "mac_lima");
  assert.equal(availability.message, "Mac Lima is ready.");
});

test("runtimeAvailability treats whitespace capability strings as desktop capable", () => {
  const availability = runtimeAvailability(
    {
      providers: [
        {
          provider_id: "windows_wsl",
          label: "RumiUbuntu WSL2",
          status: "ready",
          available: true,
          installed: true,
          ready: true,
          selected: true,
          capabilities: "sandbox.desktop sandbox.desktop_input sandbox.exec sandbox.snapshot",
        },
      ],
      selected_provider_id: "windows_wsl",
    },
    null,
    null,
  );

  assert.equal(availability.status, "ready");
  assert.equal(availability.selectedProvider?.provider_id, "windows_wsl");
  assert.equal(availability.message, "RumiUbuntu WSL2 is ready.");
});

test("runtimeAvailability does not treat exec-only ready provider as desktop ready", () => {
  const availability = runtimeAvailability(
    {
      providers: [
        {
          provider_id: "linux_native",
          status: "needs_setup",
          available: true,
          installed: false,
          ready: false,
          capabilities: [
            "sandbox.desktop",
            "sandbox.desktop_input",
            "sandbox.snapshot",
          ],
        },
        {
          provider_id: "docker",
          label: "Docker",
          status: "ready",
          available: true,
          installed: true,
          ready: true,
          capabilities: ["sandbox.exec", "sandbox.files"],
        },
      ],
      selected_provider_id: "linux_native",
    },
    null,
    null,
  );

  assert.equal(availability.status, "needs_setup");
  assert.equal(availability.selectedProvider?.provider_id, "linux_native");
});

test("normalizeDesktopStatus maps sandbox ready and busy states to running", () => {
  assert.equal(normalizeDesktopStatus("ready"), "running");
  assert.equal(normalizeDesktopStatus("busy"), "running");
  assert.equal(normalizeDesktopStatus("not-a-status"), "unknown");
});

test("diagnosticsText redacts secret-like diagnostic values", () => {
  const text = diagnosticsText({
    providersResponse: {
      providers: [
        {
          provider_id: "linux_native",
          status: "error",
          diagnostics: {
            api_key: "sk-test-secret",
            nested: { accessToken: "runtime-token" },
            safe: "visible",
          },
        },
      ],
    },
    doctor: {
      status: "error",
      diagnostics: {
        credential_ref: "credential-secret",
        command: "xvfb",
      },
    },
    error: "plain error",
  });

  assert.match(text, /"safe": "visible"/);
  assert.match(text, /"command": "xvfb"/);
  assert.match(text, /\[redacted\]/);
  assert.doesNotMatch(text, /sk-test-secret/);
  assert.doesNotMatch(text, /runtime-token/);
  assert.doesNotMatch(text, /credential-secret/);
});
