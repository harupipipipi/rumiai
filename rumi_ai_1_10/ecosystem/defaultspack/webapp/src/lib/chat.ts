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

function numericValue(value: unknown): number | null {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function messageSortKey(message: ChatMessage, originalIndex: number): {
  sequence: number | null;
  createdAt: number;
  originalIndex: number;
} {
  const sequence = numericValue(message.sequence_number);
  return {
    sequence: sequence && sequence > 0 ? sequence : null,
    createdAt: numericValue(message.created_at) ?? 0,
    originalIndex,
  };
}

export function orderConversationMessages(messages: ChatMessage[]): ChatMessage[] {
  const byId = new Map<string, { message: ChatMessage; originalIndex: number }>();
  messages.forEach((message, index) => {
    const id = String(message.id || "").trim();
    if (!id) {
      byId.set(`__message_${index}`, { message, originalIndex: index });
      return;
    }
    const existing = byId.get(id);
    byId.set(id, {
      message: {
        ...(existing?.message ?? {}),
        ...message,
        events: message.events ?? existing?.message.events ?? null,
        tool_logs: message.tool_logs ?? existing?.message.tool_logs ?? null,
      },
      originalIndex: existing?.originalIndex ?? index,
    });
  });

  return [...byId.values()]
    .sort((left, right) => {
      const leftKey = messageSortKey(left.message, left.originalIndex);
      const rightKey = messageSortKey(right.message, right.originalIndex);
      if (leftKey.sequence !== null && rightKey.sequence !== null && leftKey.sequence !== rightKey.sequence) {
        return leftKey.sequence - rightKey.sequence;
      }
      if (leftKey.createdAt !== rightKey.createdAt) {
        return leftKey.createdAt - rightKey.createdAt;
      }
      return leftKey.originalIndex - rightKey.originalIndex;
    })
    .map((entry) => entry.message);
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
