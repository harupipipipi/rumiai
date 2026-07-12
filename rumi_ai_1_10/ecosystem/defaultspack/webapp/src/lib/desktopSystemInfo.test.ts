import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  fetchDesktopSystemInfo,
  isDesktopSystemInfoAvailable,
} from "./desktopSystemInfo";

function setupWindowMock(tauriMock?: unknown) {
  if (typeof (globalThis as Record<string, unknown>).window !== "object" || (globalThis as Record<string, unknown>).window === null) {
    (globalThis as Record<string, unknown>).window = {};
  }
  const win = (globalThis as Record<string, unknown>).window as Record<string, unknown>;
  if (tauriMock !== undefined) {
    win.__TAURI__ = tauriMock;
  } else {
    delete win.__TAURI__;
  }
  if (!win.location || typeof (win.location as Record<string, unknown>) !== "object") {
    win.location = { origin: "http://localhost:8766" };
  } else {
    (win.location as Record<string, unknown>).origin = "http://localhost:8766";
  }
}

describe("desktopSystemInfo", () => {
  describe("isDesktopSystemInfoAvailable", () => {
    it("returns false when window.__TAURI__ is missing", () => {
      setupWindowMock();
      assert.equal(isDesktopSystemInfoAvailable(), false);
    });

    it("returns true when window.__TAURI__.core.invoke is a function", () => {
      setupWindowMock({ core: { invoke: async () => {} } });
      assert.equal(isDesktopSystemInfoAvailable(), true);
    });
  });

  describe("fetchDesktopSystemInfo (HTTP fallback)", () => {
    it("returns null when __TAURI__ is missing and HTTP fetch fails", async () => {
      setupWindowMock();
      const savedFetch = globalThis.fetch;
      globalThis.fetch = async () => {
        throw new Error("network error");
      };
      try {
        const result = await fetchDesktopSystemInfo();
        assert.equal(result, null);
      } finally {
        globalThis.fetch = savedFetch;
      }
    });

    it("returns null when __TAURI__ is missing and HTTP response is not OK", async () => {
      setupWindowMock();
      const savedFetch = globalThis.fetch;
      globalThis.fetch = async () => new Response("{}", { status: 404 });
      try {
        const result = await fetchDesktopSystemInfo();
        assert.equal(result, null);
      } finally {
        globalThis.fetch = savedFetch;
      }
    });

    it("returns null when __TAURI__ is missing and window.location is unavailable", async () => {
      setupWindowMock();
      const win = (globalThis as Record<string, unknown>).window as Record<string, unknown>;
      win.location = null;
      const savedFetch = globalThis.fetch;
      globalThis.fetch = async () =>
        new Response(JSON.stringify({ status: "ok", data: { app_name: "X" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      try {
        const result = await fetchDesktopSystemInfo();
        assert.equal(result, null);
      } finally {
        globalThis.fetch = savedFetch;
      }
    });

    it("returns DesktopSystemInfo via HTTP fallback when response has { status, data } shape", async () => {
      setupWindowMock();
      const savedFetch = globalThis.fetch;
      const payload = {
        status: "ok",
        data: {
          app_name: "Tobkiri",
          source: "viewer_broker",
          reliable: true,
          display_version: "1.0.0",
          viewer_version: "1.0.0",
          build_channel: "beta",
          platform: "darwin",
          platform_release: "15.0",
          permissions: [
            { id: "accessibility", label: "Accessibility", status: "granted", granted: true, detail: "desc", settings_hint: "hint" },
          ],
        },
      };
      globalThis.fetch = async () =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      try {
        const result = await fetchDesktopSystemInfo();
        assert.notEqual(result, null);
        assert.equal(result!.app_name, "Tobkiri");
        assert.equal(result!.source, "viewer_broker");
        assert.equal(result!.reliable, true);
        assert.equal(result!.permissions.length, 1);
        assert.equal(result!.permissions[0].id, "accessibility");
      } finally {
        globalThis.fetch = savedFetch;
      }
    });

    it("returns DesktopSystemInfo via HTTP fallback when response is bare object", async () => {
      setupWindowMock();
      const savedFetch = globalThis.fetch;
      const payload = {
        app_name: "Tobkiri",
        source: "fallback",
        reliable: false,
        display_version: "",
        viewer_version: "1.0.0",
        build_channel: "beta",
        platform: "darwin",
        platform_release: "15.0",
        permissions: [],
      };
      globalThis.fetch = async () =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      try {
        const result = await fetchDesktopSystemInfo();
        assert.notEqual(result, null);
        assert.equal(result!.app_name, "Tobkiri");
        assert.equal(result!.reliable, false);
      } finally {
        globalThis.fetch = savedFetch;
      }
    });

    it("rejects legacy HTTP payloads without reliability metadata", async () => {
      setupWindowMock();
      const savedFetch = globalThis.fetch;
      const payload = {
        app_name: "Tobkiri",
        display_version: "",
        viewer_version: "1.0.0",
        build_channel: "beta",
        platform: "darwin",
        platform_release: "15.0",
        permissions: [],
      };
      globalThis.fetch = async () =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      try {
        const result = await fetchDesktopSystemInfo();
        assert.equal(result, null);
      } finally {
        globalThis.fetch = savedFetch;
      }
    });
  });
});
