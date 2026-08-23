import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type FormEvent,
  type ReactNode,
} from "react";
import { Loader2, MessageSquareText } from "lucide-react";

import type {
  ChatActivityEvent,
  ChatContentBlock,
  ChatMessage,
  ChatStreamEvent,
  ComposerCommandItem,
  Conversation,
  ModelProfile,
  ToolSelectionRequest,
} from "../lib/api";
import {
  ChatStreamInterruptedError,
  sideChatResources,
} from "../features/chat/resources/sideChatResources";
import { messageToText, orderConversationMessages } from "../lib/chat";
import type { ComposerEntityReference } from "../lib/composerReferences";
import {
  composerMentionMetadataFromWidgets,
  composerMentionToolIdsFromWidgets,
} from "../lib/composerWidgets";
import {
  findSideChatConversation,
  sideChatCreateOptions,
  sideChatRequestMetadata,
} from "../lib/sideChat";
import {
  hasWorkspaceAttachment,
  workspaceFileToAttachment,
} from "../lib/workspaceAttachments";
import type {
  AppMode,
  AttachedFile,
  ChatMessagesRendererProps,
  ChatUiMessage,
  ComposerExtensionItem,
  ComposerRendererProps,
  ComposerSkillItem,
  ContextUsageInfo,
  DroppedWidget,
} from "../renderers/types";
import type { ActionApprovalMode } from "../features/tools/ActionApprovalControl";

type SideChatWidgetProps = {
  parentConversation: Conversation | null;
  selectedModel: string;
  selectedProfile: ModelProfile | null;
  favoriteProfiles: ModelProfile[];
  modelProfiles: ModelProfile[];
  thinkingLevel: string | null;
  deepthinkEnabled: boolean;
  contextUsage: ContextUsageInfo;
  inlineExtensions: ComposerExtensionItem[];
  skillExtensions: ComposerSkillItem[];
  commands: ComposerCommandItem[];
  selectedToolIds: string[];
  disabledToolIds: string[];
  actionApprovalMode: ActionApprovalMode;
  fullAccess: boolean;
  mode: AppMode;
  workspaceId?: string | null;
  workspaceLabel?: string | null;
  workspaceRoot?: string | null;
  templateParams?: Record<string, unknown>;
  templateToolPolicy?: Record<string, unknown>;
  unknownBlockStrategy: string;
  showActivityInMessages: boolean;
  showWidgets: boolean;
  showPromptUsageInMessages: boolean;
  composerRenderer: ComponentType<ComposerRendererProps>;
  messagesRenderer: ComponentType<ChatMessagesRendererProps>;
  refreshKey?: number;
  approvalSurface?: ReactNode;
  onConversationStateChange?: (
    conversation: Conversation | null,
    messages: ChatUiMessage[],
  ) => void;
  onOpenModelManager: () => void;
  onOpenToolSettings: () => void;
  onActionApprovalModeChange: (mode: ActionApprovalMode) => void;
  onExtensionSelect: (item: ComposerExtensionItem) => void;
  onCommandSelect: (
    commandId: string,
    rawInput?: string,
    conversationId?: string,
  ) => Promise<boolean | void>;
  onModelProfileSelect: (profileId: string) => void;
  onThinkingLevelChange: (level: string | null) => void;
  awaitParentContextSync?: (parentConversationId: string) => Promise<void>;
};

type RetryDraft = { text: string; files: AttachedFile[] };

function normalizedBlocks(message: ChatMessage): ChatContentBlock[] {
  if (Array.isArray(message.content)) return message.content;
  return [{ type: "text", text: String(message.content ?? "") }];
}

function messageMetadata(message: ChatMessage): ChatUiMessage["metadata"] {
  const metadata = message.metadata && typeof message.metadata === "object"
    ? message.metadata
    : {};
  const thinking = metadata.thinking && typeof metadata.thinking === "object"
    ? metadata.thinking as Record<string, unknown>
    : {};
  const timing = metadata.timing && typeof metadata.timing === "object"
    ? metadata.timing as Record<string, unknown>
    : {};
  const transport = metadata.transport && typeof metadata.transport === "object"
    ? metadata.transport as Record<string, unknown>
    : {};
  return {
    modelName: message.model ?? undefined,
    thinkingLabel: typeof thinking.state === "string" ? thinking.state : undefined,
    thinkingDuration: typeof timing.thinking_duration_label === "string"
      ? timing.thinking_duration_label
      : undefined,
    thinkingTranscript: typeof thinking.transcript === "string"
      ? thinking.transcript
      : undefined,
    interrupted: message.finish_reason === "interrupted" || transport.status === "interrupted",
    interruptionReason: typeof transport.reason === "string" ? transport.reason : undefined,
    pendingApproval: metadata.pending_approval && typeof metadata.pending_approval === "object"
      ? metadata.pending_approval as Record<string, unknown>
      : undefined,
    pendingAuthorityApproval: metadata.pending_authority_approval
      && typeof metadata.pending_authority_approval === "object"
      ? metadata.pending_authority_approval as Record<string, unknown>
      : undefined,
    promptUsage: metadata.prompt_usage && typeof metadata.prompt_usage === "object"
      ? metadata.prompt_usage as NonNullable<ChatUiMessage["metadata"]>["promptUsage"]
      : undefined,
  };
}

function toUiMessage(message: ChatMessage): ChatUiMessage {
  return {
    id: message.id,
    conversationId: message.conversation_id,
    createdAt: message.created_at,
    role: message.role === "user" ? "user" : "agent",
    content: normalizedBlocks(message),
    rawText: message.raw_text ?? messageToText(message),
    widget: message.widget,
    metadata: messageMetadata(message),
    events: message.events ?? undefined,
    toolLogs: message.tool_logs ?? undefined,
  };
}

function optimisticMessage(
  conversationId: string,
  role: "user" | "assistant",
  text: string,
  model?: string,
  metadata?: Record<string, unknown>,
): ChatMessage {
  return {
    id: `side-${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content: [{ type: "text", text }],
    raw_text: text,
    created_at: Date.now(),
    conversation_id: conversationId,
    model,
    metadata: role === "assistant"
      ? { ...metadata, thinking: { state: "streaming", transcript: "" } }
      : metadata,
    events: [],
  };
}

function isActivityEvent(event: ChatStreamEvent): boolean {
  return !["delta", "thinking_delta", "message", "done", "user_message", "error"]
    .includes(event.type);
}

export function sideChatContextIsCurrent(
  expectedGeneration: number,
  currentGeneration: number,
  expectedParentId: string,
  currentParentId: string | null,
  conversation: Pick<Conversation, "parent_conversation_id">,
): boolean {
  return expectedGeneration === currentGeneration
    && expectedParentId === currentParentId
    && conversation.parent_conversation_id === expectedParentId;
}

function contextChangedError(): DOMException {
  return new DOMException("Side chat parent changed", "AbortError");
}

export function SideChatWidget({
  parentConversation,
  selectedModel,
  selectedProfile,
  favoriteProfiles,
  modelProfiles,
  thinkingLevel,
  deepthinkEnabled,
  contextUsage,
  inlineExtensions,
  skillExtensions,
  commands,
  selectedToolIds,
  disabledToolIds,
  actionApprovalMode,
  fullAccess,
  mode,
  workspaceId,
  workspaceLabel,
  workspaceRoot,
  templateParams = {},
  templateToolPolicy = {},
  unknownBlockStrategy,
  showActivityInMessages,
  showWidgets,
  showPromptUsageInMessages,
  composerRenderer: Composer,
  messagesRenderer: Messages,
  refreshKey = 0,
  approvalSurface,
  onConversationStateChange,
  onOpenModelManager,
  onOpenToolSettings,
  onActionApprovalModeChange,
  onExtensionSelect,
  onCommandSelect,
  onModelProfileSelect,
  onThinkingLevelChange,
  awaitParentContextSync,
}: SideChatWidgetProps) {
  const [sideConversation, setSideConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [pendingMentionAttachmentPaths, setPendingMentionAttachmentPaths] = useState<string[]>([]);
  const [droppedWidgets, setDroppedWidgets] = useState<DroppedWidget[]>([]);
  const [entityReferences, setEntityReferences] = useState<ComposerEntityReference[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retryDraft, setRetryDraft] = useState<RetryDraft | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sideConversationRef = useRef<Conversation | null>(null);
  const generationRef = useRef(0);
  const parentIdRef = useRef<string | null>(null);
  const mentionAttachmentTokenRef = useRef(0);
  const pendingMentionAttachmentRequestsRef = useRef(new Map<string, number>());
  const parentId = parentConversation?.id ?? null;
  parentIdRef.current = parentId;
  const messages = useMemo(
    () => orderConversationMessages(sideConversation?.messages ?? []).map(toUiMessage),
    [sideConversation],
  );

  useEffect(() => {
    generationRef.current += 1;
    const priorSideConversationId = sideConversationRef.current?.id;
    if (abortControllerRef.current && priorSideConversationId) {
      void sideChatResources.stopMessage(priorSideConversationId).catch(() => undefined);
    }
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    sideConversationRef.current = null;
    setSideConversation(null);
    setInput("");
    setAttachedFiles([]);
    pendingMentionAttachmentRequestsRef.current.clear();
    setPendingMentionAttachmentPaths([]);
    setDroppedWidgets([]);
    setEntityReferences([]);
    setError(null);
    setRetryDraft(null);
    setIsGenerating(false);
    if (!parentId) {
      setIsLoading(false);
      return;
    }
    const generation = generationRef.current;
    let cancelled = false;
    setIsLoading(true);
    void (async () => {
      try {
        const parent = await sideChatResources.getConversation(parentId);
        const children = await Promise.all((parent.child_conversation_ids ?? []).map(
          (childId) => sideChatResources.getConversation(childId).catch(() => null),
        ));
        if (!cancelled && generation === generationRef.current) {
          setSideConversation(findSideChatConversation(children, parentId));
        }
      } catch (loadError) {
        if (!cancelled && generation === generationRef.current) {
          setError(loadError instanceof Error
            ? loadError.message
            : "サイドチャットを読み込めませんでした。");
        }
      } finally {
        if (!cancelled && generation === generationRef.current) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [parentId, refreshKey]);

  useEffect(() => {
    sideConversationRef.current = sideConversation;
  }, [sideConversation]);

  useEffect(() => {
    onConversationStateChange?.(sideConversation, messages);
  }, [messages, onConversationStateChange, sideConversation]);

  useEffect(() => (
    () => onConversationStateChange?.(null, [])
  ), [onConversationStateChange]);

  useEffect(() => () => {
    generationRef.current += 1;
    abortControllerRef.current?.abort();
    const conversationId = sideConversationRef.current?.id;
    if (conversationId) {
      void sideChatResources.stopMessage(conversationId).catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isGenerating]);

  const ensureSideConversation = async (
    expectedGeneration: number,
  ): Promise<Conversation> => {
    if (!parentId) throw new Error("先にメインチャットを開始してください。");
    if (sideConversation?.parent_conversation_id === parentId) {
      if (!sideChatContextIsCurrent(
        expectedGeneration,
        generationRef.current,
        parentId,
        parentIdRef.current,
        sideConversation,
      )) throw contextChangedError();
      return sideConversation;
    }
    const created = await sideChatResources.createConversation(
      sideChatCreateOptions(parentId),
    );
    if (!sideChatContextIsCurrent(
      expectedGeneration,
      generationRef.current,
      parentId,
      parentIdRef.current,
      created,
    )) throw contextChangedError();
    sideConversationRef.current = created;
    setSideConversation(created);
    return created;
  };

  const handleSideCommand = async (commandId: string, rawInput?: string) => {
    if (!parentId || isGenerating) return;
    const generation = generationRef.current;
    try {
      setError(null);
      await awaitParentContextSync?.(parentId);
      if (generation !== generationRef.current || parentIdRef.current !== parentId) {
        throw contextChangedError();
      }
      const conversation = await ensureSideConversation(generation);
      const shouldClearInput = await onCommandSelect(
        commandId,
        rawInput,
        conversation.id,
      );
      if (shouldClearInput !== false) setInput("");
    } catch (commandError) {
      if (commandError instanceof DOMException && commandError.name === "AbortError") return;
      setError(
        commandError instanceof Error
          ? commandError.message
          : "サイドチャットの command 実行に失敗しました。",
      );
    }
  };

  const handleAtFileAttach = (path: string) => {
    const normalizedPath = path.trim();
    if (mode !== "coding" || !normalizedPath) return;
    if (hasWorkspaceAttachment(attachedFiles, normalizedPath)) return;
    if (pendingMentionAttachmentRequestsRef.current.has(normalizedPath)) return;

    const generation = generationRef.current;
    const expectedParentId = parentId;
    const token = mentionAttachmentTokenRef.current + 1;
    mentionAttachmentTokenRef.current = token;
    pendingMentionAttachmentRequestsRef.current.set(normalizedPath, token);
    setPendingMentionAttachmentPaths((current) => [...current, normalizedPath]);

    void sideChatResources.readWorkspaceFile(normalizedPath, {
      workspace_id: workspaceId ?? undefined,
    }).then((result) => {
      if (
        pendingMentionAttachmentRequestsRef.current.get(normalizedPath) !== token
        || generation !== generationRef.current
        || expectedParentId !== parentIdRef.current
      ) return;
      setAttachedFiles((current) => hasWorkspaceAttachment(current, normalizedPath)
        ? current
        : [
            ...current,
            workspaceFileToAttachment(
              result.path || normalizedPath,
              result.content,
              result.size,
            ),
          ]);
    }).catch((readError) => {
      if (
        pendingMentionAttachmentRequestsRef.current.get(normalizedPath) !== token
        || generation !== generationRef.current
        || expectedParentId !== parentIdRef.current
      ) return;
      setError(readError instanceof Error
        ? readError.message
        : "workspace file の添付に失敗しました。");
    }).finally(() => {
      if (pendingMentionAttachmentRequestsRef.current.get(normalizedPath) !== token) {
        return;
      }
      pendingMentionAttachmentRequestsRef.current.delete(normalizedPath);
      setPendingMentionAttachmentPaths((current) => (
        current.filter((candidate) => candidate !== normalizedPath)
      ));
    });
  };

  const handlePendingMentionAttachmentRemove = (path: string) => {
    pendingMentionAttachmentRequestsRef.current.delete(path);
    setPendingMentionAttachmentPaths((current) => (
      current.filter((candidate) => candidate !== path)
    ));
  };

  const updateDraft = (
    conversationId: string,
    draftId: string,
    updater: (message: ChatMessage) => ChatMessage,
  ) => {
    setSideConversation((current) => current?.id === conversationId
      ? {
          ...current,
          messages: current.messages.map((message) => (
            message.id === draftId ? updater(message) : message
          )),
        }
      : current);
  };

  const submit = async (text: string, files: AttachedFile[]) => {
    if (!parentId || isGenerating || (!text.trim() && files.length === 0)) return;
    const commandName = text.trim().match(/^\/([^\s]+)/)?.[1]?.toLowerCase();
    const command = commandName
      ? commands.find((candidate) => (
          candidate.id.toLowerCase() === commandName
          || candidate.name?.toLowerCase() === commandName
        ))
      : undefined;
    if (command) {
      await handleSideCommand(command.id, text);
      return;
    }

    const generation = generationRef.current;
    setError(null);
    setRetryDraft(null);
    setIsGenerating(true);
    setInput("");
    setAttachedFiles([]);
    try {
      await awaitParentContextSync?.(parentId);
      if (generation !== generationRef.current || parentIdRef.current !== parentId) {
        throw contextChangedError();
      }
      const conversation = await ensureSideConversation(generation);
      if (!sideChatContextIsCurrent(
        generation,
        generationRef.current,
        parentId,
        parentIdRef.current,
        conversation,
      )) throw contextChangedError();
      const userText = text.trim() || "添付ファイルを確認してください。";
      const submittedWidgets = droppedWidgets.filter((widget) => {
        const mention = widget.metadata?.mention;
        if (!mention || typeof mention !== "object" || Array.isArray(mention)) {
          return widget.enabled !== false;
        }
        const syntax = String(
          (mention as Record<string, unknown>).syntax ?? `@${widget.label}`,
        );
        return userText.includes(syntax);
      });
      const submittedMentions = composerMentionMetadataFromWidgets(submittedWidgets);
      const mentionedToolIds = composerMentionToolIdsFromWidgets(submittedWidgets);
      const submittedToolIds = [...new Set([...selectedToolIds, ...mentionedToolIds])];
      const submittedSkillIds = [...new Set(
        submittedMentions
          .filter((mention) => mention.kind === "skill")
          .map((mention) => mention.id),
      )];
      const userMessage = optimisticMessage(
        conversation.id,
        "user",
        userText,
        undefined,
        submittedMentions.length ? { mentions: submittedMentions } : undefined,
      );
      const assistantDraft = optimisticMessage(
        conversation.id,
        "assistant",
        "",
        selectedModel || conversation.model,
      );
      setSideConversation({
        ...conversation,
        messages: [...conversation.messages, userMessage, assistantDraft],
      });
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const toolSelection: ToolSelectionRequest = submittedToolIds.length > 0
        ? {
            mode: "manual",
            include: submittedToolIds.map((id) => ({ kind: "tool", id })),
            exclude: [],
            scope: "turn",
            must_use: false,
          }
        : { mode: "auto", include: [], exclude: [], scope: "turn", must_use: false };

      await sideChatResources.streamMessage(conversation.id, userText, {
        params: { ...templateParams, ...(selectedModel ? { model: selectedModel } : {}) },
        thinking_level: selectedProfile?.supports_thinking ? thinkingLevel : null,
        deepthink_enabled: deepthinkEnabled,
        tool_selection: toolSelection,
        tool_policy: {
          ...templateToolPolicy,
          action_approval_mode: actionApprovalMode,
          ...(fullAccess ? {
            yolo_mode: true,
            allow_shell: true,
            allow_file_write: true,
            write_actions_require_approval: false,
            full_access: true,
          } : {}),
          ...(workspaceId ? { workspace_id: workspaceId } : {}),
          ...(disabledToolIds.length ? { disabled_tools: disabledToolIds } : {}),
          ...(submittedToolIds.length ? { selected_tools: submittedToolIds } : {}),
        },
        attachments: files,
        tools: submittedToolIds.length ? submittedToolIds : undefined,
        metadata: {
          mode,
          ...sideChatRequestMetadata(parentId, {
            id: workspaceId,
            label: workspaceLabel,
            root: workspaceRoot,
          }),
          selected_tools: submittedToolIds,
          ...(submittedSkillIds.length ? { skills: submittedSkillIds } : {}),
          ...(submittedMentions.length ? { mentions: submittedMentions } : {}),
          dropped_widgets: submittedWidgets,
          attachments: files.map(({ name, size, type, source, sourcePath }) => ({
            name,
            size,
            type,
            source,
            sourcePath,
          })),
        },
      }, {
        signal: controller.signal,
        onUserMessage: (message) => {
          if (generation !== generationRef.current) return;
          setSideConversation((current) => current?.id === conversation.id
            ? {
                ...current,
                messages: current.messages.map((candidate) => (
                  candidate.id === userMessage.id ? message : candidate
                )),
              }
            : current);
        },
        onDelta: (delta) => {
          if (generation !== generationRef.current) return;
          updateDraft(conversation.id, assistantDraft.id, (message) => {
            const nextText = `${message.raw_text ?? ""}${delta}`;
            return { ...message, content: [{ type: "text", text: nextText }], raw_text: nextText };
          });
        },
        onThinkingDelta: (delta) => {
          if (generation !== generationRef.current) return;
          updateDraft(conversation.id, assistantDraft.id, (message) => {
            const metadata = message.metadata ?? {};
            const thinking = metadata.thinking && typeof metadata.thinking === "object"
              ? metadata.thinking as Record<string, unknown>
              : {};
            return {
              ...message,
              metadata: {
                ...metadata,
                thinking: {
                  ...thinking,
                  transcript: `${String(thinking.transcript ?? "")}${delta}`,
                },
              },
            };
          });
        },
        onEvent: (event) => {
          if (generation !== generationRef.current || !isActivityEvent(event)) return;
          updateDraft(conversation.id, assistantDraft.id, (message) => ({
            ...message,
            events: [...(message.events ?? []), event as ChatActivityEvent],
          }));
        },
        onMessage: (message) => {
          if (generation !== generationRef.current) return;
          setSideConversation((current) => {
            if (!current || current.id !== conversation.id) return current;
            const withoutDraft = current.messages.filter(
              (candidate) => candidate.id !== assistantDraft.id,
            );
            return {
              ...current,
              messages: withoutDraft.some((candidate) => candidate.id === message.id)
                ? withoutDraft.map((candidate) => candidate.id === message.id ? message : candidate)
                : [...withoutDraft, message],
            };
          });
        },
      });
      if (generation === generationRef.current) {
        const refreshed = await sideChatResources.getConversation(conversation.id);
        if (generation === generationRef.current) {
          setSideConversation(refreshed);
          setDroppedWidgets([]);
          setEntityReferences([]);
        }
      }
    } catch (submitError) {
      if (generation !== generationRef.current) return;
      if (submitError instanceof DOMException && submitError.name === "AbortError") return;
      setRetryDraft({ text, files });
      setInput(text);
      setAttachedFiles(files);
      setError(submitError instanceof ChatStreamInterruptedError
        ? "応答ストリームが途中で切れました。再試行できます。"
        : submitError instanceof Error
          ? submitError.message
          : "サイドチャットの送信に失敗しました。");
    } finally {
      if (generation === generationRef.current) {
        abortControllerRef.current = null;
        setIsGenerating(false);
      }
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit(input, attachedFiles);
  };

  const handleStop = () => {
    generationRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (sideConversation?.id) {
      void sideChatResources.stopMessage(sideConversation.id).catch(() => undefined);
    }
    setIsGenerating(false);
  };

  if (!parentConversation) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center px-5 text-center" data-testid="side-chat-empty-parent">
        <MessageSquareText size={24} className="text-zinc-600" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-zinc-300">新しいチャットのサイドチャット</p>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          メインチャットを開始すると、ここに空の補助会話が作成されます。
        </p>
      </div>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b]" aria-label="サイドチャット" data-testid="side-chat-panel">
      <div className="flex items-center justify-between border-b border-zinc-800/70 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-[11px] font-medium text-zinc-300">現在のチャットに紐づく補助会話</p>
          <p className="truncate text-[10px] text-zinc-600">
            {selectedProfile?.display_name ?? selectedModel}
          </p>
        </div>
        {isLoading && <Loader2 size={14} className="animate-spin text-zinc-500" aria-label="読み込み中" />}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <Messages
          error={error}
          isMessagesRegionVisible
          isLoading={isLoading}
          isNewConversation={!sideConversation || messages.length === 0}
          isGenerating={isGenerating}
          pendingStatus={isGenerating ? `${selectedProfile?.display_name ?? selectedModel} が思考中` : null}
          pendingToolNames={[]}
          pendingStartedAt={null}
          pendingToolStartedAt={{}}
          messages={messages}
          messagesEndRef={messagesEndRef}
          messagesScrollRef={messagesScrollRef}
          unknownBlockStrategy={unknownBlockStrategy}
          showActivityInMessages={showActivityInMessages}
          showWidgets={showWidgets}
          showPromptUsageInMessages={showPromptUsageInMessages}
          onSuggestionClick={setInput}
          onRetry={retryDraft ? () => void submit(retryDraft.text, retryDraft.files) : undefined}
          onDismissError={() => {
            setError(null);
            setRetryDraft(null);
          }}
        />
      </div>
      <div className="border-t border-zinc-800/70">
        {approvalSurface}
        <Composer
          input={input}
          placeholder="サイドチャットにメッセージ"
          isNewConversation={false}
          isGenerating={isGenerating}
          selectedProfile={selectedProfile}
          favoriteProfiles={favoriteProfiles}
          modelProfiles={modelProfiles}
          thinkingLevel={thinkingLevel}
          contextUsage={contextUsage}
          inlineExtensions={inlineExtensions}
          belowExtensions={[]}
          skillExtensions={skillExtensions}
          commands={commands}
          mode={mode}
          attachedFiles={attachedFiles}
          pendingMentionAttachmentPaths={pendingMentionAttachmentPaths}
          droppedWidgets={droppedWidgets}
          entityReferences={entityReferences}
          selectedToolIds={selectedToolIds}
          actionApprovalMode={actionApprovalMode}
          suppressPopovers={isLoading}
          onOpenModelManager={onOpenModelManager}
          onOpenToolSettings={onOpenToolSettings}
          onActionApprovalModeChange={onActionApprovalModeChange}
          onExtensionSelect={onExtensionSelect}
          onCommandSelect={(commandId, rawInput) => {
            void handleSideCommand(commandId, rawInput);
          }}
          onModelProfileSelect={onModelProfileSelect}
          onThinkingLevelChange={onThinkingLevelChange}
          onInputChange={setInput}
          onSubmit={handleSubmit}
          onStopGenerating={handleStop}
          onFileAttach={(files) => setAttachedFiles((current) => [...current, ...files])}
          onAtFileAttach={handleAtFileAttach}
          onPendingMentionAttachmentRemove={handlePendingMentionAttachmentRemove}
          onFileRemove={(fileId) => setAttachedFiles((current) => (
            current.filter((file) => file.id !== fileId)
          ))}
          onDropWidget={(widget) => setDroppedWidgets((current) => (
            current.some((candidate) => candidate.id === widget.id)
              ? current.map((candidate) => candidate.id === widget.id ? widget : candidate)
              : [...current, widget]
          ))}
          onEntityReferencesChange={setEntityReferences}
        />
      </div>
    </section>
  );
}
