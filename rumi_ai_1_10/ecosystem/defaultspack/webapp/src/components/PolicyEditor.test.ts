import test from "node:test";
import assert from "node:assert/strict";

import { createDefaultApprovalPolicy, policyEnabledCount, togglePolicyFlag } from "./PolicyEditor";

test("policy editor creates conservative defaults", () => {
  const policy = createDefaultApprovalPolicy(["browser_use"], ["openrouter/free"], ["low", "high"]);

  assert.deepEqual(policy.tool_policy, { browser_use: true });
  assert.deepEqual(policy.model_policy, { "openrouter/free": true });
  assert.deepEqual(policy.risk_policy, { low: true, high: false });
  assert.deepEqual(policy.require_human_for, ["medium", "high", "critical"]);
});

test("policy editor toggles independent policy groups", () => {
  const policy = createDefaultApprovalPolicy(["browser_use"], [], ["low"]);
  const next = togglePolicyFlag(policy, "tool_policy", "browser_use");

  assert.equal(next.tool_policy?.browser_use, false);
  assert.equal(policy.tool_policy?.browser_use, true);
  assert.equal(policyEnabledCount(next, "tool_policy"), 0);
});
