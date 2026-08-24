import type { Conversation } from "./api";

export type ConversationExportFormat = "markdown" | "json" | "text";

export type ConversationExport = {
  conversation_id: string;
  content: string;
  format: ConversationExportFormat;
};

export type ConversationSlashApi = {
  exportConversation: (
    conversationId: string,
    format: ConversationExportFormat,
  ) => Promise<ConversationExport>;
  forkConversation: (
    conversationId: string,
    messageId?: string | null,
  ) => Promise<Conversation>;
  getConversation: (conversationId: string) => Promise<Conversation>;
  updateConversation: (
    conversationId: string,
    updates: Partial<Conversation>,
  ) => Promise<Conversation>;
};

export type ConversationSlashOutcome =
  | { handled: false }
  | {
    handled: true;
    clearInput: false;
    effect: "error";
    message: string;
  }
  | {
    handled: true;
    clearInput: true;
    effect: "history";
    message?: string;
  }
  | {
    handled: true;
    clearInput: true;
    effect: "export";
    exported: ConversationExport;
  }
  | {
    handled: true;
    clearInput: true;
    effect: "fork" | "resume" | "rename";
    conversation: Conversation;
    message: string;
  };

const CONVERSATION_ACTIONS = new Set([
  "open_history",
  "export_conversation",
  "fork_conversation",
  "resume_conversation",
  "rename_conversation",
]);

export function conversationSlashExportFormat(
  args: Record<string, unknown>,
): ConversationExportFormat | null {
  const requested = String(args.format ?? "markdown")
    .trim()
    .toLowerCase()
    .replace(/^\./, "");
  if (!requested || requested === "markdown" || requested === "md") {
    return "markdown";
  }
  if (requested === "json") return "json";
  if (requested === "text" || requested === "txt") return "text";
  return null;
}

export function conversationSlashRenameTitle(
  args: Record<string, unknown>,
): string {
  return String(args.title ?? "").replace(/\s+/g, " ").trim();
}

export function conversationExportFilename(format: ConversationExportFormat): string {
  const extension = format === "markdown" ? "md" : format === "text" ? "txt" : "json";
  return `conversation.${extension}`;
}

export function conversationExportMimeType(format: ConversationExportFormat): string {
  return format === "json" ? "application/json" : "text/plain";
}

export function isUnresolvedSlashCommandInput(
  input: string,
  commandsEnabled: boolean,
): boolean {
  const normalized = input.trimStart();
  return commandsEnabled && normalized.startsWith("/") && !normalized.startsWith("//");
}

export async function writeConversationExportClipboard(
  content: string,
  hostWrite: (value: string) => Promise<{ written?: boolean }>,
): Promise<boolean> {
  try {
    return (await hostWrite(content)).written === true;
  } catch {
    // Clipboard writes stay behind the host's approval and audit boundary.
    return false;
  }
}

export async function runConversationSlashAction(
  action: string | undefined,
  args: Record<string, unknown>,
  context: {
    activeConversation: Conversation | null;
    activeConversationId: string | null;
    api: ConversationSlashApi;
  },
): Promise<ConversationSlashOutcome> {
  if (!action || !CONVERSATION_ACTIONS.has(action)) return { handled: false };

  if (action === "open_history") {
    return { handled: true, clearInput: true, effect: "history" };
  }

  const conversationId = context.activeConversationId;
  if (!conversationId) {
    if (action === "resume_conversation") {
      return {
        handled: true,
        clearInput: true,
        effect: "history",
        message: "履歴から再開する会話を選択してください。",
      };
    }
    const actionLabel = action === "export_conversation"
      ? "エクスポート"
      : action === "fork_conversation"
        ? "fork"
        : "名前を変更";
    return {
      handled: true,
      clearInput: false,
      effect: "error",
      message: `${actionLabel}する会話がありません。`,
    };
  }

  try {
    if (action === "export_conversation") {
      const format = conversationSlashExportFormat(args);
      if (!format) {
        return {
          handled: true,
          clearInput: false,
          effect: "error",
          message: "export format は markdown、json、text のいずれかを指定してください。",
        };
      }
      const exported = await context.api.exportConversation(conversationId, format);
      return { handled: true, clearInput: true, effect: "export", exported };
    }

    if (action === "fork_conversation") {
      const messageId = context.activeConversation?.id === conversationId
        ? context.activeConversation.current_node_id
        : null;
      const conversation = await context.api.forkConversation(conversationId, messageId);
      return {
        handled: true,
        clearInput: true,
        effect: "fork",
        conversation,
        message: `Fork を作成しました: ${conversation.title}`,
      };
    }

    if (action === "resume_conversation") {
      const conversation = await context.api.getConversation(conversationId);
      return {
        handled: true,
        clearInput: true,
        effect: "resume",
        conversation,
        message: "Conversation を最新状態から再開しました。",
      };
    }

    const title = conversationSlashRenameTitle(args);
    if (!title) {
      return {
        handled: true,
        clearInput: false,
        effect: "error",
        message: "新しい会話名を /rename <title> の形式で指定してください。",
      };
    }
    const conversation = await context.api.updateConversation(conversationId, { title });
    return {
      handled: true,
      clearInput: true,
      effect: "rename",
      conversation,
      message: `Conversation を「${conversation.title}」に変更しました。`,
    };
  } catch {
    return {
      handled: true,
      clearInput: false,
      effect: "error",
      message: "会話コマンドの実行に失敗しました。入力内容を確認して、もう一度お試しください。",
    };
  }
}
