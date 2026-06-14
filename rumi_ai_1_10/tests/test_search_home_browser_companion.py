from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_companion_background_supports_search_home_candidate_navigation():
    extension_root = (
        ROOT
        / "ecosystem"
        / "defaultspack"
        / "browser_extensions"
        / "rumi_browser_companion"
    )
    background = (extension_root / "background.js").read_text(encoding="utf-8")
    manifest = (extension_root / "manifest.json").read_text(encoding="utf-8")
    policy = (extension_root / "bridge_url_policy.js").read_text(encoding="utf-8")

    assert 'import "./bridge_url_policy.js";' in background
    assert '"bridge_url_policy.js"' in manifest
    assert "rumi:search-home:set-route-state" in background
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
        ROOT
        / "ecosystem"
        / "defaultspack"
        / "browser_extensions"
        / "rumi_browser_companion"
        / "content_script.js"
    ).read_text(encoding="utf-8")

    assert 'window.addEventListener("message"' in content
    assert 'type: "rumi:search-home:set-route-state"' in content
    assert 'message.source !== SEARCH_HOME_MESSAGE_SOURCE' in content
    assert 'event.origin !== window.location.origin' in content
    assert "RumiBridgeUrlPolicy?.isTrustedSearchHomeOrigin(event.origin)" in content
    assert "isSearchHomeRouteState(message.payload)" in content
    assert 'window.addEventListener(\n    "keydown"' in content
    assert 'event.key === "ArrowRight"' in content
    assert 'event.key === "ArrowLeft"' in content
    assert 'event.key === "Enter"' in content


def test_browser_companion_url_policy_blocks_untrusted_search_home_navigation_targets():
    extension_root = (
        ROOT
        / "ecosystem"
        / "defaultspack"
        / "browser_extensions"
        / "rumi_browser_companion"
    )
    node = shutil.which("node")
    if not node:
        return

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
