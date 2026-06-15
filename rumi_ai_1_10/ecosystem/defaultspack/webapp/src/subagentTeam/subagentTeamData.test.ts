import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentActivity,
  channelCount,
  previewAgents,
  previewChannels,
  previewInbox,
  previewMessages,
  previewRuns,
  shortId,
} from "./subagentTeamData";

test("shortId returns compact readable ids without separators", () => {
  assert.equal(shortId("msg-preview-frontend-1"), "ntend1");
  assert.equal(shortId(""), "----");
  assert.equal(shortId("a"), "000a");
});

test("preview data includes Creator, PM, and a rich channel lane", () => {
  assert.ok(previewAgents.some((agent) => agent.agent_id === "creator"));
  assert.ok(previewAgents.some((agent) => agent.agent_id === "pm"));
  assert.ok(previewChannels.some((channel) => channel.metadata?.tone === "rich"));
});

test("channelCount prefers unread metadata and falls back to messages", () => {
  const shipRoom = previewChannels.find((channel) => channel.id === "ship-room");
  assert.ok(shipRoom);
  assert.equal(channelCount(shipRoom, previewMessages), 2);

  assert.equal(
    channelCount({ id: "dm-pm", name: "dm-pm", metadata: {} }, previewMessages),
    1,
  );
});

test("buildAgentActivity combines run status with open inbox counts", () => {
  const activity = buildAgentActivity(previewAgents, previewInbox, previewRuns);

  assert.equal(activity.get("frontend")?.status, "active");
  assert.equal(activity.get("frontend")?.openInboxCount, 1);
  assert.equal(activity.get("pm")?.latestInbox?.priority, "high");
  assert.equal(activity.get("qa")?.latestRun?.run_id, "run-preview-qa");
});
