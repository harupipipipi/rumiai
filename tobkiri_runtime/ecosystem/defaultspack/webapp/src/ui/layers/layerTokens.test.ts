import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { layerClassName, layerZ } from "./layerTokens";

describe("layer tokens", () => {
  it("keeps global layer order stable", () => {
    assert.deepEqual(layerZ, {
      base: 0,
      panel: 10,
      localPopover: 20,
      globalOverlay: 40,
      modalBackdrop: 50,
      modal: 60,
      commandPalette: 70,
      toast: 80,
      debug: 90,
    });
  });

  it("exports class names for every token", () => {
    assert.deepEqual(Object.keys(layerClassName).sort(), Object.keys(layerZ).sort());
    assert.equal(layerClassName.modal, "rumi-layer-modal");
  });
});
