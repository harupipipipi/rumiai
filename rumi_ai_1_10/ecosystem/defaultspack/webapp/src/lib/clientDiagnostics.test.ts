import assert from "node:assert/strict";
import test from "node:test";

import { api } from "./api";
import { diagnosticFingerprint } from "./clientDiagnostics";
import { reportClientDiagnostic } from "./clientDiagnostics";

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

test("reportClientDiagnostic retries after a failed send for the same fingerprint", async () => {
  const originalReportClientEvent = api.reportClientEvent;
  let calls = 0;
  api.reportClientEvent = async () => {
    calls += 1;
    if (calls === 1) {
      throw new Error("backend unavailable");
    }
    return { recorded: true, diagnostic_id: "diag_1" };
  };

  try {
    const first = await reportClientDiagnostic({
      source: "webapp",
      category: "conversation_integrity",
      message: "Frontend collapsed duplicate conversation messages before rendering.",
      fingerprint: "retry-me",
    });
    const second = await reportClientDiagnostic({
      source: "webapp",
      category: "conversation_integrity",
      message: "Frontend collapsed duplicate conversation messages before rendering.",
      fingerprint: "retry-me",
    });

    assert.equal(first, false);
    assert.equal(second, true);
    assert.equal(calls, 2);
  } finally {
    api.reportClientEvent = originalReportClientEvent;
  }
});
