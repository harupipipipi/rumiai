from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_companion_background_supports_search_home_candidate_navigation():
    extension_root = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
    )
    background = (extension_root / "background.js").read_text(encoding="utf-8")
    manifest = (extension_root / "manifest.json").read_text(encoding="utf-8")
    policy = (extension_root / "bridge_url_policy.js").read_text(encoding="utf-8")

    assert 'import "./bridge_url_policy.js";' in background
    assert '"bridge_url_policy.js"' in manifest
    assert "rumi:search-home:set-route-state" in background
    assert "rumi:search-home:get-route-state" in background
    assert "rumi:search-home:advance-candidate" in background
    assert "SEARCH_HOME_ROUTE_STATE_KEY" in background
    assert "trustedSearchHomeSourceOrigin" in background
    assert "isTrustedStoredSearchHomeRouteState(current)" in background
    assert "RumiBridgeUrlPolicy.normalizeNavigationUrl(value)" in background
    assert 'chrome.tabs.update(tabId, { url })' in background
    assert "validateNavigationUrl" in policy
    assert "Navigation URL must not use a local or private host." in policy


def test_browser_companion_content_script_captures_search_home_hotkeys():
    content = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
        / "content_script.js"
    ).read_text(encoding="utf-8")

    assert 'window.addEventListener("message"' in content
    assert 'type: "rumi:search-home:set-route-state"' in content
    assert 'type: "rumi:search-home:get-route-state"' in content
    assert 'message.source !== SEARCH_HOME_MESSAGE_SOURCE' in content
    assert 'event.origin !== window.location.origin' in content
    assert "RumiBridgeUrlPolicy?.isTrustedSearchHomeOrigin(event.origin)" in content
    assert "isSearchHomeRouteState(message.payload)" in content
    assert 'window.addEventListener(\n    "keydown"' in content
    assert 'event.key === "ArrowRight"' in content
    assert 'event.key === "ArrowLeft"' in content
    assert 'event.key === "Enter"' in content
    assert 'searchHomeRouteStateExpiresAt = Date.now() + SEARCH_HOME_ROUTE_STATE_MAX_AGE_MS' in content
    assert "refreshSearchHomeRouteState();" in content
    assert 'action: event.key === "ArrowLeft" ? "prev" : event.key === "ArrowRight" ? "next" : "open"' in content
    assert "event.preventDefault()" in content


def test_browser_companion_background_search_home_action_contract():
    background = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
        / "background.js"
    ).read_text(encoding="utf-8")

    assert "function normalizeSearchHomeRouteAction" in background
    assert 'value === "previous" || value === "prev" || value === "left"' in background
    assert 'value === "open" || value === "enter"' in background
    assert 'normalizedAction === "open"' in background


def test_browser_companion_url_policy_blocks_untrusted_search_home_navigation_targets():
    extension_root = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
    )
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to exercise the browser companion URL policy")

    script = """
const policyPath = process.argv[1];
require(policyPath);
const policy = globalThis.RumiBridgeUrlPolicy;
const cases = [
  ["server", "http://127.0.0.1:8766", true],
  ["server", "https://example.com", false],
  ["origin", "http://localhost:5173", true],
  ["origin", "https://example.com", false],
  ["nav", "https://example.com/path", true],
  ["nav", "http://127.0.0.1:3000/private", false],
  ["nav", "http://192.168.1.5/admin", false],
  ["nav", "file:///tmp/secret", false],
  ["nav", "https://user:pass@example.com/", false],
];
for (const [kind, value, expected] of cases) {
  const result =
    kind === "server"
      ? policy.validateServerUrl(value).ok
      : kind === "origin"
        ? policy.isTrustedSearchHomeOrigin(value)
        : policy.validateNavigationUrl(value).ok;
  if (result !== expected) {
    throw new Error(`${kind} ${value} expected ${expected} but got ${result}`);
  }
}
"""
    result = subprocess.run(
        [node, "-e", script, str(extension_root / "bridge_url_policy.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_browser_companion_content_script_restores_search_home_state_after_navigation():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to exercise the browser companion content script lifecycle")

    content_path = (
        DEFAULTSPACK_ROOT
        / "browser_extensions"
        / "rumi_browser_companion"
        / "content_script.js"
    )
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const content = fs.readFileSync(process.argv[1], "utf8");
        const listeners = {};
        const runtimeMessages = [];
        const now = Date.now();
        const chrome = {
          runtime: {
            sendMessage(message, callback) {
              runtimeMessages.push(message);
              if (message.type === "rumi:search-home:get-route-state") {
                const response = { ok: true, active: true, expires_at: now + 60_000 };
                if (callback) {
                  setImmediate(() => callback(response));
                }
                return undefined;
              }
              if (message.type === "rumi:search-home:advance-candidate") {
                if (callback) {
                  callback({ ok: true });
                }
                return undefined;
              }
              if (callback) {
                callback({ ok: true });
              }
              return undefined;
            },
            onMessage: {
              addListener(listener) {
                listeners.runtime = listener;
              }
            }
          }
        };
        const window = {
          addEventListener(type, handler) {
            listeners[type] = listeners[type] || [];
            listeners[type].push(handler);
          },
          innerWidth: 1280,
          innerHeight: 720,
          scrollX: 0,
          scrollY: 0
        };
        const document = {
          title: "Search Home candidate",
          body: {},
          documentElement: {}
        };
        const context = {
          console,
          Date,
          setImmediate,
          setTimeout,
          clearTimeout,
          chrome,
          window,
          document,
          location: { href: "https://example.com/result" },
          NodeFilter: { SHOW_ELEMENT: 1 },
          HTMLElement: class HTMLElement {},
          Element: class Element {},
          MouseEvent: class MouseEvent {},
          KeyboardEvent: class KeyboardEvent {},
          Event: class Event {}
        };
        vm.createContext(context);
        vm.runInContext(content, context, { filename: "content_script.js" });

        setTimeout(() => {
          const keydown = (listeners.keydown || [])[0];
          if (!keydown) {
            throw new Error("keydown listener was not registered");
          }
          let prevented = false;
          let stopped = false;
          keydown({
            key: "ArrowRight",
            preventDefault() {
              prevented = true;
            },
            stopPropagation() {
              stopped = true;
            }
          });
          if (!runtimeMessages.some((message) => message.type === "rumi:search-home:get-route-state")) {
            throw new Error("content script did not restore Search Home state from background");
          }
          const advance = runtimeMessages.find((message) => message.type === "rumi:search-home:advance-candidate");
          if (!advance || advance.action !== "next") {
            throw new Error(`unexpected advance message: ${JSON.stringify(advance)}`);
          }
          if (!prevented || !stopped) {
            throw new Error("restored Search Home hotkey was not captured");
          }
        }, 20);
        """
    )
    subprocess.run(
        [node, "-e", script, str(content_path)],
        cwd=ROOT,
        check=True,
        text=True,
    )
