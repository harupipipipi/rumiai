import test from "node:test";
import assert from "node:assert/strict";

import type { AuthorityRequest } from "./api";
import { verifyAuthorityApprovalHint } from "./authorityApprovalEvents";

function authorityRequest(overrides: Partial<AuthorityRequest> = {}): AuthorityRequest {
  return {
    request_id: "req-1",
    status: "pending",
    principal_id: "principal-1",
    permission_id: "tool.execute",
    resource: { tool_id: "tool.example" },
    reason: "test",
    risk_level: "medium",
    created_at: "2026-07-10T00:00:00Z",
    conversation_id: "conversation-1",
    ...overrides,
  };
}

test("client-declared approval is ignored while the authoritative request is pending", async () => {
  const result = await verifyAuthorityApprovalHint(
    {
      requestId: "req-1",
      status: "approved",
      conversationId: "conversation-1",
      issuedAt: 1000,
    },
    {
      now: 1000,
      expectedRequestId: "req-1",
      fetchRequest: async () => authorityRequest(),
    },
  );

  assert.deepEqual(result, { kind: "ignored", reason: "request_not_settled" });
});

test("authoritative status replaces a forged client status", async () => {
  const result = await verifyAuthorityApprovalHint(
    {
      requestId: "req-1",
      status: "approved",
      conversationId: "conversation-1",
      issuedAt: 1000,
    },
    {
      now: 1000,
      expectedRequestId: "req-1",
      expectedConversationId: "conversation-1",
      expectedPrincipalId: "principal-1",
      expectedPermissionId: "tool.execute",
      fetchRequest: async () => authorityRequest({ status: "denied" }),
    },
  );

  assert.equal(result.kind, "verified");
  if (result.kind !== "verified") return;
  assert.deepEqual(result.settlement, {
    requestId: "req-1",
    status: "denied",
    conversationId: "conversation-1",
  });
});

test("wrong request, conversation, principal, and permission bindings fail closed", async () => {
  const fetchRequest = async () => authorityRequest({ status: "approved" });

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "other-request", issuedAt: 1000 },
      { now: 1000, expectedRequestId: "req-1", fetchRequest },
    ),
    { kind: "ignored", reason: "unexpected_request" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1", conversationId: "other-conversation", issuedAt: 1000 },
      { now: 1000, expectedRequestId: "req-1", fetchRequest },
    ),
    { kind: "ignored", reason: "conversation_mismatch" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1", issuedAt: 1000 },
      { now: 1000, expectedPrincipalId: "other-principal", fetchRequest },
    ),
    { kind: "ignored", reason: "principal_mismatch" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1", issuedAt: 1000 },
      { now: 1000, expectedPermissionId: "other.permission", fetchRequest },
    ),
    { kind: "ignored", reason: "permission_mismatch" },
  );
});

test("stale, malformed, failed, and mismatched lookups do not settle UI", async () => {
  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1", issuedAt: 1 },
      { now: 120000, fetchRequest: async () => authorityRequest({ status: "approved" }) },
    ),
    { kind: "ignored", reason: "stale_hint" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint({}, { fetchRequest: async () => authorityRequest() }),
    { kind: "ignored", reason: "malformed_hint" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1" },
      { fetchRequest: async () => { throw new Error("offline"); } },
    ),
    { kind: "ignored", reason: "lookup_failed" },
  );

  assert.deepEqual(
    await verifyAuthorityApprovalHint(
      { requestId: "req-1" },
      { fetchRequest: async () => authorityRequest({ request_id: "req-2", status: "approved" }) },
    ),
    { kind: "ignored", reason: "request_mismatch" },
  );
});

test("legacy settlement message shapes are only wake-up hints", async () => {
  const result = await verifyAuthorityApprovalHint(
    {
      type: "rumi-authority-approval-settlement",
      event: {
        requestId: "req-1",
        status: "denied",
        conversationId: "conversation-1",
        ts: 1000,
      },
    },
    {
      now: 1000,
      fetchRequest: async () => authorityRequest({ status: "approved" }),
    },
  );

  assert.equal(result.kind, "verified");
  if (result.kind !== "verified") return;
  assert.equal(result.settlement.status, "approved");
});
