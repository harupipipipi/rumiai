import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { AuthorityRequest } from "../lib/api";
import type { DesktopSystemInfo } from "../lib/desktopSystemInfo";
import { buildHostPermissionRows, hostPermissionSummary } from "./hostPermissions";

function desktopInfo(overrides: Partial<DesktopSystemInfo> = {}): DesktopSystemInfo {
  return {
    source: "viewer_tauri",
    reliable: true,
    app_name: "Rumi AI",
    display_version: "1.0.0",
    viewer_version: "1.0.0",
    build_channel: "dev",
    platform: "darwin",
    platform_release: "15.0",
    permissions: [],
    ...overrides,
  };
}

function authorityRequest(overrides: Partial<AuthorityRequest>): AuthorityRequest {
  return {
    request_id: "req-1",
    status: "pending",
    principal_id: "local:user",
    permission_id: "host.screen.capture",
    resource: {},
    reason: "",
    risk_level: "high",
    created_at: "2026-06-15T00:00:00.000Z",
    ...overrides,
  };
}

describe("host permissions", () => {
  it("builds rows from desktop host permissions and OS permission aliases", () => {
    const rows = buildHostPermissionRows(desktopInfo({
      host_permissions: {
        "host.microphone.capture": {
          id: "host.microphone.capture",
          rumi_granted: true,
          os_status: "granted",
          stream_allowed: true,
          required_by_functions: ["ambient_monitor_start"],
        },
      },
      permissions: [
        { id: "screen_recording", label: "Screen Recording", status: "missing", granted: false, detail: "", settings_hint: "" },
      ],
    }));

    const microphone = rows.find((row) => row.id === "host.microphone.capture");
    assert.equal(microphone?.rumiStatus, "approved");
    assert.equal(microphone?.osStatus, "approved");
    assert.deepEqual(microphone?.requiredByFunctions, ["ambient_monitor_start"]);

    const screen = rows.find((row) => row.id === "host.screen.capture");
    assert.equal(screen?.osStatus, "missing");
    assert.equal(screen?.streamAllowed, true);
  });

  it("uses latest matching authority request for Rumi approval status", () => {
    const rows = buildHostPermissionRows(
      desktopInfo(),
      [
        authorityRequest({ request_id: "old", status: "denied", created_at: "2026-06-14T00:00:00.000Z" }),
        authorityRequest({ request_id: "new", status: "approved", created_at: "2026-06-15T00:00:00.000Z" }),
      ],
    );

    const screen = rows.find((row) => row.id === "host.screen.capture");
    assert.equal(screen?.rumiStatus, "approved");
  });

  it("summarizes approvals and treats clipboard OS permission as not required", () => {
    const rows = buildHostPermissionRows(desktopInfo({
      host_permissions: [
        { id: "host.clipboard.*", rumi_status: "approved", stream_allowed: false },
      ],
    }));
    const clipboard = rows.find((row) => row.id === "host.clipboard.*");
    assert.equal(clipboard?.osStatus, "unsupported");

    const summary = hostPermissionSummary(rows);
    assert.equal(summary.total, 6);
    assert.equal(summary.approved, 1);
    assert.equal(summary.osReady, 1);
  });
});
