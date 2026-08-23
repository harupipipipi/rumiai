import assert from "node:assert/strict";
import test from "node:test";

import type { Conversation } from "./api";
import {
  type ConversationExportFormat,
  type ConversationSlashApi,
  conversationExportFilename,
  conversationExportMimeType,
  conversationSlashExportFormat,
  conversationSlashRenameTitle,
  isUnresolvedSlashCommandInput,
  runConversationSlashAction,
  writeConversationExportClipboard,
} from "./conversationSlashActions";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "conversation-source",
    title: "Architecture review",
    created_at: 10,
    updated_at: 20,
    model: "openai/gpt-test",
    system_prompt_id: "prompt-1",
    agent_id: "agent-1",
    parent_conversation_id: null,
    child_conversation_ids: [],
    conversation_kind: "coding",
    group_id: "group-1",
    metadata: { workspace_id: "workspace-1" },
    tags: ["coding", "review"],
    is_starred: false,
    is_archived: false,
    current_node_id: "message-last",
    messages: [],
    ...overrides,
  };
}

function apiStub(overrides: Partial<ConversationSlashApi> = {}): ConversationSlashApi {
  const source = conversation();
  return {
    exportConversation: async (
      conversationId: string,
      format: ConversationExportFormat,
    ) => ({
      conversation_id: conversationId,
      content: "exported",
      format,
    }),
    forkConversation: async () => conversation({
      id: "conversation-fork",
      title: "Architecture review (fork)",
      parent_conversation_id: source.id,
    }),
    getConversation: async () => source,
    updateConversation: async (_id: string, updates: Partial<Conversation>) => conversation(updates),
    ...overrides,
  };
}

test("conversation slash formats normalize documented aliases", () => {
  assert.equal(conversationSlashExportFormat({}), "markdown");
  assert.equal(conversationSlashExportFormat({ format: " .MD " }), "markdown");
  assert.equal(conversationSlashExportFormat({ format: "JSON" }), "json");
  assert.equal(conversationSlashExportFormat({ format: "txt" }), "text");
  assert.equal(conversationSlashExportFormat({ format: "pdf" }), null);
  assert.equal(conversationSlashRenameTitle({ title: "  QA   Canvas Slash  " }), "QA Canvas Slash");
  assert.equal(conversationExportFilename("markdown"), "conversation.md");
  assert.equal(conversationExportFilename("text"), "conversation.txt");
  assert.equal(conversationExportMimeType("json"), "application/json");
});

test("history and empty resume produce visible history outcomes", async () => {
  const context = { activeConversation: null, activeConversationId: null, api: apiStub() };
  assert.deepEqual(await runConversationSlashAction("open_history", {}, context), {
    handled: true,
    clearInput: true,
    effect: "history",
  });
  const resumed = await runConversationSlashAction("resume_conversation", {}, context);
  assert.equal(resumed.handled, true);
  assert.equal(resumed.handled && resumed.effect, "history");
  assert.match(resumed.handled && "message" in resumed ? resumed.message ?? "" : "", /履歴/);
});

test("missing inputs and API failures preserve the slash command", async () => {
  const noConversation = { activeConversation: null, activeConversationId: null, api: apiStub() };
  for (const action of ["export_conversation", "fork_conversation", "rename_conversation"]) {
    const outcome = await runConversationSlashAction(action, {}, noConversation);
    assert.equal(outcome.handled, true);
    assert.equal(outcome.handled && outcome.clearInput, false);
    assert.equal(outcome.handled && outcome.effect, "error");
  }

  const source = conversation();
  const failing = {
    activeConversation: source,
    activeConversationId: source.id,
    api: apiStub({
      exportConversation: async () => { throw new Error("clipboard policy denied export"); },
    }),
  };
  const failure = await runConversationSlashAction("export_conversation", {}, failing);
  assert.equal(failure.handled && failure.clearInput, false);
  const failureMessage = failure.handled && "message" in failure ? failure.message ?? "" : "";
  assert.match(failureMessage, /失敗/);
  assert.doesNotMatch(failureMessage, /policy denied/);
});

test("export, fork, resume, and rename use the active conversation exactly once", async () => {
  const source = conversation();
  const calls: Array<[string, ...unknown[]]> = [];
  const api = apiStub({
    exportConversation: async (id: string, format: ConversationExportFormat) => {
      calls.push(["export", id, format]);
      return { conversation_id: id, content: "plain", format };
    },
    forkConversation: async (id: string, messageId?: string | null) => {
      calls.push(["fork", id, messageId]);
      return conversation({ id: "forked", parent_conversation_id: id });
    },
    getConversation: async (id: string) => {
      calls.push(["resume", id]);
      return source;
    },
    updateConversation: async (id: string, updates: Partial<Conversation>) => {
      calls.push(["rename", id, updates]);
      return conversation(updates);
    },
  });
  const context = { activeConversation: source, activeConversationId: source.id, api };

  const exported = await runConversationSlashAction("export_conversation", { format: "txt" }, context);
  const forked = await runConversationSlashAction("fork_conversation", {}, context);
  const resumed = await runConversationSlashAction("resume_conversation", {}, context);
  const renamed = await runConversationSlashAction("rename_conversation", { title: " New name " }, context);

  for (const outcome of [exported, forked, resumed, renamed]) {
    assert.equal(outcome.handled && outcome.clearInput, true);
  }
  assert.deepEqual(calls, [
    ["export", source.id, "text"],
    ["fork", source.id, source.current_node_id],
    ["resume", source.id],
    ["rename", source.id, { title: "New name" }],
  ]);
});

test("unrelated frontend actions are not intercepted", async () => {
  const outcome = await runConversationSlashAction("open_settings", {}, {
    activeConversation: null,
    activeConversationId: null,
    api: apiStub(),
  });
  assert.deepEqual(outcome, { handled: false });
});

test("unknown single slash commands fail closed while double slash remains literal", () => {
  assert.equal(isUnresolvedSlashCommandInput(" /stale-command", true), true);
  assert.equal(isUnresolvedSlashCommandInput("//history", true), false);
  assert.equal(isUnresolvedSlashCommandInput("plain text", true), false);
  assert.equal(isUnresolvedSlashCommandInput("/history", false), false);
});

test("clipboard export never bypasses the host approval boundary", async () => {
  assert.equal(await writeConversationExportClipboard(
    "payload",
    async () => ({ written: true }),
  ), true);

  assert.equal(await writeConversationExportClipboard(
    "payload",
    async () => ({ written: false }),
  ), false);

  assert.equal(await writeConversationExportClipboard(
    "payload",
    async () => { throw new Error("host denied"); },
  ), false);
});
