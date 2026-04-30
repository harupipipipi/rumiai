import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { ChatItem } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { api, type ChatContentBlock, type ChatMessage, type Conversation, type ModelProfile, type SettingsSection, type SidebarAction, type SidebarItem, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";
import { cn } from "./lib/cn";
import { hasShellRegion } from "./lib/uiShell";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { ChatUiMessage, ComposerExtensionItem, ContextUsageInfo } from "./renderers/types";

function useLocalStorage<T>(key: string, defaultValue: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? JSON.parse(saved) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue];
}

function formatBoardDate(updatedAt: number): string {
  const diffHours = (Date.now() - updatedAt) / 3_600_000;
  if (diffHours < 24) return "Today";
  if (diffHours < 48) return "Yesterday";
  if (diffHours < 24 * 7) return "Previous 7 Days";
  return formatRelativeTime(updatedAt);
}

function toChatItem(conversation: Conversation): ChatItem {
  return {
    id: conversation.id,
    title: conversation.title,
    date: formatBoardDate(conversation.updated_at),
    type: "chat",
  };
}

function normalizeBlocks(message: ChatMessage): ChatContentBlock[] {
  if (typeof message.content === "string") {
    return [{ type: "text", text: message.content }];
  }
  return message.content;
}

function toUiMessage(message: ChatMessage, profile?: ModelProfile | null): ChatUiMessage {
  const isUser = message.role === "user";
  const metadata = message.metadata ?? {};
  const attachedToolCount = Number(metadata.attached_tool_count ?? 0);
  return {
    id: message.id,
    role: isUser ? "user" : "agent",
    content: normalizeBlocks(message),
    rawText: messageToText(message),
    widget: message.widget,
    events: message.events ?? [],
    toolLogs: message.tool_logs ?? [],
    metadata: isUser
      ? undefined
      : {
          executionTime: formatRelativeTime(message.created_at),
          modelName: profile?.display_name ?? String(message.model ?? ""),
          thinkingLabel: String((metadata.thinking as Record<string, unknown> | undefined)?.state ?? ""),
          attachedToolCount,
        },
  };
}

function optimisticUserMessage(conversationId: string, text: string): ChatMessage {
  return {
    id: `optimistic-${Date.now()}`,
    role: "user",
    content: [{ type: "text", text }],
    raw_text: text,
    created_at: Date.now(),
    conversation_id: conversationId,
    parent_id: null,
    children_ids: [],
    sequence_number: 0,
    finish_reason: null,
    usage: null,
    widget: null,
  };
}

function previewFromAction(action: SidebarAction, title: string, data: unknown): ToolPreviewItem {
  const content = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return {
    id: `sidebar-${action.id}-${Date.now()}`,
    toolStepId: action.id,
    timestamp: Date.now(),
    data: {
      type: "file",
      filename: `${title}.json`,
      size: "sidebar action",
      content,
    },
  };
}

function profileKey(profile: ModelProfile | null | undefined, fallback: string): string {
  return profile?.profile_id || profile?.qualified_model_id || fallback;
}

function findProfile(profiles: ModelProfile[], modelId: string): ModelProfile | null {
  return profiles.find((profile) => (
    profile.profile_id === modelId
    || profile.qualified_model_id === modelId
    || `${profile.provider_id}/${profile.model_id}` === modelId
  )) ?? null;
}

function favoriteModelProfiles(rawFavorites: unknown, profiles: ModelProfile[], preferredModel: string): ModelProfile[] {
  const favoriteIds = Array.isArray(rawFavorites)
    ? rawFavorites.map((item) => String(item))
    : typeof rawFavorites === "string"
      ? rawFavorites.split(/\r?\n|,/).map((item) => item.trim())
      : [preferredModel];
  const uniqueIds = favoriteIds.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index);
  const selected = uniqueIds
    .map((profileId) => findProfile(profiles, profileId) ?? {
      profile_id: profileId,
      qualified_model_id: profileId,
      display_name: profileId,
      max_context: -1,
      supports_thinking: false,
      thinking_levels: [],
    })
    .filter(Boolean);
  if (selected.length > 0) return selected;
  const fallback = findProfile(profiles, preferredModel);
  return fallback ? [fallback] : [];
}

function contextUsageFor(conversation: Conversation | null, profile: ModelProfile | null): ContextUsageInfo {
  const usedTokens = (conversation?.messages ?? []).reduce((total, message) => {
    const usage = message.usage ?? {};
    return total + Number(usage.total_tokens ?? usage.input_tokens ?? usage.prompt_tokens ?? 0);
  }, 0);
  const maxContext = Number(profile?.max_context_tokens ?? profile?.max_context ?? 0);
  if (maxContext < 0) {
    return { usedTokens, maxContext, ratio: 0, label: "∞" };
  }
  if (!maxContext) {
    return { usedTokens, maxContext: 0, ratio: 0, label: "?" };
  }
  const ratio = Math.min(1, Math.max(0, usedTokens / maxContext));
  return { usedTokens, maxContext, ratio, label: `${Math.round(ratio * 100)}%` };
}

function composerExtensionItems(items: SidebarItem[]): ComposerExtensionItem[] {
  return items
    .filter((item) => item.category === "tool" || item.category === "capability")
    .slice(0, 6)
    .map((item) => ({
      id: item.id,
      label: item.label,
      category: item.category,
      description: item.description,
    }));
}

export default function App() {
  const [catalog, setCatalog] = useState<UICatalog | null>(null);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [settingsSections, setSettingsSections] = useState<SettingsSection[]>([]);
  const [settingsValues, setSettingsValues] = useState<Record<string, Record<string, unknown>>>({});
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useLocalStorage("rumi-input", "");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useLocalStorage("rumi-show-preview", false);
  const [previewMode, setPreviewMode] = useLocalStorage<ToolPreviewMode>("rumi-preview-mode", "auto");
  const [activePreviewId, setActivePreviewId] = useState<string | null>(null);
  const [previews, setPreviews] = useState<ToolPreviewItem[]>([]);
  const [health, setHealth] = useState<{ status: string; pack: string; ts: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = conversations.map(toChatItem);
  const activeModelId = activeConversation?.model ?? String(settingsValues.models?.preferred_model ?? "openrouter/tencent/hy3-preview:free").trim();
  const activeProfile = findProfile(modelProfiles, activeModelId);
  const messages = activeConversation ? activeConversation.messages.map((message) => toUiMessage(message, activeProfile)) : [];
  const activeChatTitle = activeConversation?.title ?? "New Conversation";
  const isNewConversation = activeConversation === null || activeConversation.messages.length === 0;
  const placeholder = String(settingsValues.general?.composer_placeholder ?? "メッセージを入力...");
  const preferredModel = activeModelId;
  const favoriteProfiles = favoriteModelProfiles(settingsValues.models?.favorite_profiles, modelProfiles, preferredModel);
  const thinkingLevels = (settingsValues.models?.thinking_level_by_profile ?? {}) as Record<string, unknown>;
  const selectedThinkingLevel = String(thinkingLevels[profileKey(activeProfile, preferredModel)] ?? activeProfile?.default_thinking_level ?? "medium");
  const contextUsage = contextUsageFor(activeConversation, activeProfile);
  const composerExtensions = composerExtensionItems(sidebarItems);
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "json");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  async function refreshHealth() {
    try {
      setHealth(await api.health());
    } catch (healthError) {
      console.error(healthError);
    }
  }

  async function refreshCatalog() {
    const [nextCatalog, nextSettings, profilesResult] = await Promise.all([api.uiCatalog(), api.uiSettings(), api.listModelProfiles()]);
    setCatalog(nextCatalog);
    setModelProfiles(profilesResult.profiles);
    setSettingsSections(nextSettings.sections);
    setSettingsValues(nextSettings.values);
    const defaultMode = nextSettings.values.preview?.default_mode;
    if (defaultMode === "auto" || defaultMode === "manual") {
      setPreviewMode(defaultMode);
    }
  }

  async function refreshPreview(conversationId: string | null) {
    if (!conversationId) {
      setPreviews([]);
      setActivePreviewId(null);
      return;
    }
    try {
      const result = await api.conversationPreview(conversationId);
      const limit = Number(settingsValues.preview?.max_items ?? 12);
      const nextPreviews = result.previews.slice(0, limit);
      setPreviews(nextPreviews);
      setActivePreviewId(nextPreviews[0]?.id ?? null);
      if (settingsValues.preview?.auto_open && nextPreviews.length > 0) {
        setShowPreview(true);
      }
    } catch (previewError) {
      console.error(previewError);
      setPreviews([]);
      setActivePreviewId(null);
    }
  }

  async function loadConversation(conversationId: string | null) {
    if (!conversationId) {
      setActiveConversationId(null);
      setActiveConversation(null);
      await refreshPreview(null);
      return;
    }
    const conversation = await api.getConversation(conversationId);
    setActiveConversationId(conversationId);
    setActiveConversation(conversation);
    await refreshPreview(conversationId);
  }

  async function refreshConversations(preferredId?: string | null) {
    const result = await api.listConversations();
    setConversations(result.conversations);

    const targetId = preferredId ?? activeConversationId ?? result.conversations[0]?.id ?? null;
    if (!targetId) {
      setActiveConversationId(null);
      setActiveConversation(null);
      await refreshPreview(null);
      return;
    }

    if (!result.conversations.some((conversation) => conversation.id === targetId)) {
      await loadConversation(result.conversations[0]?.id ?? null);
      return;
    }

    await loadConversation(targetId);
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setIsLoading(true);
      try {
        await Promise.all([refreshHealth(), refreshCatalog()]);
        if (!cancelled) {
          await refreshConversations(null);
        }
      } catch (bootstrapError) {
        if (!cancelled) {
          setError(
            bootstrapError instanceof Error
              ? bootstrapError.message
              : "defaultspack の読み込みに失敗しました。",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshPreview(activeConversationId);
  }, [settingsValues.preview?.max_items, settingsValues.preview?.auto_open, activeConversationId]);

  const handleNewTask = () => {
    setActiveConversationId(null);
    setActiveConversation(null);
    setPreviews([]);
    setError(null);
  };

  const handleHistoryClick = (conversationId: string) => {
    setError(null);
    void loadConversation(conversationId);
  };

  const handleSettingChange = (sectionId: string, fieldId: string, value: unknown) => {
    setSettingsValues((current) => {
      const section = settingsSections.find((item) => item.id === sectionId);
      const field = section?.fields.find((item) => item.id === fieldId);
      const next = {
        ...current,
        [sectionId]: {
          ...(current[sectionId] ?? {}),
          [fieldId]: field?.type === "secret" ? "" : value,
        },
      };
      if (field?.type === "secret") {
        const providerId = field.provider_id ?? fieldId.replace(/_api_key$/, "");
        void api.saveProviderApiKey(providerId, String(value ?? ""))
          .then(() => refreshCatalog())
          .catch(console.error);
      } else {
        void api.updateUiSettings(next).then((result) => setSettingsValues(result.values)).catch(console.error);
      }
      return next;
    });
  };

  const updateModelSettings = (updates: Record<string, unknown>) => {
    const next = {
      ...settingsValues,
      models: {
        ...(settingsValues.models ?? {}),
        ...updates,
      },
    };
    setSettingsValues(next);
    void api.updateUiSettings(next).then((result) => setSettingsValues(result.values)).catch(console.error);
  };

  const handleModelProfileSelect = (profileId: string) => {
    updateModelSettings({ preferred_model: profileId });
    if (activeConversationId) {
      void api.updateConversation(activeConversationId, { model: profileId }).then((conversation) => {
        setActiveConversation(conversation);
        void refreshConversations(conversation.id);
      }).catch(console.error);
    }
  };

  const handleThinkingLevelChange = (level: string | null) => {
    const key = profileKey(activeProfile, preferredModel);
    updateModelSettings({
      thinking_level_by_profile: {
        ...thinkingLevels,
        [key]: level,
      },
    });
  };

  const pushActionPreview = (action: SidebarAction, title: string, data: unknown) => {
    const preview = previewFromAction(action, title, data);
    setPreviews((current) => [preview, ...current].slice(0, 30));
    setActivePreviewId(preview.id);
    setShowPreview(true);
  };

  const handlePanelAction = async (item: SidebarItem, action: SidebarAction) => {
    setError(null);
    try {
      let result: unknown;
      if (action.id === "conversation.export") {
        if (!activeConversationId) throw new Error("エクスポートする会話がありません。");
        result = await api.exportConversation(activeConversationId, String(action.payload?.format ?? "markdown"));
      } else if (action.id === "conversation.share") {
        if (!activeConversationId) throw new Error("共有する会話がありません。");
        const exported = await api.exportConversation(activeConversationId, "markdown");
        result = await api.createShare({
          target_type: "conversation",
          target_id: activeConversationId,
          title: activeChatTitle,
          content: exported.content,
          visibility: "local",
        });
      } else if (action.id === "artifacts.list") {
        result = await api.listArtifacts();
      } else if (action.id === "research.web") {
        result = await api.webSearch(String(input || activeChatTitle || "rumi"), false);
      } else if (action.id === "research.reddit") {
        result = await api.redditSearch(String(input || activeChatTitle || "rumi"), false);
      } else if (action.id === "browser.session") {
        result = await api.browserComputer("browser.session", { dry_run: true });
      } else if (action.id === "browser.screenshot.dry_run") {
        result = await api.browserComputer("computer.screenshot", { dry_run: true });
      } else if (action.id === "schedules.list") {
        result = await api.listSchedules();
      } else if (action.id === "channels.list") {
        result = await api.listChannels();
      } else if (action.endpoint) {
        result = await fetch(action.endpoint, { method: action.method ?? "GET" }).then((response) => response.json());
      } else {
        result = { item: item.id, action: action.id, status: "ready" };
      }
      pushActionPreview(action, action.label, result);
      const text = typeof result === "string" ? result : JSON.stringify(result, null, 2);
      void navigator.clipboard?.writeText(text).catch(() => undefined);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "サイドバー操作に失敗しました。");
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || isGenerating) return;

    const userText = input.trim();
    setIsGenerating(true);
    setError(null);
    setInput("");

    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await api.createConversation({
          model: preferredModel || "stub/default",
        });
        setActiveConversationId(conversation.id);
      }

      const title =
        conversation.title === "New Conversation"
          ? deriveConversationTitle(userText)
          : conversation.title;
      const optimisticConversation = {
        ...conversation,
        title,
        updated_at: Date.now(),
        messages: [...conversation.messages, optimisticUserMessage(conversation.id, userText)],
      };
      setActiveConversation(optimisticConversation);
      setConversations((current) => {
        const item = {
          ...optimisticConversation,
          messages: [],
        };
        const withoutCurrent = current.filter((candidate) => candidate.id !== conversation.id);
        return [item, ...withoutCurrent];
      });

      await api.sendMessage(conversation.id, userText, {
        thinking_level: activeProfile?.supports_thinking ? selectedThinkingLevel : null,
      });

      if (title !== conversation.title) {
        await api.updateConversation(conversation.id, { title });
      }

      await refreshConversations(conversation.id);
    } catch (submitError) {
      console.error("Chat error:", submitError);
      setInput(userText);
      setError(
        submitError instanceof Error
          ? submitError.message
          : "メッセージ送信に失敗しました。",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const Renderers = useMemo(() => resolveDefaultspackRenderers(catalog), [catalog]);

  return (
    <RendererBoundary>
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-zinc-800">
      {showRegion("title_bar") && <Renderers.titleBar appName={catalog?.app?.name} appIcon={catalog?.app?.icon} />}

      <div className="flex flex-1 min-h-0">
        {showRegion("history") && (
          <Renderers.historyBoard
            activeChatId={activeConversationId}
            chatItems={chatItems}
            account={catalog?.app?.account}
            onChatSelect={handleHistoryClick}
            onNewTask={handleNewTask}
            onSettingsClick={() => setIsSettingsOpen(true)}
          />
        )}

        <main className="flex-1 flex min-w-0 bg-[#09090b] relative">
          <div className={cn("flex-1 flex flex-col min-w-0", showPreview && "border-r border-zinc-800/40")}>
            {showRegion("chat_header") && (
              <Renderers.chatHeader
                title={activeChatTitle}
                showPreview={showPreview}
                canShowPreview={showRegion("activity_preview")}
                canOpenSettings={showRegion("settings_modal")}
                onTogglePreview={() => setShowPreview((value) => !value)}
                onOpenSettings={() => setIsSettingsOpen(true)}
              />
            )}

            <Renderers.chatMessages
              error={error}
              isMessagesRegionVisible={showRegion("chat_messages")}
              isLoading={isLoading}
              isNewConversation={isNewConversation}
              isGenerating={isGenerating}
              messages={messages}
              messagesEndRef={messagesEndRef}
              unknownBlockStrategy={unknownBlockStrategy}
              showActivityInMessages={showActivityInMessages}
              showWidgets={showWidgets}
              onSuggestionClick={(text) => setInput(text)}
            />

            {showRegion("composer") && (
              <Renderers.composer
                input={input}
                placeholder={placeholder}
                isGenerating={isGenerating}
                selectedProfile={activeProfile}
                favoriteProfiles={favoriteProfiles}
                thinkingLevel={activeProfile?.supports_thinking ? selectedThinkingLevel : null}
                contextUsage={contextUsage}
                inlineExtensions={composerExtensions.slice(0, 3)}
                belowExtensions={composerExtensions.slice(3)}
                onModelProfileSelect={handleModelProfileSelect}
                onThinkingLevelChange={handleThinkingLevelChange}
                onInputChange={setInput}
                onSubmit={handleSubmit}
              />
            )}
          </div>

          {showRegion("activity_preview") && showPreview && (
            <Renderers.toolPreviewPanel
              previews={previews}
              showPreview={showPreview}
              onClose={() => setShowPreview(false)}
              previewMode={previewMode}
              onModeChange={setPreviewMode}
              activePreviewId={activePreviewId}
            />
          )}
        </main>

        {showRegion("right_sidebar") && (
          <Renderers.rightSidebar
            items={sidebarItems}
            settingsValues={settingsValues}
            settingsSections={settingsSections}
            onSettingChange={handleSettingChange}
            onOpenSettings={() => setIsSettingsOpen(true)}
            onPanelAction={handlePanelAction}
          />
        )}
      </div>

      {showRegion("settings_modal") && (
        <Renderers.settingsModal
          isOpen={isSettingsOpen}
          catalog={catalog}
          health={health}
          previewsCount={previews.length}
          settingsSections={settingsSections}
          settingsValues={settingsValues}
          onClose={() => setIsSettingsOpen(false)}
          onSettingChange={handleSettingChange}
        />
      )}
    </div>
    </RendererBoundary>
  );
}
