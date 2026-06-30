export async function loadConversationForRefresh({
  preferredId,
  activeConversationId,
  locationChatId,
  listedConversations,
  loadConversation,
}: {
  preferredId?: string | null;
  activeConversationId?: string | null;
  locationChatId?: string | null;
  listedConversations: Array<{ id: string }>;
  loadConversation: (conversationId: string | null) => Promise<void>;
}): Promise<void> {
  const targetId = preferredId ?? locationChatId ?? activeConversationId ?? listedConversations[0]?.id ?? null;
  if (!targetId) {
    await loadConversation(null);
    return;
  }

  if (listedConversations.some((conversation) => conversation.id === targetId)) {
    await loadConversation(targetId);
    return;
  }

  try {
    await loadConversation(targetId);
  } catch {
    await loadConversation(listedConversations[0]?.id ?? null);
  }
}
