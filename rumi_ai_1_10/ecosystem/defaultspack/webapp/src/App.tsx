import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { PanelLeftOpen } from "lucide-react";

import type { ChatItem } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { api, type ChatContentBlock, type ChatMessage, type ComposerWidgetAction, type Conversation, type ModelProfile, type SettingsSection, type SidebarAction, type SidebarItem, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";
import { cn } from "./lib/cn";
import { canExecuteComposerEndpointAction } from "./lib/composerWidgets";
import { hasShellRegion } from "./lib/uiShell";
import { hasWorkspaceAttachment, workspaceFileToAttachment } from "./lib/workspaceAttachments";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { AppMode, AttachedFile, ChatUiMessage, CodingContext, ComposerExtensionItem, ContextUsageInfo, DroppedWidget } from "./renderers/types";

type BrowserApproval = {
  action: string;
  payload: Record<string, unknown>;
  token: string;
};

type PendingChatRequest = {
  conversationId: string;
  startedAt: number;
  status: string;
  toolNames: string[];
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

function writeJsonLocalStorage<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
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

function getNewConversationPlaceholder(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "夜更かし中ですね。今日はどうしましたか？";
  if (hour < 11) return "おはようございます。今日はどうしましたか？";
  if (hour < 17) return "今日はどうしましたか？";
  return "こんばんは。今日はどうしましたか？";
}

function getNewConversationGreeting(): string {
  return "今日は何をしましょう？";
}

function findProfile(profiles: ModelProfile[], modelId: string): ModelProfile | null {
  return profiles.find((profile) => (
    profile.profile_id === modelId
    || profile.qualified_model_id === modelId
    || `${profile.provider_id}/${profile.model_id}` === modelId
  )) ?? null;
}

const CORE_MODEL_PROVIDERS = new Set(["google", "openrouter", "stub"]);
const API_KEY_PROVIDER_IDS = new Set(["google", "openrouter"]);

function isConfiguredProfile(profile: ModelProfile): boolean {
  const availability = profile.availability ?? {};
  return Boolean(
    availability.configured
    || availability.active
    || availability.status === "configured"
    || availability.status === "active",
  );
}

export function profileNeedsApiKey(profile: ModelProfile | null | undefined): boolean {
  if (!profile) return false;
  const providerId = String(profile.provider_id ?? "").trim();
  if (!providerId || providerId === "stub" || providerId === "rumi") return false;
  const availability = profile.availability ?? {};
  if (profile.local || availability.local || isConfiguredProfile(profile)) return false;
  return API_KEY_PROVIDER_IDS.has(providerId);
}

function isUserFacingModelProfile(profile: ModelProfile, preferredModel: string): boolean {
  const providerId = String(profile.provider_id ?? "").trim();
  const modelId = String(profile.model_id ?? "").trim();
  const type = String(profile.type ?? "chat").toLowerCase();
  const profileId = profile.profile_id || profile.qualified_model_id || `${providerId}/${modelId}`;

  if (profileId === preferredModel) return true;
  if (type && type !== "chat") return false;
  if (providerId === "rumi") return false;
  if (providerId === "stub") return modelId === "default";
  if (providerId === "openrouter") return modelId === "tencent/hy3-preview:free";
  if (providerId === "google") return modelId.startsWith("gemini-") || modelId.startsWith("gemma-");
  return isConfiguredProfile(profile);
}

function modelProfileSortKey(profile: ModelProfile): [number, number, string] {
  const providerId = String(profile.provider_id ?? "").trim();
  const modelId = String(profile.model_id ?? "").trim();
  const providerOrder: Record<string, number> = {
    google: 0,
    openrouter: 1,
    openai: 2,
    anthropic: 3,
    genspark: 4,
    ollama: 7,
    lmstudio: 8,
    stub: 99,
  };
  const modelOrder: Record<string, number> = {
    "gemini-2.5-pro": 0,
    "gemini-2.5-flash": 1,
    "gemini-3-pro-preview": 2,
    "gemini-3-flash-preview": 3,
    "gemini-2.5-flash-lite": 4,
    "gemini-2.0-flash-lite": 5,
    "gemma-4-31b-it": 6,
    "gemma-4-26b-a4b-it": 7,
    "gemma-3-27b-it": 8,
    "gemma-3n-e4b-it": 9,
    "tencent/hy3-preview:free": 0,
    default: 0,
  };
  return [
    providerOrder[providerId] ?? 50,
    modelOrder[modelId] ?? 20,
    profile.display_name || profile.profile_id,
  ];
}

export function userFacingModelProfiles(profiles: ModelProfile[], preferredModel: string): ModelProfile[] {
  const deduped = new Map<string, ModelProfile>();
  for (const profile of profiles) {
    if (!isUserFacingModelProfile(profile, preferredModel)) continue;
    const key = profile.profile_id || profile.qualified_model_id || `${profile.provider_id}/${profile.model_id}`;
    if (key) deduped.set(key, profile);
  }
  return [...deduped.values()].sort((a, b) => {
    const aKey = modelProfileSortKey(a);
    const bKey = modelProfileSortKey(b);
    return aKey[0] - bKey[0] || aKey[1] - bKey[1] || aKey[2].localeCompare(bKey[2]);
  });
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
    .map((item) => ({
      id: item.id,
      label: item.label,
      category: item.category,
      description: item.description,
      tags: item.tags ?? [],
      ui: item.ui,
    }));
}

function chatIdFromLocation(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("chat") || null;
}

function isPendingInLocation(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get("pending") === "1";
}

function replaceChatIdInUrl(conversationId: string | null, pending?: boolean) {
  const url = new URL(window.location.href);
  if (conversationId) {
    url.searchParams.set("chat", conversationId);
  } else {
    url.searchParams.delete("chat");
  }
  if (pending === true) {
    url.searchParams.set("pending", "1");
  } else if (pending === false || !conversationId) {
    url.searchParams.delete("pending");
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== current) {
    window.history.pushState({ conversationId }, "", next);
  }
}

function pendingBrowserApproval(messages: ChatUiMessage[]): BrowserApproval | null {
  for (const message of [...messages].reverse()) {
    for (const log of [...(message.toolLogs ?? [])].reverse()) {
      if (log.tool_name !== "browser_computer") continue;
      const result = log.result as Record<string, unknown> | undefined;
      const data = (result?.data ?? result) as Record<string, unknown> | undefined;
      const widget = data?.widget as Record<string, unknown> | undefined;
      const candidate = (widget?.requires_approval ? widget : data) as Record<string, unknown> | undefined;
      if (!candidate?.requires_approval || !candidate.approval_token) continue;
      const rawPayload = candidate.payload;
      return {
        action: String(candidate.action ?? "browser.session"),
        payload: rawPayload && typeof rawPayload === "object" ? rawPayload as Record<string, unknown> : {},
        token: String(candidate.approval_token),
      };
    }
  }
  return null;
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
  const [isHistoryMinimized, setIsHistoryMinimized] = useLocalStorage("rumi-history-minimized", false);
  const [isNewChatLaunching, setIsNewChatLaunching] = useState(false);
  const [previewMode, setPreviewMode] = useLocalStorage<ToolPreviewMode>("rumi-preview-mode", "auto");
  const [activePreviewId, setActivePreviewId] = useState<string | null>(null);
  const [previews, setPreviews] = useState<ToolPreviewItem[]>([]);
  const [health, setHealth] = useState<{ status: string; pack: string; ts: string } | null>(null);
  const [activeSidebarItemId, setActiveSidebarItemId] = useState<string | null>(null);
  const [sidebarSelectionTick, setSidebarSelectionTick] = useState(0);
  const [yoloMode, setYoloMode] = useLocalStorage("rumi-yolo-mode", false);
  const [mode, setMode] = useLocalStorage<AppMode>("rumi-app-mode", "chat");
  const [codingContext, setCodingContext] = useState<CodingContext | null>(null);
  const [codingDirectory, setCodingDirectory] = useState(".");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [droppedWidgets, setDroppedWidgets] = useState<DroppedWidget[]>([]);
  const [selectedTools, setSelectedTools] = useState<ComposerExtensionItem[]>([]);
  const pendingStorageKey = "rumi-pending-chat-requests";
  const [pendingRequests, setPendingRequests] = useLocalStorage<Record<string, PendingChatRequest>>(pendingStorageKey, {});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isUnloadingRef = useRef(false);

  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = conversations.map(toChatItem);
  const activeModelId = activeConversation?.model ?? String(settingsValues.models?.preferred_model ?? "openrouter/tencent/hy3-preview:free").trim();
  const activeProfile = findProfile(modelProfiles, activeModelId);
  const messages = activeConversation ? activeConversation.messages.map((message) => toUiMessage(message, activeProfile)) : [];
  const activeChatTitle = activeConversation?.title ?? "New Conversation";
  const isNewConversation = activeConversation === null || activeConversation.messages.length === 0;
  const placeholder = String(settingsValues.general?.composer_placeholder ?? "メッセージを入力...");
  const preferredModel = activeModelId;
  const selectableModelProfiles = userFacingModelProfiles(modelProfiles, preferredModel);
  const favoriteProfiles = favoriteModelProfiles(settingsValues.models?.favorite_profiles, selectableModelProfiles, preferredModel);
  const thinkingLevels = (settingsValues.models?.thinking_level_by_profile ?? {}) as Record<string, unknown>;
  const selectedThinkingLevel = String(
    settingsValues.models?.thinking_level
    ?? thinkingLevels[profileKey(activeProfile, preferredModel)]
    ?? activeProfile?.default_thinking_level
    ?? "medium",
  );
  const contextUsage = contextUsageFor(activeConversation, activeProfile);
  const composerExtensions = composerExtensionItems(sidebarItems);
  const selectedToolIds = useMemo(() => selectedTools.map((tool) => tool.id), [selectedTools]);
  const selectedToolIdSet = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);
  const pendingRequest = activeConversationId ? pendingRequests[activeConversationId] : null;
  const isConversationPending = Boolean(
    pendingRequest && Date.now() - pendingRequest.startedAt < 10 * 60_000,
  );
  const browserApproval = pendingBrowserApproval(messages);
  const composerCommands = [
    {
      id: "yolo",
      label: "yolo",
      description: "このチャットの tool 承認を自動化",
      enabled: yoloMode,
    },
    {
      id: "coding",
      label: "coding",
      description: "コーディングモードに切替",
      enabled: mode === "coding",
    },
  ];
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "json");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);

  const updatePendingRequests = (updater: (current: Record<string, PendingChatRequest>) => Record<string, PendingChatRequest>) => {
    setPendingRequests((current) => {
      const next = updater(current);
      writeJsonLocalStorage(pendingStorageKey, next);
      return next;
    });
  };

  const rememberPendingRequest = (request: PendingChatRequest) => {
    updatePendingRequests((current) => ({
      ...current,
      [request.conversationId]: request,
    }));
  };

  const forgetPendingRequest = (conversationId: string) => {
    updatePendingRequests((current) => {
      const next = { ...current };
      delete next[conversationId];
      return next;
    });
  };

  const loadCodingContext = useCallback(async () => {
    try {
      const [result, branchInfo] = await Promise.all([
        api.getCodingContext({ directory: codingDirectory }),
        api.getGitBranch().catch(() => null),
      ]);
      setCodingContext({
        branch: result.branch,
        rootFolder: result.root_folder,
        directory: result.directory ?? codingDirectory,
        branches: branchInfo?.branches ?? [],
        files: result.files,
        entries: result.entries,
        git: result.git,
      });
    } catch {
      setCodingContext(null);
    }
  }, [codingDirectory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  useEffect(() => {
    const markUnloading = () => {
      isUnloadingRef.current = true;
    };
    window.addEventListener("beforeunload", markUnloading);
    window.addEventListener("pagehide", markUnloading);
    return () => {
      window.removeEventListener("beforeunload", markUnloading);
      window.removeEventListener("pagehide", markUnloading);
    };
  }, []);

  useEffect(() => {
    if (mode === "coding") {
      void loadCodingContext();
    }
  }, [mode, loadCodingContext]);

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

  async function loadConversation(conversationId: string | null, updateUrl = true) {
    if (!conversationId) {
      setActiveConversationId(null);
      setActiveConversation(null);
      await refreshPreview(null);
      if (updateUrl) replaceChatIdInUrl(null, false);
      return;
    }
    const conversation = await api.getConversation(conversationId);
    setActiveConversationId(conversationId);
    setActiveConversation(conversation);
    if (updateUrl) replaceChatIdInUrl(conversationId);
    await refreshPreview(conversationId);
  }

  async function refreshConversations(preferredId?: string | null) {
    const result = await api.listConversations();
    setConversations(result.conversations);

    const targetId = preferredId ?? activeConversationId ?? chatIdFromLocation() ?? result.conversations[0]?.id ?? null;
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
        const pendingConversationId = chatIdFromLocation();
        if (pendingConversationId && isPendingInLocation()) {
          rememberPendingRequest({
            conversationId: pendingConversationId,
            startedAt: Date.now(),
            status: "Processing...",
            toolNames: [],
          });
        }
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
    const handlePopState = () => {
      setError(null);
      void loadConversation(chatIdFromLocation(), false).catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : "会話の読み込みに失敗しました。");
      });
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshPreview(activeConversationId);
  }, [settingsValues.preview?.max_items, settingsValues.preview?.auto_open, activeConversationId]);

  useEffect(() => {
    if (!activeConversationId || !isConversationPending) return;
    setIsGenerating(true);
    const interval = window.setInterval(() => {
      void api.getConversation(activeConversationId).then((conversation) => {
        setActiveConversation(conversation);
        const latest = conversation.messages[conversation.messages.length - 1];
        if (latest && latest.role !== "user") {
          forgetPendingRequest(activeConversationId);
          replaceChatIdInUrl(activeConversationId, false);
          setIsGenerating(false);
          void refreshConversations(conversation.id);
        }
      }).catch(console.error);
    }, 1500);
    return () => window.clearInterval(interval);
  }, [activeConversationId, isConversationPending]);

  useEffect(() => {
    const staleIds = Object.entries(pendingRequests)
      .filter(([, request]) => Date.now() - request.startedAt >= 10 * 60_000)
      .map(([id]) => id);
    if (staleIds.length === 0) return;
    updatePendingRequests((current) => {
      const next = { ...current };
      for (const id of staleIds) delete next[id];
      return next;
    });
    if (activeConversationId && staleIds.includes(activeConversationId)) {
      setIsGenerating(false);
      replaceChatIdInUrl(activeConversationId, false);
    }
  }, [pendingRequests, activeConversationId]);

  const handleNewTask = () => {
    setActiveConversationId(null);
    setActiveConversation(null);
    setPreviews([]);
    setError(null);
    setIsGenerating(false);
    setAttachedFiles([]);
    setDroppedWidgets([]);
    replaceChatIdInUrl(null, false);
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

  const handleProviderApiKeySave = async (providerId: string, value: string) => {
    await api.saveProviderApiKey(providerId, value);
    await refreshCatalog();
  };

  const handleThinkingLevelChange = (level: string | null) => {
    const key = profileKey(activeProfile, preferredModel);
    updateModelSettings({
      thinking_level: level ?? "medium",
      thinking_level_by_profile: {
        ...thinkingLevels,
        [key]: level,
      },
    });
  };

  const handleComposerExtensionSelect = (item: ComposerExtensionItem) => {
    setActiveSidebarItemId(item.id);
    setSidebarSelectionTick((value) => value + 1);
    toggleSelectedTool(item);
  };

  const toggleSelectedTool = (item: ComposerExtensionItem) => {
    setSelectedTools((current) => {
      if (current.some((selected) => selected.id === item.id)) {
        return current.filter((selected) => selected.id !== item.id);
      }
      return [...current, item];
    });
  };

  const handleComposerCommand = (commandId: string) => {
    if (commandId === "yolo") {
      setYoloMode((value) => !value);
    } else if (commandId === "coding") {
      setMode((value) => (value === "coding" ? "chat" : "coding"));
    }
  };

  const handleModeChange = (newMode: AppMode) => {
    setMode(newMode);
  };

  const handleCodingBranchSwitch = (branch: string, create = false) => {
    void api.switchGitBranch(branch, create)
      .then(() => loadCodingContext())
      .catch((branchError) => setError(branchError instanceof Error ? branchError.message : "ブランチ切り替えに失敗しました。"));
  };

  const handleCodingDirectoryChange = (directory: string) => {
    setCodingDirectory(directory || ".");
  };

  const handleFileAttach = (files: AttachedFile[]) => {
    setAttachedFiles((prev) => [...prev, ...files]);
  };

  const handleAtFileAttach = (path: string) => {
    if (mode !== "coding") return;
    if (hasWorkspaceAttachment(attachedFiles, path)) return;

    void api.readWorkspaceFile(path)
      .then((result) => {
        setAttachedFiles((prev) => {
          if (hasWorkspaceAttachment(prev, path)) return prev;
          return [...prev, workspaceFileToAttachment(result.path || path, result.content, result.size)];
        });
      })
      .catch((readError) => {
        setError(readError instanceof Error ? readError.message : "workspace file の添付に失敗しました。");
      });
  };

  const handleFileRemove = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const handleDropWidget = (widget: DroppedWidget) => {
    setDroppedWidgets((prev) => {
      if (prev.some((w) => w.id === widget.id)) return prev;
      return [...prev, { ...widget, enabled: widget.enabled ?? true }];
    });
    if ((widget.widgetKind === "tool_toggle" || widget.type === "tool") && widget.enabled !== false) {
      const toolId = widget.sourceItemId || widget.id;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) {
        setSelectedTools((current) => current.some((selected) => selected.id === item.id) ? current : [...current, item]);
      }
    }
  };

  const handleWidgetToggle = (widgetId: string) => {
    const widget = droppedWidgets.find((candidate) => candidate.id === widgetId);
    if (widget?.widgetKind === "tool_toggle" || widget?.type === "tool") {
      const toolId = widget.sourceItemId || widgetId;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) {
        toggleSelectedTool(item);
        return;
      }
    }
    setDroppedWidgets((prev) => prev.map((w) => (w.id === widgetId ? { ...w, enabled: !w.enabled } : w)));
  };

  const handleComposerEndpointAction = async (widget: DroppedWidget, action: Extract<ComposerWidgetAction, { type: "call_endpoint" }>) => {
    if (!canExecuteComposerEndpointAction(action)) {
      setError("この widget action は安全な /api/ endpoint ではないか、承認が必要なため直接実行できません。");
      return;
    }

    const method = action.method ?? "GET";
    const result = await fetch(action.endpoint, {
      method,
      headers: method === "GET" ? undefined : { "Content-Type": "application/json" },
      body: method === "GET" ? undefined : JSON.stringify(action.payload ?? {}),
    }).then((response) => response.json());

    if (action.result_surface === "silent") return;
    pushActionPreview(
      { id: `composer.${widget.id}`, label: widget.label, icon: widget.icon },
      widget.label,
      result,
    );
  };

  const handleWidgetAction = (widget: DroppedWidget) => {
    const action = widget.action;

    if (!action) {
      const target = widget.sourceItemId || widget.id;
      setActiveSidebarItemId(target);
      setSidebarSelectionTick((value) => value + 1);
      return;
    }

    if (action.type === "open_panel") {
      const target = action.target_item_id || widget.sourceItemId || widget.id;
      setActiveSidebarItemId(target);
      setSidebarSelectionTick((value) => value + 1);
      return;
    }

    if (action.type === "toggle_tool") {
      const toolId = action.tool_id || widget.sourceItemId || widget.id;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) toggleSelectedTool(item);
      return;
    }

    if (action.type === "select_model") {
      if (action.profile_id) handleModelProfileSelect(action.profile_id);
      return;
    }

    if (action.type === "call_endpoint") {
      setError(null);
      void handleComposerEndpointAction(widget, action).catch((actionError) => {
        setError(actionError instanceof Error ? actionError.message : "composer widget action に失敗しました。");
      });
    }
  };

  const approveBrowserAction = async () => {
    if (!browserApproval) return;
    setError(null);
    try {
      const result = await api.browserComputer(browserApproval.action, {
        ...browserApproval.payload,
        approval_token: browserApproval.token,
      });
      pushActionPreview(
        { id: "browser.approval", label: "Approved Browser Action", icon: "browser" },
        "browser-approval",
        result,
      );
      if (activeConversationId) {
        await refreshPreview(activeConversationId);
      }
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "browser/computer の承認に失敗しました。");
    }
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
    if ((!input.trim() && attachedFiles.length === 0) || isGenerating) return;

    const userText = input.trim() || "添付ファイルを確認してください。";
    const submittedAttachments = attachedFiles;
    const wasNewConversation = isNewConversation;
    setIsGenerating(true);
    setError(null);
    if (wasNewConversation) {
      setIsNewChatLaunching(true);
    }
    setInput("");
    setAttachedFiles([]);
    let submittedConversationId: string | null = null;
    const selectedToolLabels = [
      ...selectedTools.map((item) => item.label || item.id),
    ];

    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await api.createConversation({
          model: preferredModel || "stub/default",
        });
        setActiveConversationId(conversation.id);
      }
      submittedConversationId = conversation.id;
      rememberPendingRequest({
        conversationId: conversation.id,
        startedAt: Date.now(),
        status: `${activeProfile?.display_name ?? preferredModel} が思考中`,
        toolNames: selectedToolLabels,
      });
      replaceChatIdInUrl(conversation.id, true);

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
        tool_policy: {
          ...(yoloMode ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...(selectedToolIds.length ? { selected_tools: selectedToolIds } : {}),
        },
        attachments: submittedAttachments,
        tools: selectedToolIds,
        metadata: {
          mode: "chat",
          attachments: submittedAttachments.map(({ name, size, type, truncated, source, sourcePath }) => ({ name, size, type, truncated, source, sourcePath })),
          selected_tools: selectedToolIds,
          dropped_widgets: droppedWidgets
            .filter((widget) => widget.widgetKind === "tool_toggle" || widget.type === "tool" ? selectedToolIdSet.has(widget.sourceItemId || widget.id) : widget.enabled !== false)
            .map(({ id, type, label, widgetKind, sourceItemId }) => ({ id, type, label, widgetKind, sourceItemId })),
        },
      });
      setAttachedFiles([]);
      setSelectedTools([]);
      setDroppedWidgets([]);
      forgetPendingRequest(conversation.id);
      replaceChatIdInUrl(conversation.id, false);

      if (title !== conversation.title) {
        await api.updateConversation(conversation.id, { title });
      }

      await refreshConversations(conversation.id);
    } catch (submitError) {
      console.error("Chat error:", submitError);
      if (submittedConversationId && !isUnloadingRef.current && document.visibilityState !== "hidden") {
        forgetPendingRequest(submittedConversationId);
      }
      setInput(userText);
      setAttachedFiles(submittedAttachments);
      setError(
        submitError instanceof Error
          ? submitError.message
          : "メッセージ送信に失敗しました。",
      );
      setIsNewChatLaunching(false);
    } finally {
      setIsGenerating(false);
      setIsNewChatLaunching(false);
    }
  };

  const Renderers = useMemo(() => resolveDefaultspackRenderers(catalog), [catalog]);
  const renderComposer = (isCentered = false) => (
    <Renderers.composer
      input={input}
      placeholder={isCentered ? getNewConversationPlaceholder() : placeholder}
      isNewConversation={isCentered}
      isGenerating={isGenerating || isConversationPending}
      selectedProfile={activeProfile}
      favoriteProfiles={favoriteProfiles}
      modelProfiles={selectableModelProfiles}
      thinkingLevel={activeProfile?.supports_thinking ? selectedThinkingLevel : null}
      contextUsage={contextUsage}
      inlineExtensions={composerExtensions}
      belowExtensions={[]}
      commands={composerCommands}
      yoloMode={yoloMode}
      mode={mode}
      codingContext={codingContext}
      attachedFiles={attachedFiles}
      droppedWidgets={droppedWidgets}
      selectedToolIds={selectedToolIds}
      onExtensionSelect={handleComposerExtensionSelect}
      onCommandSelect={handleComposerCommand}
      onModelProfileSelect={handleModelProfileSelect}
      onProviderApiKeySave={handleProviderApiKeySave}
      onThinkingLevelChange={handleThinkingLevelChange}
      onInputChange={setInput}
      onSubmit={handleSubmit}
      onModeChange={handleModeChange}
      onFileAttach={handleFileAttach}
      onAtFileAttach={handleAtFileAttach}
      onFileRemove={handleFileRemove}
      onDropWidget={handleDropWidget}
      onWidgetAction={handleWidgetAction}
      onWidgetToggle={handleWidgetToggle}
      onCodingBranchSwitch={handleCodingBranchSwitch}
      onCodingDirectoryChange={handleCodingDirectoryChange}
      onCodingContextRefresh={loadCodingContext}
    />
  );

  return (
    <RendererBoundary>
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-zinc-800">
      {showRegion("title_bar") && <Renderers.titleBar appName={catalog?.app?.name} appIcon={catalog?.app?.icon} />}

      <div className="flex flex-1 min-h-0">
        {showRegion("history") && !isHistoryMinimized && (
          <div className="w-[360px] max-w-[36vw] min-w-[300px] flex-shrink-0 overflow-hidden border-r border-zinc-800/60 max-[900px]:w-[300px]">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onMinimize={() => setIsHistoryMinimized(true)}
            />
          </div>
        )}

        {showRegion("history") && isHistoryMinimized && (
          <div className="rumi-history-rail flex w-12 flex-shrink-0 flex-col items-center border-r border-zinc-800/60 bg-[#09090b] py-2">
            <button
              type="button"
              onClick={() => setIsHistoryMinimized(false)}
              className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
              title="チャット欄を開く"
            >
              <PanelLeftOpen size={17} />
            </button>
          </div>
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

            {isNewConversation && !isLoading ? (
              <div className={cn("rumi-new-chat-stage flex flex-1 items-center justify-center px-5 pb-[10vh]", isNewChatLaunching && "is-launching")}>
                <div className="w-full">
                  <h1 className="rumi-greeting mx-auto mb-7 max-w-[720px] px-4 text-center text-[clamp(24px,3.2vw,44px)] font-medium leading-tight text-zinc-200">
                    {getNewConversationGreeting()}
                  </h1>
                  {renderComposer(true)}
                </div>
              </div>
            ) : (
              <Renderers.chatMessages
                error={error}
                isMessagesRegionVisible={showRegion("chat_messages")}
                isLoading={isLoading}
                isNewConversation={isNewConversation}
                isGenerating={isGenerating || isConversationPending}
                pendingStatus={pendingRequest?.status ?? null}
                pendingToolNames={pendingRequest?.toolNames ?? []}
                messages={messages}
                messagesEndRef={messagesEndRef}
                unknownBlockStrategy={unknownBlockStrategy}
                showActivityInMessages={showActivityInMessages}
                showWidgets={showWidgets}
                onSuggestionClick={(text) => setInput(text)}
              />
            )}

            {showRegion("composer") && !isNewConversation && (
              <div className="relative">
                {browserApproval && !yoloMode && (
                  <div className="pointer-events-auto absolute bottom-full left-1/2 z-30 mb-2 w-[min(520px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-orange-500/30 bg-zinc-950 p-3 shadow-2xl">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">{browserApproval.action} の承認が必要です</p>
                        <p className="truncate text-[11px] text-zinc-500">{JSON.stringify(browserApproval.payload)}</p>
                      </div>
                      <button
                        type="button"
                        onClick={approveBrowserAction}
                        className="h-8 flex-shrink-0 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
                      >
                        許可
                      </button>
                    </div>
                  </div>
                )}
              {renderComposer(false)}
              </div>
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
            activeItemId={activeSidebarItemId ? `${activeSidebarItemId}:${sidebarSelectionTick}` : null}
            settingsValues={settingsValues}
            settingsSections={settingsSections}
            selectedToolIds={selectedToolIds}
            onSettingChange={handleSettingChange}
            onOpenSettings={() => setIsSettingsOpen(true)}
            onToolToggle={(item) => toggleSelectedTool({
              id: item.id,
              label: item.label,
              category: item.category,
              description: item.description,
              tags: item.tags ?? [],
              ui: item.ui,
            })}
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
