export type ConversationSlashActionIntent =
  | { kind: "open_history" }
  | { kind: "export_conversation"; format: string }
  | { kind: "rename_conversation"; title: string }
  | { kind: "feedback"; message: string };

export function conversationSlashActionIntent(
  action: string | undefined,
  args: Record<string, unknown>,
  options: { hasActiveConversation: boolean },
): ConversationSlashActionIntent | null {
  switch (action) {
    case "open_history":
      return { kind: "open_history" };
    case "export_conversation":
      if (!options.hasActiveConversation) {
        return { kind: "feedback", message: "エクスポートする会話がありません。" };
      }
      return {
        kind: "export_conversation",
        format: cleanString(args.format) || "markdown",
      };
    case "rename_conversation": {
      if (!options.hasActiveConversation) {
        return { kind: "feedback", message: "リネームする会話がありません。" };
      }
      const title = cleanString(args.title);
      if (!title) {
        return { kind: "feedback", message: "/rename の後に新しい会話名を指定してください。" };
      }
      return { kind: "rename_conversation", title };
    }
    case "fork_conversation":
      return {
        kind: "feedback",
        message: "/fork はまだこの UI から利用できません。会話は変更されていません。",
      };
    case "resume_conversation":
      return {
        kind: "feedback",
        message: "/resume はまだこの UI から利用できません。会話は変更されていません。",
      };
    default:
      return null;
  }
}

function cleanString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
