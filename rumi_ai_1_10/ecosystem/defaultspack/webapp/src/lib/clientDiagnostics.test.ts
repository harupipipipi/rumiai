import assert from "node:assert/strict";
import test from "node:test";

import { api } from "./api";
import {
  diagnosticFingerprint,
  opaqueDiagnosticContextId,
  redactClientDiagnosticText,
  reportClientDiagnostic,
} from "./clientDiagnostics";

test("diagnosticFingerprint stays stable without exposing raw context or message", () => {
  const input = {
    source: "window.error",
    category: "window_error",
    message: "Renderer crashed for user@example.com with token sk-supersecretvalue",
    conversationId: "conv-private-1",
  };
  const first = diagnosticFingerprint(input);
  const second = diagnosticFingerprint(input);

  assert.equal(first, second);
  assert.match(first, /^fp_[0-9a-f]{8}$/);
  assert.doesNotMatch(first, /conv-private-1|user@example\.com|supersecret/);
  assert.match(opaqueDiagnosticContextId(input.conversationId) ?? "", /^ctx_[0-9a-f]{8}$/);
});

test("redactClientDiagnosticText removes credentials, URLs, email addresses, and local paths", () => {
  const redacted = redactClientDiagnosticText(
    "Authorization: Bearer secret-token-value failed for user@example.com at https://example.test/path?token=abc#private /Users/alice/project/.env",
  );

  assert.doesNotMatch(redacted, /secret-token-value|user@example\.com|example\.test|alice|\.env/);
  assert.match(redacted, /\[redacted-authorization\]|authorization=\[redacted\]/);
  assert.match(redacted, /\[redacted-email\]/);
  assert.match(redacted, /\[redacted-url\]/);
  assert.match(redacted, /\[redacted-path\]/);
});

test("reportClientDiagnostic sends only redacted bounded schema fields", async () => {
  const originalReportClientEvent = api.reportClientEvent;
  let captured: Parameters<typeof api.reportClientEvent>[0] | undefined;
  api.reportClientEvent = async (payload) => {
    captured = payload;
    return { recorded: true, diagnostic_id: "diag_redacted" };
  };

  try {
    const sent = await reportClientDiagnostic({
      source: "window.error",
      category: "window_error",
      message: "Request failed for user@example.com at https://api.example.test/v1?api_key=raw-secret",
      fingerprint: "fingerprint-with-secret-raw-secret",
      conversationId: "conversation-sensitive-123",
      detail: {
        authorization: "Bearer raw-bearer-secret",
        api_key: "sk-rawprovidersecret123456",
        message: "private user prompt content",
        path: "/Users/alice/customer/private.txt",
        source: "https://internal.example.test/path?token=hidden#fragment",
        stack: "Error: token=raw-stack-secret\n    at /Users/alice/project/app.ts:10:2",
        status: 500,
        private_blob: "must not be transported",
      },
    });

    assert.equal(sent, true);
    assert.ok(captured);
    const serialized = JSON.stringify(captured);
    assert.doesNotMatch(serialized, /raw-secret|raw-bearer-secret|rawprovidersecret|private user prompt|alice|customer|internal\.example|fragment|conversation-sensitive|must not be transported/);
    assert.match(captured?.conversation_id ?? "", /^ctx_[0-9a-f]{8}$/);
    assert.match(captured?.fingerprint ?? "", /^fp_[0-9a-f]{8}$/);
    assert.equal((captured?.detail as { schema_version?: string })?.schema_version, "client-diagnostic.v1");
    assert.ok(serialized.length <= 8_500);
  } finally {
    api.reportClientEvent = originalReportClientEvent;
  }
});

test("reportClientDiagnostic handles circular and oversized detail without leaking arbitrary fields", async () => {
  const originalReportClientEvent = api.reportClientEvent;
  let captured: Parameters<typeof api.reportClientEvent>[0] | undefined;
  api.reportClientEvent = async (payload) => {
    captured = payload;
    return { recorded: true, diagnostic_id: "diag_circular" };
  };

  const circular: Record<string, unknown> = {
    code: "E_CIRCULAR",
    status: "failed",
    ignored_private_field: "x".repeat(20_000),
  };
  circular.reason = circular;

  try {
    const sent = await reportClientDiagnostic({
      source: "webapp",
      category: "circular_test",
      message: "Circular diagnostic",
      fingerprint: "circular-unique",
      detail: circular,
    });

    assert.equal(sent, true);
    const serialized = JSON.stringify(captured);
    assert.match(serialized, /E_CIRCULAR/);
    assert.match(serialized, /\[circular\]/);
    assert.doesNotMatch(serialized, /ignored_private_field|x{100}/);
    assert.ok(serialized.length <= 8_500);
  } finally {
    api.reportClientEvent = originalReportClientEvent;
  }
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
