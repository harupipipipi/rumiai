import type { Conversation } from "./api";

export const SIDE_CHAT_CONVERSATION_KIND = "side";
export const SIDE_CHAT_CONVERSATION_CHANNEL = "side";

export type SideChatCreateOptions = {
  model?: string;
  system_prompt_id?: string | null;
  agent_id?: string | null;
  tags?: string[];
  parent_conversation_id?: string | null;
  conversation_kind?: string | null;
  group_id?: string | null;
  metadata?: Record<string, unknown>;
};

export function isSideChatConversation(
  conversation: Conversation | null | undefined,
  parentConversationId?: string | null,
): boolean {
  if (!conversation) return false;
  const metadata = conversation.metadata && typeof conversation.metadata === "object"
    ? conversation.metadata
    : {};
  const isSide = conversation.conversation_kind === SIDE_CHAT_CONVERSATION_KIND
    || metadata.conversation_channel === SIDE_CHAT_CONVERSATION_CHANNEL;
  if (!isSide) return false;
  return parentConversationId
    ? conversation.parent_conversation_id === parentConversationId
    : true;
}

export function findSideChatConversation(
  conversations: Array<Conversation | null | undefined>,
  parentConversationId: string,
): Conversation | null {
  return conversations.find((conversation) => (
    isSideChatConversation(conversation, parentConversationId)
  )) ?? null;
}

export function sideChatCreateOptions(
  parent: Conversation,
  model: string,
): SideChatCreateOptions {
  const parentMetadata = parent.metadata && typeof parent.metadata === "object"
    ? parent.metadata
    : {};
  return {
    model: model || parent.model,
    system_prompt_id: parent.system_prompt_id ?? null,
    agent_id: parent.agent_id ?? null,
    tags: ["side-chat"],
    parent_conversation_id: parent.id,
    conversation_kind: SIDE_CHAT_CONVERSATION_KIND,
    group_id: parent.group_id ?? null,
    metadata: {
      ...parentMetadata,
      hidden: true,
      conversation_channel: SIDE_CHAT_CONVERSATION_CHANNEL,
      side_parent_conversation_id: parent.id,
    },
  };
}
