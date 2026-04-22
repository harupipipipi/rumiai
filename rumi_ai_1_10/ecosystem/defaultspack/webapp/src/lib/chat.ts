import type { ChatContentBlock, ChatMessage, Conversation } from "./api";

export function contentBlocksToText(content: string | ChatContentBlock[]): string {
  if (typeof content === "string") {
    return content;
  }
  return content
    .map((block) => {
      if (typeof block === "string") {
        return block;
      }
      if (block.type === "text") {
        return String(block.text ?? "");
      }
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

export function messageToText(message: ChatMessage): string {
  if (message.raw_text && message.raw_text.trim()) {
    return message.raw_text;
  }
  return contentBlocksToText(message.content).trim();
}

export function deriveConversationTitle(seed: string): string {
  const title = seed.replace(/\s+/g, " ").trim();
  if (!title) {
    return "New Conversation";
  }
  return title.length > 40 ? `${title.slice(0, 40)}...` : title;
}

export function formatRelativeTime(timestamp: number, now = Date.now()): string {
  const diffMs = Math.max(0, now - timestamp);
  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }
  return new Intl.DateTimeFormat("ja-JP", {
    month: "short",
    day: "numeric",
  }).format(timestamp);
}

export function conversationSummary(conversation: Conversation | null): {
  title: string;
  messageCount: number;
  lastMessage: string;
} {
  if (!conversation) {
    return {
      title: "Ready",
      messageCount: 0,
      lastMessage: "まだ会話はありません。",
    };
  }
  const lastMessage = conversation.messages[conversation.messages.length - 1];
  return {
    title: conversation.title,
    messageCount: conversation.messages.length,
    lastMessage: lastMessage ? messageToText(lastMessage) : "まだメッセージはありません。",
  };
}
