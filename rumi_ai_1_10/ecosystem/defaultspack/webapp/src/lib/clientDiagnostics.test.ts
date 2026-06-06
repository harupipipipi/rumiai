import assert from "node:assert/strict";
import test from "node:test";

import { diagnosticFingerprint } from "./clientDiagnostics";

test("diagnosticFingerprint stays stable for the same category and message", () => {
  const first = diagnosticFingerprint({
    source: "window.error",
    category: "window_error",
    message: "Renderer crashed",
    conversationId: "conv-1",
  });
  const second = diagnosticFingerprint({
    source: "window.error",
    category: "window_error",
    message: "Renderer crashed",
    conversationId: "conv-1",
  });

  assert.equal(first, second);
});
