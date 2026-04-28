import { useEffect, useRef, useState, type FormEvent, type ReactElement } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Activity,
  Clock,
  FileText,
  Hash,
  Image as ImageIcon,
  Loader2,
  Mic,
  MoreHorizontal,
  Paperclip,
  PanelRightClose,
  PanelRightOpen,
  Send,
  Settings,
  Sparkles,
  Terminal,
  Globe,
  X,
  Zap,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import { TitleBar } from "./components/TitleBar";
import { HistoryBoard, type ChatItem } from "./components/HistoryBoard";
import { RightSidebar } from "./components/RightSidebar";
import { ToolPreviewPanel, type ToolPreviewItem, type ToolPreviewMode } from "./components/ToolPreview";
import { api, type ChatContentBlock, type ChatMessage, type Conversation, type SettingsSection, type SidebarItem, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: "user" | "agent";
  content: ChatContentBlock[];
  rawText: string;
  widget?: Record<string, unknown> | null;
  metadata?: {
    toolUsed?: string;
    executionTime?: string;
  };
};

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

function toUiMessage(message: ChatMessage): Message {
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

function WelcomeScreen({ onSuggestionClick }: { onSuggestionClick: (text: string) => void }) {
  const suggestions = [
    { icon: <Terminal size={15} className="text-amber-400" />, label: "コード", text: "defaultspack の拡張ポイントを整理して" },
    { icon: <Globe size={15} className="text-emerald-400" />, label: "リサーチ", text: "この会話の context に何が注入されているか教えて" },
    { icon: <FileText size={15} className="text-violet-400" />, label: "ドキュメント", text: "frontend extension manifest のテンプレートを書いて" },
    { icon: <Sparkles size={15} className="text-blue-400" />, label: "設計", text: "非中央集権な UI registry の設計をまとめて" },
  ];

  return (
    <div className="flex-1 flex items-center justify-center px-5">
      <div className="max-w-md w-full text-center">
        <div className="mb-6">
          <div className="w-9 h-9 rounded-lg bg-white text-black flex items-center justify-center mx-auto mb-3">
            <Zap size={18} className="fill-black" />
          </div>
          <h1 className="text-xl font-semibold text-zinc-100 mb-1">何を作りましょうか？</h1>
          <p className="text-xs text-zinc-500">registry から拡張される chat shell</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.label}
              onClick={() => onSuggestionClick(suggestion.text)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 hover:border-zinc-700 transition-all text-xs text-zinc-400 hover:text-zinc-200"
            >
              {suggestion.icon}
              <span>{suggestion.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageBlock({ block, unknownStrategy }: { block: ChatContentBlock; unknownStrategy: string }) {
  const blockType = String(block.type ?? "text");

  if (blockType === "text" || blockType === "markdown") {
    return <ReactMarkdown>{String(block.text ?? "")}</ReactMarkdown>;
  }

  if (blockType === "code") {
    return (
      <pre className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 overflow-x-auto text-[12px] text-zinc-200 font-mono">
        <code>{String(block.text ?? "")}</code>
      </pre>
    );
  }

  if (blockType === "image") {
    const url = String(block.url ?? "");
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-2">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <ImageIcon size={12} />
          <span>{String(block.alt ?? "image")}</span>
        </div>
        {url ? <img src={url} alt={String(block.alt ?? "image")} className="max-h-72 rounded-lg border border-zinc-800" /> : null}
      </div>
    );
  }

  if (unknownStrategy === "hidden") return null;
  if (unknownStrategy === "text") return <p>{JSON.stringify(block)}</p>;
  return (
    <pre className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 overflow-x-auto text-[11px] text-zinc-400 font-mono">
      {JSON.stringify(block, null, 2)}
    </pre>
  );
}

function WidgetCard({ widget }: { widget: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 mt-2">
      <div className="text-[10px] uppercase tracking-wider text-blue-300 mb-2">Widget</div>
      <pre className="text-[11px] text-zinc-200 overflow-x-auto font-mono">{JSON.stringify(widget, null, 2)}</pre>
    </div>
  );
}

function SettingsField({
  sectionId,
  field,
  value,
  onChange,
}: {
  sectionId: string;
  field: SettingsSection["fields"][number];
  value: unknown;
  onChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const commonLabel = <span className="text-sm text-zinc-300">{field.label}</span>;

  let control: ReactElement;
  switch (field.type) {
    case "toggle":
      control = (
        <button
          type="button"
          onClick={() => onChange(sectionId, field.id, !Boolean(value))}
          className={cn("w-10 h-6 rounded-full relative transition-colors", Boolean(value) ? "bg-emerald-500" : "bg-zinc-700")}
        >
          <span className={cn("absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform", Boolean(value) && "translate-x-4")} />
        </button>
      );
      break;
    case "select":
      control = (
        <select
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
        >
          {(field.options ?? []).map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
      );
      break;
    case "number":
      control = (
        <input
          type="number"
          value={Number(value ?? field.default ?? 0)}
          min={field.min}
          max={field.max}
          onChange={(event) => onChange(sectionId, field.id, Number(event.target.value))}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none w-28"
        />
      );
      break;
    case "readonly":
      control = <div className="text-sm text-zinc-200 font-mono">{String(value ?? field.default ?? "")}</div>;
      break;
    case "textarea":
      control = (
        <textarea
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="w-full h-24 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none resize-none"
        />
      );
      break;
    default:
      control = (
        <input
          type="text"
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none min-w-[240px]"
        />
      );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-4">
        {commonLabel}
        {control}
      </div>
      {field.help && <p className="text-[11px] text-zinc-500">{field.help}</p>}
    </div>
  );
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
      const next = {
        ...current,
        [sectionId]: {
          ...(current[sectionId] ?? {}),
          [fieldId]: value,
        },
      };
      void api.updateUiSettings(next).then((result) => setSettingsValues(result.values)).catch(console.error);
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

  return (
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-zinc-800">
      <TitleBar appName={catalog?.app?.name} appIcon={catalog?.app?.icon} />

      <div className="flex flex-1 min-h-0">
        <HistoryBoard
          activeChatId={activeConversationId}
          chatItems={chatItems}
          onChatSelect={handleHistoryClick}
          onNewTask={handleNewTask}
          onSettingsClick={() => setIsSettingsOpen(true)}
        />

        <main className="flex-1 flex min-w-0 bg-[#09090b] relative">
          <div className={cn("flex-1 flex flex-col min-w-0", showPreview && "border-r border-zinc-800/40")}>
            <header className="h-11 flex items-center px-4 border-b border-zinc-800/60 justify-between bg-[#09090b]/80 backdrop-blur-md z-10 flex-shrink-0">
              <div className="flex items-center gap-2">
                <Hash size={14} className="text-zinc-600" />
                <h2 className="text-zinc-200 font-medium text-sm truncate">{activeChatTitle}</h2>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowPreview((value) => !value)}
                  className={cn("p-1.5 rounded-md transition-colors", showPreview ? "text-zinc-200 bg-zinc-800" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800")}
                  title={showPreview ? "Hide preview" : "Show preview"}
                >
                  {showPreview ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
                </button>
                <button onClick={() => setIsSettingsOpen(true)} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors">
                  <Settings size={14} />
                </button>
                <button className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors">
                  <MoreHorizontal size={14} />
                </button>
              </div>
            </header>

            {error && <div className="mx-4 mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</div>}

            {isLoading ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 size={18} className="animate-spin text-zinc-500" />
              </div>
            ) : isNewConversation ? (
              <WelcomeScreen onSuggestionClick={(text) => setInput(text)} />
            ) : (
              <div className="flex-1 overflow-y-auto px-4 py-3">
                <div className="max-w-3xl mx-auto space-y-4">
                  {messages.map((message) => (
                    <div key={message.id} className={cn("flex gap-2.5", message.role === "user" ? "flex-row-reverse" : "")}>
                      {message.role === "agent" && (
                        <div className="flex-shrink-0 mt-1">
                          <div className="w-5 h-5 rounded bg-white text-black flex items-center justify-center">
                            <Zap size={10} className="fill-black" />
                          </div>
                        </div>
                      )}

                      <div className={cn("flex flex-col min-w-0", message.role === "user" ? "items-end max-w-[75%]" : "items-start flex-1")}>
                        {message.role === "agent" && (
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span className="text-[10px] font-medium text-zinc-500">Rumi</span>
                            {message.metadata?.executionTime && (
                              <span className="text-[9px] text-zinc-600 font-mono flex items-center gap-0.5">
                                <Clock size={8} /> {message.metadata.executionTime}
                              </span>
                            )}
                          </div>
                        )}

                        <div className={cn("rounded-lg max-w-full", message.role === "user" ? "bg-zinc-800 text-zinc-100 px-3 py-2 rounded-tr-sm text-[13px]" : "text-zinc-300")}>
                          {message.role === "agent" && showActivityInMessages && message.metadata?.toolUsed && (
                            <div className="flex items-center gap-1 text-[10px] text-zinc-500 mb-1 font-mono">
                              <Activity size={9} />
                              <span>{message.metadata.toolUsed}</span>
                            </div>
                          )}

                          <div className="markdown-body text-[13px] leading-relaxed break-words space-y-3">
                            {message.content.length > 0
                              ? message.content.map((block, index) => (
                                  <MessageBlock key={`${message.id}-${index}`} block={block} unknownStrategy={unknownBlockStrategy} />
                                ))
                              : <ReactMarkdown>{message.rawText}</ReactMarkdown>}
                          </div>

                          {showWidgets && message.widget && <WidgetCard widget={message.widget} />}
                        </div>
                      </div>
                    </div>
                  ))}

                  {isGenerating && (
                    <div className="flex gap-2.5">
                      <div className="flex-shrink-0 mt-1">
                        <div className="w-5 h-5 rounded bg-white text-black flex items-center justify-center">
                          <Zap size={10} className="fill-black" />
                        </div>
                      </div>
                      <div className="text-zinc-400 text-[13px] flex items-center gap-2">
                        <Loader2 size={12} className="animate-spin" />
                        Processing...
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} className="h-1" />
                </div>
              </div>
            )}

            <div className="p-2.5 bg-[#09090b] flex-shrink-0">
              <div className="max-w-3xl mx-auto">
                <form onSubmit={handleSubmit} className="relative flex flex-col bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden focus-within:border-zinc-700 transition-colors">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder={placeholder}
                    disabled={isGenerating}
                    className="w-full bg-transparent border-none outline-none text-zinc-100 px-3.5 py-2.5 text-[13px] resize-none min-h-[44px] max-h-[160px] placeholder:text-zinc-600 disabled:opacity-50"
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void handleSubmit(event);
                      }
                    }}
                  />
                  <div className="flex items-center justify-between px-2.5 py-1 border-t border-zinc-800/50">
                    <div className="flex items-center gap-0.5">
                      <button type="button" disabled={isGenerating} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors disabled:opacity-50">
                        <Paperclip size={14} />
                      </button>
                      <button type="button" disabled={isGenerating} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors disabled:opacity-50">
                        <Mic size={14} />
                      </button>
                    </div>
                    <button type="submit" disabled={!input.trim() || isGenerating} className="flex items-center justify-center w-7 h-7 bg-white text-black rounded-md disabled:opacity-20 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors">
                      {isGenerating ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>

          {showPreview && (
            <div className="w-[380px] flex-shrink-0 h-full">
              <ToolPreviewPanel
                previews={previews}
                isVisible={showPreview}
                onClose={() => setShowPreview(false)}
                mode={previewMode}
                onModeChange={setPreviewMode}
                activePreviewId={activePreviewId}
              />
            </div>
          )}
        </main>

        <RightSidebar
          items={sidebarItems}
          settingsValues={settingsValues}
          settingsSections={settingsSections}
          onSettingChange={handleSettingChange}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />
      </div>

      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setIsSettingsOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-4xl bg-[#09090b] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]"
            >
              <div className="px-6 py-4 border-b border-zinc-800 flex justify-between items-center">
                <div>
                  <h2 className="text-lg font-medium text-zinc-100">Settings</h2>
                  <p className="text-xs text-zinc-500 mt-1">
                    backend registry: {catalog?.extension_points.length ?? 0} extension points, {catalog?.parts?.length ?? 0} parts, {health?.pack ?? "defaultspack"}
                  </p>
                </div>
                <button onClick={() => setIsSettingsOpen(false)} className="text-zinc-500 hover:text-zinc-300">
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-8">
                {settingsSections.map((section) => (
                  <section key={section.id} className="space-y-4">
                    <div>
                      <h3 className="text-sm font-medium text-zinc-100">{section.label}</h3>
                      {section.description && <p className="text-xs text-zinc-500 mt-1">{section.description}</p>}
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-4">
                      {section.fields.map((field) => (
                        <SettingsField
                          key={`${section.id}.${field.id}`}
                          sectionId={section.id}
                          field={field}
                          value={settingsValues[section.id]?.[field.id] ?? field.default}
                          onChange={handleSettingChange}
                        />
                      ))}
                    </div>
                  </section>
                ))}

                <section className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-100">Extension Points</h3>
                    <p className="text-xs text-zinc-500 mt-1">frontend は registry と schema だけを知る構成です。</p>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    {(catalog?.extension_points ?? []).map((point) => (
                      <div key={point.id} className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-2">
                        <div className="text-sm text-zinc-200">{point.id}</div>
                        <div className="text-[11px] text-zinc-500 font-mono break-all">{point.path}</div>
                        <p className="text-[11px] text-zinc-400 leading-relaxed">{point.description}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-100">Parts</h3>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    {(catalog?.parts ?? []).map((part) => (
                      <div key={part.id} className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 space-y-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm text-zinc-200">{part.label ?? part.id}</div>
                          <div className="text-[10px] text-zinc-500 font-mono">{part.kind}</div>
                        </div>
                        <div className="text-[11px] text-zinc-500 font-mono break-all">{(part.uses ?? []).join(", ")}</div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-zinc-100">System Status</h3>
                  </div>
                  <textarea className="w-full h-32 bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-300 resize-none focus:border-zinc-600 outline-none font-mono" value={JSON.stringify({ health, previewCount: previews.length, chatRenderers: catalog?.chat_rendering.renderers ?? [], componentBindings: catalog?.component_bindings ?? [] }, null, 2)} readOnly />
                </section>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
