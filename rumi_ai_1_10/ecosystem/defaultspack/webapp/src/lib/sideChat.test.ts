import assert from "node:assert/strict";
import test from "node:test";

import type { Conversation } from "./api";
import {
  findSideChatConversation,
  isSideChatConversation,
  sideChatCreateOptions,
} from "./sideChat";

function conversation(
  id: string,
  overrides: Partial<Conversation> = {},
): Conversation {
  return {
    id,
    title: id,
    created_at: 1,
    updated_at: 1,
    model: "provider/main",
    system_prompt_id: null,
    agent_id: null,
    tags: [],
    is_starred: false,
    is_archived: false,
    current_node_id: null,
    parent_conversation_id: null,
    child_conversation_ids: [],
    conversation_kind: "chat",
    group_id: null,
    metadata: {},
    messages: [],
    ...overrides,
  } as Conversation;
}

test("findSideChatConversation selects only the side child for the current parent", () => {
  const sideA = conversation("side-a", {
    parent_conversation_id: "parent-a",
    conversation_kind: "side",
    metadata: { hidden: true, conversation_channel: "side" },
  });
  const sideB = conversation("side-b", {
    parent_conversation_id: "parent-b",
    conversation_kind: "side",
    metadata: { hidden: true, conversation_channel: "side" },
  });
  const subagent = conversation("worker", {
    parent_conversation_id: "parent-a",
    conversation_kind: "subagent",
  });

  assert.equal(findSideChatConversation([subagent, sideB, sideA], "parent-a")?.id, "side-a");
  assert.equal(isSideChatConversation(sideB, "parent-a"), false);
});

test("sideChatCreateOptions keeps the shared runtime context and hides the child", () => {
  const parent = conversation("parent", {
    model: "provider/model",
    system_prompt_id: "system-prompt",
    agent_id: "agent",
    group_id: "group",
    metadata: {
      workspace_id: "workspace",
      workspace_root: "/workspace",
      tool_preferences: { mode: "manual" },
    },
  });

  const options = sideChatCreateOptions(parent, "provider/selected");

  assert.equal(options.model, "provider/selected");
  assert.equal(options.parent_conversation_id, parent.id);
  assert.equal(options.conversation_kind, "side");
  assert.equal(options.metadata?.hidden, true);
  assert.equal(options.metadata?.conversation_channel, "side");
  assert.equal(options.metadata?.workspace_id, "workspace");
  assert.deepEqual(options.metadata?.tool_preferences, { mode: "manual" });
});
