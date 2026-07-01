import test from "node:test";
import assert from "node:assert/strict";

import { isTrustedLocalRendererModule, loadTrustedRenderer } from "./trustedRendererLoader";

const originalWindow = globalThis.window;

test("trusted local renderer modules are restricted to pack-namespaced static renderer paths", () => {
  Object.defineProperty(globalThis, "window", {
    value: { location: { origin: "http://127.0.0.1:8766" } },
    configurable: true,
  });

  assert.equal(isTrustedLocalRendererModule("/static/packs/rumi_memo_pack/renderers/custom.js"), true);
  assert.equal(isTrustedLocalRendererModule("/static/packs/rumi_memo_pack/assets/renderers/custom.js"), true);
  assert.equal(isTrustedLocalRendererModule("/static/renderers/custom.js"), false);
  assert.equal(isTrustedLocalRendererModule("/static/assets/renderers/custom.js"), false);
  assert.equal(isTrustedLocalRendererModule("/static/user_renderers/custom.js"), false);
  assert.equal(isTrustedLocalRendererModule("/api/ui/catalog"), false);
  assert.equal(isTrustedLocalRendererModule("https://example.com/custom.js"), false);

  Object.defineProperty(globalThis, "window", {
    value: originalWindow,
    configurable: true,
  });
});

test("loader falls back when renderer is not trusted local", () => {
  function Fallback() {
    return null;
  }

  const resolved = loadTrustedRenderer({ id: "x", component: "X", module: "/api/x", trust: "local" }, Fallback);
  assert.equal(resolved, Fallback);
});

test("loader falls back when pack binding metadata is absent or mismatched", () => {
  Object.defineProperty(globalThis, "window", {
    value: { location: { origin: "http://127.0.0.1:8766" } },
    configurable: true,
  });

  function Fallback() {
    return null;
  }

  assert.equal(
    loadTrustedRenderer({
      id: "x",
      component: "X",
      module: "/static/packs/rumi_memo_pack/renderers/custom.js",
      trust: "local",
    }, Fallback),
    Fallback,
  );
  assert.equal(
    loadTrustedRenderer({
      id: "x",
      component: "X",
      module: "/static/packs/other_pack/renderers/custom.js",
      source_pack_id: "rumi_memo_pack",
      module_pack_id: "other_pack",
      integrity: "sha256-test",
      trust: "local",
    }, Fallback),
    Fallback,
  );

  Object.defineProperty(globalThis, "window", {
    value: originalWindow,
    configurable: true,
  });
});
