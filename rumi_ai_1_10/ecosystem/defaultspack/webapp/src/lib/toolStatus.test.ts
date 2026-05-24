import test from "node:test";
import assert from "node:assert/strict";

import { extractLatestToolFilterContext, summarizeToolManager, toolFilterBlockedSummary, toolFilterReasonDetail } from "./toolStatus";

test("extractLatestToolFilterContext reads the newest metadata payload", () => {
  const context = extractLatestToolFilterContext([
    {
      id: "m1",
      role: "user",
      content: "older",
      created_at: 1,
      conversation_id: "c1",
      metadata: {
        tool_filter_result: [{ tool_name: "older_tool", status: "allowed" }],
      },
    },
    {
      id: "m2",
      role: "user",
      content: "newer",
      created_at: 2,
      conversation_id: "c1",
      metadata: {
        tool_filter_result: [{ tool_name: "vision_tool", status: "blocked", reason_code: "model_unsupported", required: { model_capabilities: ["model.image_input"] } }],
        runtime_capability_snapshot: { model_capabilities: ["model.text"] },
      },
    },
  ]);

  assert.equal(context.entries[0]?.tool_name, "vision_tool");
  assert.deepEqual(context.snapshot?.model_capabilities, ["model.text"]);
});

test("toolFilterReasonDetail explains vision blocks in friendly text", () => {
  assert.equal(
    toolFilterReasonDetail({
      tool_name: "vision_tool",
      status: "blocked",
      reason_code: "model_unsupported",
      required: { model_capabilities: ["model.image_input"] },
    }),
    "Vision対応モデルに切り替えると使えます。",
  );
});

test("toolFilterBlockedSummary names the required model capability", () => {
  assert.equal(
    toolFilterBlockedSummary({
      tool_name: "browser",
      status: "blocked",
      reason_code: "model_unsupported",
      required: { model_capabilities: ["model.tool_calling"] },
    }),
    "Blocked: model.tool_calling",
  );
});

test("summarizeToolManager separates on off hidden blocked approval and setup", () => {
  const summary = summarizeToolManager(
    [
      { id: "vision_tool", label: "Vision", category: "tool", tool_info: { requires_approval: true } },
      { id: "web_search", label: "Web", category: "tool", tool_info: { setup_state: { status: "missing" } } },
      { id: "browser_use", label: "Browser", category: "tool" },
    ],
    {
      disabledToolIds: ["browser_use"],
      hiddenToolIds: ["web_search"],
      filterEntries: [{ tool_name: "vision_tool", status: "blocked", reason_code: "model_unsupported" }],
    },
  );

  assert.deepEqual(summary, {
    totalCount: 3,
    onCount: 2,
    offByUserCount: 1,
    hiddenCount: 1,
    blockedCount: 1,
    needsApprovalCount: 1,
    missingSetupCount: 1,
  });
});
