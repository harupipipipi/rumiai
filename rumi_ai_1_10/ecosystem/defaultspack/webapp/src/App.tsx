import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type { ChatItem } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { api, type ChatContentBlock, type ChatMessage, type Conversation, type SettingsSection, type SidebarItem, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";
import { cn } from "./lib/cn";
import { hasShellRegion } from "./lib/uiShell";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { ChatUiMessage } from "./renderers/types";

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

function toUiMessage(message: ChatMessage): ChatUiMessage {
  const isUser = message.role === "user";
  return {
    id: message.id,
    role: isUser ? "user" : "agent",
    content: normalizeBlocks(message),
    rawText: messageToText(message),
    widget: message.widget,
    metadata: isUser
      ? undefined
      : {
          toolUsed: message.finish_reason ? `defaultspack/${message.finish_reason}` : "defaultspack",
          executionTime: formatRelativeTime(message.created_at),
        },
  };
}

export default function App() {
  const [catalog, setCatalog] = useState<UICatalog | null>(null);
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

  const chatItems = conversations.map(toChatItem);
  const messages = activeConversation ? activeConversation.messages.map(toUiMessage) : [];
  const activeChatTitle = activeConversation?.title ?? "New Conversation";
  const isNewConversation = activeConversation === null || activeConversation.messages.length === 0;
  const placeholder = String(settingsValues.general?.composer_placeholder ?? "メッセージを入力...");
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "json");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
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
    const [nextCatalog, nextSettings] = await Promise.all([api.uiCatalog(), api.uiSettings()]);
    setCatalog(nextCatalog);
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

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || isGenerating) return;

    const userText = input.trim();
    setIsGenerating(true);
    setError(null);

    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await api.createConversation();
        setActiveConversationId(conversation.id);
      }

      await api.sendMessage(conversation.id, userText);

      const title =
        conversation.title === "New Conversation"
          ? deriveConversationTitle(userText)
          : conversation.title;
      if (title !== conversation.title) {
        await api.updateConversation(conversation.id, { title });
      }

      await refreshConversations(conversation.id);
      setInput("");
    } catch (submitError) {
      console.error("Chat error:", submitError);
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
