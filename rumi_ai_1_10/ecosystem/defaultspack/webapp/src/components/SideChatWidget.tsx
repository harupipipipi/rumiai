import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type FormEvent,
} from "react";
import { Loader2, MessageSquareText } from "lucide-react";

import {
  ChatStreamInterruptedError,
  api,
  type ChatActivityEvent,
  type ChatContentBlock,
  type ChatMessage,
  type ChatStreamEvent,
  type ComposerCommandItem,
  type Conversation,
  type ModelProfile,
  type TemplateComposerInput,
  type ToolSelectionRequest,
} from "../lib/api";
import type { ActionApprovalMode } from "../features/tools/ActionApprovalControl";
import { messageToText, orderConversationMessages } from "../lib/chat";
import {
  findSideChatConversation,
  sideChatCreateOptions,
} from "../lib/sideChat";
import type {
  AppMode,
  AttachedFile,
  ChatMessagesRendererProps,
  ChatUiMessage,
  ComposerExtensionItem,
  ComposerRendererProps,
  ComposerSkillItem,
  ContextUsageInfo,
} from "../renderers/types";

type SideChatWidgetProps = {
  parentConversation: Conversation | null;
  selectedModel: string;
  selectedProfile: ModelProfile | null;
  modelProfiles: ModelProfile[];
  thinkingLevel: string | null;
  deepthinkEnabled: boolean;
  contextUsage: ContextUsageInfo;
  inlineExtensions: ComposerExtensionItem[];
  skillExtensions?: ComposerSkillItem[];
  commands?: ComposerCommandItem[];
  composerInput?: TemplateComposerInput | null;
  selectedToolIds: string[];
  disabledToolIds?: string[];
  actionApprovalMode: ActionApprovalMode;
  yoloMode: boolean;
  ultraYoloMode: boolean;
  mode: AppMode;
  workspaceId?: string | null;
  workspaceLabel?: string | null;
  workspaceRoot?: string | null;
  templateParams?: Record<string, unknown>;
  templateToolPolicy?: Record<string, unknown>;
  voiceInputEnabled?: boolean;
  voiceInputUseAi?: boolean;
  unknownBlockStrategy: string;
  showActivityInMessages: boolean;
  showWidgets: boolean;
  showPromptUsageInMessages?: boolean;
  composerRenderer: ComponentType<ComposerRendererProps>;
  messagesRenderer: ComponentType<ChatMessagesRendererProps>;
  onOpenModelManager?: () => void;
  onOpenToolSettings?: () => void;
  onActionApprovalModeChange?: (mode: ActionApprovalMode) => void;
  onExtensionSelect?: (item: ComposerExtensionItem) => void;
  onCommandSelect?: (commandId: string, rawInput?: string) => void;
  onModelProfileSelect: (profileId: string) => void;
  onThinkingLevelChange: (level: string | null) => void;
};

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
    thinkingLabel: typeof thinking.label === "string" ? thinking.label : undefined,
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
    authorityFollowup: metadata.authority_followup && typeof metadata.authority_followup === "object"
      ? metadata.authority_followup as Record<string, unknown>
      : undefined,
    mentions: Array.isArray(metadata.mentions)
      ? metadata.mentions as NonNullable<ChatUiMessage["metadata"]>["mentions"]
      : undefined,
    promptUsage: metadata.prompt_usage && typeof metadata.prompt_usage === "object"
      ? metadata.prompt_usage as NonNullable<ChatUiMessage["metadata"]>["promptUsage"]
      : undefined,
  };
}

function chatMessageToUi(message: ChatMessage): ChatUiMessage {
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

function optimisticUserMessage(conversationId: string, text: string): ChatMessage {
  return {
    id: `side-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "user",
    content: [{ type: "text", text }],
    raw_text: text,
    created_at: Date.now(),
    conversation_id: conversationId,
  };
}

function optimisticAssistantMessage(conversationId: string, model: string): ChatMessage {
  return {
    id: `side-assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: "assistant",
    content: [{ type: "text", text: "" }],
    raw_text: "",
    created_at: Date.now(),
    conversation_id: conversationId,
    model,
    metadata: {
      thinking: { state: "thinking", transcript: "" },
    },
    events: [],
  };
}

function isActivityEvent(event: ChatStreamEvent): boolean {
  return ![
    "delta",
    "thinking_delta",
    "message",
    "done",
    "user_message",
    "error",
  ].includes(event.type);
}

function attachmentPayload(files: AttachedFile[]) {
  return files.map(({
    name,
    content,
    dataUrl,
    size,
    type,
    truncated,
    source,
    sourcePath,
  }) => ({
    name,
    content,
    dataUrl,
    size,
    type,
    truncated,
    source,
    sourcePath,
  }));
}

export function SideChatWidget({
  parentConversation,
  selectedModel,
  selectedProfile,
  modelProfiles,
  thinkingLevel,
  deepthinkEnabled,
  contextUsage,
  inlineExtensions,
  skillExtensions = [],
  commands = [],
  composerInput = null,
  selectedToolIds,
  disabledToolIds = [],
  actionApprovalMode,
  yoloMode,
  ultraYoloMode,
  mode,
  workspaceId,
  workspaceLabel,
  workspaceRoot,
  templateParams = {},
  templateToolPolicy = {},
  voiceInputEnabled = true,
  voiceInputUseAi = false,
  unknownBlockStrategy,
  showActivityInMessages,
  showWidgets,
  showPromptUsageInMessages = false,
  composerRenderer: Composer,
  messagesRenderer: Messages,
  onOpenModelManager,
  onOpenToolSettings,
  onActionApprovalModeChange,
  onExtensionSelect,
  onCommandSelect,
  onModelProfileSelect,
  onThinkingLevelChange,
}: SideChatWidgetProps) {
  const [sideConversation, setSideConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);
  const draftByParentRef = useRef(new Map<string, string>());

  const parentId = parentConversation?.id ?? null;
  const messages = useMemo(
    () => orderConversationMessages(sideConversation?.messages ?? []).map(chatMessageToUi),
    [sideConversation],
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isGenerating]);

  useEffect(() => {
    generationRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setSideConversation(null);
    setAttachedFiles([]);
    setError(null);
    setIsGenerating(false);
    setInput(parentId ? draftByParentRef.current.get(parentId) ?? "" : "");
    if (!parentId || !parentConversation) {
      setIsLoading(false);
      return;
    }

    const generation = generationRef.current;
    let cancelled = false;
    setIsLoading(true);
    void (async () => {
      try {
        const freshParent = await api.getConversation(parentId).catch(() => parentConversation);
        const childIds = [...new Set(freshParent.child_conversation_ids ?? [])];
        const children = await Promise.all(childIds.map((childId) => (
          api.getConversation(childId).catch(() => null)
        )));
        if (cancelled || generation !== generationRef.current) return;
        setSideConversation(findSideChatConversation(children, parentId));
      } catch (loadError) {
        if (cancelled || generation !== generationRef.current) return;
        setError(loadError instanceof Error ? loadError.message : "サイドチャットを読み込めませんでした。");
      } finally {
        if (!cancelled && generation === generationRef.current) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [parentConversation, parentId]);

  const ensureSideConversation = async (): Promise<Conversation> => {
    if (!parentConversation) throw new Error("先にメインチャットを作成してください。");
    if (
      sideConversation?.parent_conversation_id === parentConversation.id
      && sideConversation.conversation_kind === "side"
    ) {
      return sideConversation;
    }

    const freshParent = await api.getConversation(parentConversation.id).catch(() => parentConversation);
    const children = await Promise.all((freshParent.child_conversation_ids ?? []).map((childId) => (
      api.getConversation(childId).catch(() => null)
    )));
    const existing = findSideChatConversation(children, parentConversation.id);
    if (existing) {
      setSideConversation(existing);
      return existing;
    }

    const created = await api.createConversation(
      sideChatCreateOptions(parentConversation, selectedModel),
    );
    setSideConversation(created);
    return created;
  };

  const updateDraftMessage = (
    conversationId: string,
    draftId: string,
    updater: (message: ChatMessage) => ChatMessage,
  ) => {
    setSideConversation((current) => {
      if (!current || current.id !== conversationId) return current;
      return {
        ...current,
        messages: current.messages.map((message) => (
          message.id === draftId ? updater(message) : message
        )),
      };
    });
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    if (parentId) draftByParentRef.current.set(parentId, value);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if ((!text && attachedFiles.length === 0) || isGenerating || !parentConversation) return;

    if (text.startsWith("/") && onCommandSelect) {
      const commandName = text.slice(1).split(/\s+/, 1)[0]?.toLowerCase();
      const command = commands.find((candidate) => (
        candidate.id.toLowerCase() === commandName
        || candidate.name?.toLowerCase() === commandName
      ));
      if (command) {
        onCommandSelect(command.id, text);
        handleInputChange("");
        return;
      }
    }

    const generation = generationRef.current;
    setError(null);
    setIsGenerating(true);
    const submittedFiles = attachedFiles;
    handleInputChange("");
    setAttachedFiles([]);

    try {
      let conversation = await ensureSideConversation();
      if (selectedModel && conversation.model !== selectedModel) {
        conversation = await api.updateConversation(conversation.id, { model: selectedModel });
        setSideConversation(conversation);
      }

      const userMessage = optimisticUserMessage(
        conversation.id,
        text || "添付ファイルを確認してください。",
      );
      const assistantDraft = optimisticAssistantMessage(
        conversation.id,
        selectedModel || conversation.model,
      );
      setSideConversation({
        ...conversation,
        messages: [...conversation.messages, userMessage, assistantDraft],
      });

      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      const operationId = typeof globalThis.crypto?.randomUUID === "function"
        ? globalThis.crypto.randomUUID()
        : `side-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
      const toolSelection: ToolSelectionRequest = selectedToolIds.length
        ? {
            mode: "manual",
            include: selectedToolIds.map((id) => ({ kind: "tool", id })),
            exclude: [],
            scope: "turn",
            must_use: false,
          }
        : {
            mode: "auto",
            include: [],
            exclude: [],
            scope: "turn",
            must_use: false,
          };

      await api.streamMessage(conversation.id, userMessage.raw_text ?? "", {
        idempotency_key: operationId,
        params: {
          ...templateParams,
          ...(selectedModel ? { model: selectedModel } : {}),
        },
        thinking_level: selectedProfile?.supports_thinking ? thinkingLevel : null,
        deepthink_enabled: deepthinkEnabled,
        tool_selection: toolSelection,
        tool_policy: {
          ...templateToolPolicy,
          action_approval_mode: actionApprovalMode,
          ...(yoloMode || ultraYoloMode
            ? {
                yolo_mode: true,
                allow_shell: true,
                allow_file_write: true,
                write_actions_require_approval: false,
              }
            : {}),
          ...(ultraYoloMode ? { full_access: true } : {}),
          ...(workspaceId ? { workspace_id: workspaceId } : {}),
          ...(disabledToolIds.length ? { disabled_tools: disabledToolIds } : {}),
          ...(selectedToolIds.length ? { selected_tools: selectedToolIds } : {}),
        },
        attachments: attachmentPayload(submittedFiles),
        tools: selectedToolIds.length ? selectedToolIds : undefined,
        metadata: {
          mode,
          conversation_channel: "side",
          parent_conversation_id: parentConversation.id,
          ...(workspaceId ? {
            workspace_id: workspaceId,
            workspace_label: workspaceLabel,
            workspace_root: workspaceRoot,
          } : {}),
          selected_tools: selectedToolIds,
          attachments: submittedFiles.map(({ name, size, type, source, sourcePath }) => ({
            name,
            size,
            type,
            source,
            sourcePath,
          })),
        },
      }, {
        signal: abortController.signal,
        onUserMessage: (message) => {
          if (generation !== generationRef.current) return;
          setSideConversation((current) => {
            if (!current || current.id !== conversation.id) return current;
            return {
              ...current,
              messages: current.messages.map((candidate) => (
                candidate.id === userMessage.id ? message : candidate
              )),
            };
          });
        },
        onDelta: (delta) => {
          if (generation !== generationRef.current) return;
          updateDraftMessage(conversation.id, assistantDraft.id, (message) => {
            const nextText = `${message.raw_text ?? ""}${delta}`;
            return {
              ...message,
              content: [{ type: "text", text: nextText }],
              raw_text: nextText,
            };
          });
        },
        onThinkingDelta: (delta) => {
          if (generation !== generationRef.current) return;
          updateDraftMessage(conversation.id, assistantDraft.id, (message) => {
            const metadata = message.metadata && typeof message.metadata === "object"
              ? message.metadata
              : {};
            const thinking = metadata.thinking && typeof metadata.thinking === "object"
              ? metadata.thinking as Record<string, unknown>
              : {};
            return {
              ...message,
              metadata: {
                ...metadata,
                thinking: {
                  ...thinking,
                  state: "thinking",
                  transcript: `${String(thinking.transcript ?? "")}${delta}`,
                },
              },
            };
          });
        },
        onEvent: (streamEvent) => {
          if (generation !== generationRef.current || !isActivityEvent(streamEvent)) return;
          updateDraftMessage(conversation.id, assistantDraft.id, (message) => ({
            ...message,
            events: [...(message.events ?? []), streamEvent as ChatActivityEvent],
          }));
        },
        onMessage: (message) => {
          if (generation !== generationRef.current) return;
          setSideConversation((current) => {
            if (!current || current.id !== conversation.id) return current;
            const withoutDraft = current.messages.filter((candidate) => candidate.id !== assistantDraft.id);
            const exists = withoutDraft.some((candidate) => candidate.id === message.id);
            return {
              ...current,
              messages: exists
                ? withoutDraft.map((candidate) => candidate.id === message.id ? message : candidate)
                : [...withoutDraft, message],
            };
          });
        },
      });

      if (generation === generationRef.current) {
        const refreshed = await api.getConversation(conversation.id);
        if (generation === generationRef.current) setSideConversation(refreshed);
      }
    } catch (submitError) {
      if (generation !== generationRef.current) return;
      if (submitError instanceof DOMException && submitError.name === "AbortError") return;
      if (submitError instanceof ChatStreamInterruptedError && submitError.partialText.trim()) {
        setError("応答streamが途中で切れました。届いた内容は保持しています。");
      } else {
        setError(submitError instanceof Error ? submitError.message : "サイドチャットの送信に失敗しました。");
      }
      handleInputChange(text);
      setAttachedFiles(submittedFiles);
    } finally {
      if (generation === generationRef.current) {
        abortControllerRef.current = null;
        setIsGenerating(false);
      }
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (sideConversation?.id) void api.stopMessage(sideConversation.id).catch(() => undefined);
    setIsGenerating(false);
  };

  if (!parentConversation) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center px-5 text-center">
        <MessageSquareText size={24} className="text-zinc-600" />
        <p className="mt-3 text-sm font-medium text-zinc-300">メインチャットを開始してください</p>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          サイドチャットは現在の会話に紐づき、作業環境・モデル・機能を共有します。
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#09090b]">
      <div className="flex items-center justify-between border-b border-zinc-800/70 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-[11px] font-medium text-zinc-300">現在のチャットに紐づく補助会話</p>
          <p className="truncate text-[10px] text-zinc-600">
            {selectedProfile?.display_name ?? selectedModel}
          </p>
        </div>
        {isLoading && <Loader2 size={14} className="animate-spin text-zinc-500" />}
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
          unknownBlockStrategy={unknownBlockStrategy}
          showActivityInMessages={showActivityInMessages}
          showWidgets={showWidgets}
          showPromptUsageInMessages={showPromptUsageInMessages}
          onSuggestionClick={handleInputChange}
        />
      </div>

      <div className="border-t border-zinc-800/70">
        <Composer
          input={input}
          placeholder="サイドチャットにメッセージ"
          isNewConversation={false}
          isGenerating={isGenerating}
          selectedProfile={selectedProfile}
          favoriteProfiles={modelProfiles}
          modelProfiles={modelProfiles}
          thinkingLevel={thinkingLevel}
          contextUsage={contextUsage}
          inlineExtensions={inlineExtensions}
          belowExtensions={[]}
          skillExtensions={skillExtensions}
          commands={commands}
          composerInput={composerInput}
          yoloMode={yoloMode || ultraYoloMode}
          voiceInputEnabled={voiceInputEnabled}
          voiceInputUseAi={voiceInputUseAi}
          mode={mode}
          attachedFiles={attachedFiles}
          selectedToolIds={selectedToolIds}
          actionApprovalMode={actionApprovalMode}
          suppressPopovers={isLoading}
          onOpenModelManager={onOpenModelManager}
          onOpenToolSettings={onOpenToolSettings}
          onActionApprovalModeChange={onActionApprovalModeChange}
          onExtensionSelect={onExtensionSelect}
          onCommandSelect={onCommandSelect}
          onModelProfileSelect={onModelProfileSelect}
          onThinkingLevelChange={onThinkingLevelChange}
          onInputChange={handleInputChange}
          onSubmit={handleSubmit}
          onStopGenerating={handleStop}
          onFileAttach={(files) => setAttachedFiles((current) => [...current, ...files])}
          onFileRemove={(fileId) => setAttachedFiles((current) => current.filter((file) => file.id !== fileId))}
        />
      </div>
    </div>
  );
}
