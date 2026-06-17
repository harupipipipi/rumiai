import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { CompanyMessage } from "../lib/api";
import { ChannelButton } from "./SubagentTeamWorkspace";
import {
  agentShortId,
  buildAgentActivity,
  channelCount,
  channelMemberCount,
  channelUnreadCount,
  hasSubagentTeamWorkspaceMarker,
  normalizeSubagentOpenPreview,
  normalizeSubagentTreeResponse,
  previewAgents,
  previewChannels,
  previewInbox,
  previewMessages,
  previewRuns,
  removeReconciledLocalSubagentMessages,
  shortId,
  subagentMessageClientId,
  subagentTeamWorkspaceMetadata,
  subagentTreeItemsForMode,
} from "./subagentTeamData";

test("shortId returns compact readable ids without separators", () => {
  assert.equal(shortId("msg-preview-frontend-1"), "ntend1");
  assert.equal(shortId(""), "----");
  assert.equal(shortId("a"), "000a");
});

test("agentShortId prefers stable human aliases for DM and detail labels", () => {
  const frontend = previewAgents.find((agent) => agent.agent_id === "frontend");
  assert.equal(agentShortId(frontend), "sa-kai-184");
  assert.equal(agentShortId(undefined, "7e3ef4b5-2a4d-4f1f-b1f2-3ac983"), "sa-3ac983");
});

test("preview data includes Creator, PM, and a rich channel lane", () => {
  assert.ok(previewAgents.some((agent) => agent.agent_id === "creator"));
  assert.ok(previewAgents.some((agent) => agent.agent_id === "pm"));
  assert.ok(previewChannels.some((channel) => channel.metadata?.tone === "rich"));
});

test("subagent team workspace metadata carries the backend guard marker", () => {
  assert.deepEqual(
    subagentTeamWorkspaceMetadata({ conversation_id: "c1", source: "webapp", surface: "main_chat" }),
    {
      conversation_id: "c1",
      source: "webapp",
      surface: "subagent_team_workspace",
      subagent_team: true,
    },
  );
  assert.equal(hasSubagentTeamWorkspaceMarker({ surface: "subagent_team_workspace" }), true);
  assert.equal(hasSubagentTeamWorkspaceMarker({ subagent_team: true }), true);
  assert.equal(hasSubagentTeamWorkspaceMarker({ surface: "main_chat" }), false);
});

test("subagent message client ids round-trip through metadata", () => {
  const metadata = subagentTeamWorkspaceMetadata({ client_message_id: "client-1" });
  assert.equal(subagentMessageClientId({ metadata }), "client-1");
});

test("local optimistic messages reconcile with server client ids", () => {
  const local: CompanyMessage[] = [
    {
      id: "local-client-1",
      company_id: "company-1",
      channel_id: "ship-room",
      sender_id: "you",
      content: "same message",
      metadata: subagentTeamWorkspaceMetadata({ client_message_id: "client-1" }),
    },
    {
      id: "local-client-2",
      company_id: "company-1",
      channel_id: "ship-room",
      sender_id: "you",
      content: "still pending",
      metadata: subagentTeamWorkspaceMetadata({ client_message_id: "client-2" }),
    },
  ];
  const server: CompanyMessage[] = [
    {
      id: "server-client-1",
      company_id: "company-1",
      channel_id: "ship-room",
      sender_id: "user",
      content: "same message",
      metadata: subagentTeamWorkspaceMetadata({ client_message_id: "client-1" }),
    },
  ];

  assert.deepEqual(
    removeReconciledLocalSubagentMessages(local, server).map((message) => message.id),
    ["local-client-2"],
  );
});

test("local optimistic message is removed after send success even before reload metadata", () => {
  const local: CompanyMessage[] = [
    {
      id: "local-client-1",
      company_id: "company-1",
      channel_id: "ship-room",
      sender_id: "you",
      content: "same message",
      metadata: subagentTeamWorkspaceMetadata({ client_message_id: "client-1" }),
    },
  ];

  assert.deepEqual(removeReconciledLocalSubagentMessages(local, [], "client-1"), []);
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

test("channel button separates member count from unread badge", () => {
  const channel = {
    id: "curseforge_mod_code",
    name: "curseforge_mod_code",
    members: ["creator", "pm", "frontend", "backend", "qa", "reviewer"],
    metadata: { unread_count: 2 },
  };
  const html = renderToStaticMarkup(
    createElement(ChannelButton, {
      channel,
      active: false,
      memberCount: channelMemberCount(channel),
      unreadCount: channelUnreadCount(channel, []),
      onClick: () => undefined,
    }),
  );

  assert.match(html, /curseforge_mod_code/);
  assert.match(html, /\(6\)/);
  assert.match(html, /data-testid="subagent-channel-unread-curseforge_mod_code"/);
  assert.match(html, />2<\/span>/);
});

test("API file tree success uses API nodes instead of static fallback nodes", () => {
  const state = normalizeSubagentTreeResponse({
    workspace_id: "ws-api",
    files: [{ node_id: "api-only", path: "api-only.txt", name: "api-only.txt", is_dir: false }],
  });
  const labels = subagentTreeItemsForMode(state, "files").map((item) => item.label);

  assert.equal(state.source, "api");
  assert.deepEqual(labels, ["api-only.txt"]);
  assert.equal(labels.includes("SubagentTeamWorkspace.tsx"), false);
  assert.equal(labels.includes("decision-log.md"), false);
});

test("open node response normalizes into file preview and conversation history", () => {
  const fileItem = subagentTreeItemsForMode(
    normalizeSubagentTreeResponse({ files: [{ node_id: "notes", path: "notes.md", is_dir: false }] }),
    "files",
  )[0];
  const filePreview = normalizeSubagentOpenPreview(
    { node_id: "notes", path: "notes.md", content: "# API preview\nhello" },
    fileItem,
  );

  assert.equal(filePreview.title, "notes.md");
  assert.equal(filePreview.path, "notes.md");
  assert.match(filePreview.content ?? "", /API preview/);

  const historyItem = subagentTreeItemsForMode(
    normalizeSubagentTreeResponse({ history: [{ node_id: "handoff", title: "PM handoff" }] }),
    "history",
  )[0];
  const historyPreview = normalizeSubagentOpenPreview(
    { messages: [{ id: "m1", sender_id: "pm", content: "handoff complete" }] },
    historyItem,
  );

  assert.equal(historyPreview.messages?.[0]?.sender_id, "pm");
  assert.equal(historyPreview.messages?.[0]?.content, "handoff complete");
});

test("buildAgentActivity combines run status with open inbox counts", () => {
  const activity = buildAgentActivity(previewAgents, previewInbox, previewRuns);

  assert.equal(activity.get("frontend")?.status, "active");
  assert.equal(activity.get("frontend")?.openInboxCount, 1);
  assert.equal(activity.get("pm")?.latestInbox?.priority, "high");
  assert.equal(activity.get("qa")?.latestRun?.run_id, "run-preview-qa");
});
