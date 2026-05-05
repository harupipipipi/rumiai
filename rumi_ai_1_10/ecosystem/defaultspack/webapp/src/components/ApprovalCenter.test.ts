import test from "node:test";
import assert from "node:assert/strict";

import { approvalRiskRank, riskTone, sortApprovals } from "./ApprovalCenter";
import type { ApprovalRequest } from "../lib/api";

const approvals: ApprovalRequest[] = [
  { id: "low-old", status: "pending", risk_level: "low", created_at: "2026-01-01T00:00:00Z" },
  { id: "approved-high", status: "approved", risk_level: "critical", created_at: "2026-01-03T00:00:00Z" },
  { id: "high-new", status: "pending", risk_level: "high", created_at: "2026-01-02T00:00:00Z" },
];

test("approval center ranks high risk pending approvals first", () => {
  assert.deepEqual(sortApprovals(approvals).map((approval) => approval.id), [
    "high-new",
    "low-old",
    "approved-high",
  ]);
});

test("approval center risk helpers expose stable ordering and tones", () => {
  assert.equal(approvalRiskRank("critical") > approvalRiskRank("medium"), true);
  assert.match(riskTone("critical"), /red/);
  assert.match(riskTone("low"), /emerald/);
});
