import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import { sideChatContextIsCurrent } from "../components/SideChatWidget";
import type { Conversation } from "./api";
import {
  findSideChatConversation,
  isSideChatConversation,
  sideChatCreateOptions,
  sideChatRequestMetadata,
} from "./sideChat";

function conversation(overrides: Partial<Conversation>): Conversation {
  return {
    id: "conversation",
    title: "Conversation",
    created_at: 1,
    updated_at: 1,
    model: "stub/default",
    tags: [],
    is_starred: false,
    is_archived: false,
    messages: [],
    ...overrides,
  };
}

test("side chat helpers preserve the explicit parent relationship", () => {
  const sideA = conversation({
    id: "side-a",
    parent_conversation_id: "main-a",
    conversation_kind: "side",
  });
  const sideB = conversation({
    id: "side-b",
    parent_conversation_id: "main-b",
    metadata: { conversation_channel: "side" },
  });

  assert.equal(isSideChatConversation(sideA, "main-a"), true);
  assert.equal(isSideChatConversation(sideA, "main-b"), false);
  assert.equal(findSideChatConversation([sideB, sideA], "main-a"), sideA);
});

test("side chat creation and requests carry typed channel context", () => {
  assert.deepEqual(sideChatCreateOptions("main-a"), {
    parent_conversation_id: "main-a",
    conversation_kind: "side",
    tags: ["side-chat"],
    metadata: {
      hidden: true,
      conversation_channel: "side",
      side_parent_conversation_id: "main-a",
    },
  });
  assert.deepEqual(
    sideChatRequestMetadata("main-a", {
      id: "workspace-a",
      label: "Workspace A",
      root: "/workspace/a",
    }),
    {
      conversation_channel: "side",
      parent_conversation_id: "main-a",
      workspace_id: "workspace-a",
      workspace_label: "Workspace A",
      workspace_root: "/workspace/a",
    },
  );
});

test("side chat refuses stale parent context before execution", () => {
  const conversation = { parent_conversation_id: "main-a" };
  assert.equal(sideChatContextIsCurrent(3, 3, "main-a", "main-a", conversation), true);
  assert.equal(sideChatContextIsCurrent(3, 4, "main-a", "main-a", conversation), false);
  assert.equal(sideChatContextIsCurrent(3, 3, "main-a", "main-b", conversation), false);
  assert.equal(sideChatContextIsCurrent(
    3,
    3,
    "main-a",
    "main-a",
    { parent_conversation_id: "main-b" },
  ), false);
});

test("side composer keeps shared workspace file mention wiring", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "..", "components", "SideChatWidget.tsx"),
    "utf8",
  );
  assert.match(source, /sideChatResources\.readWorkspaceFile\(/);
  assert.match(source, /onAtFileAttach=\{handleAtFileAttach\}/);
  assert.match(source, /pendingMentionAttachmentPaths=\{pendingMentionAttachmentPaths\}/);
  assert.match(source, /await awaitParentContextSync\?\.\(parentId\)/);
  assert.equal((source.match(/sideChatContextIsCurrent\(/g) ?? []).length, 4);
});
