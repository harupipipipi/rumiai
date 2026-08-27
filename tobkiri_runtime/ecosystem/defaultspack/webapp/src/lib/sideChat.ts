import type { Conversation } from "./api";

export const SIDE_CHAT_CONVERSATION_KIND = "side";
export const SIDE_CHAT_CONVERSATION_CHANNEL = "side";

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

export function sideChatCreateOptions(parentConversationId: string) {
  return {
    parent_conversation_id: parentConversationId,
    conversation_kind: SIDE_CHAT_CONVERSATION_KIND,
    tags: ["side-chat"],
    metadata: {
      hidden: true,
      conversation_channel: SIDE_CHAT_CONVERSATION_CHANNEL,
      side_parent_conversation_id: parentConversationId,
    },
  };
}

export function sideChatRequestMetadata(
  parentConversationId: string,
  workspace?: {
    id?: string | null;
    label?: string | null;
    root?: string | null;
  },
): Record<string, unknown> {
  return {
    conversation_channel: SIDE_CHAT_CONVERSATION_CHANNEL,
    parent_conversation_id: parentConversationId,
    ...(workspace?.id ? {
      workspace_id: workspace.id,
      workspace_label: workspace.label,
      workspace_root: workspace.root,
    } : {}),
  };
}
