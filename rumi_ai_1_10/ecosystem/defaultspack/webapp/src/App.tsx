import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { MessageSquare } from "lucide-react";

import type { ChatItem } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { buildToolPreviewDisplayItems, hasCanvasItems } from "./components/ToolPreview";
import { api, type ChatContentBlock, type ChatMessage, type ComposerCommandItem, type ComposerCommandMode, type ComposerWidgetAction, type Conversation, type ModelProfile, type OperationsCompanyStatus, type SettingsSection, type SidebarAction, type SidebarItem, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";
import { cn } from "./lib/cn";
import { canExecuteComposerEndpointAction, isSafeLocalEndpoint } from "./lib/composerWidgets";
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
    parentId: conversation.parent_conversation_id ?? null,
    conversationKind: conversation.conversation_kind ?? "chat",
  };
}

function buildChatItems(conversations: Conversation[]): ChatItem[] {
  const byId = new Map(conversations.map((conversation) => [conversation.id, conversation]));
  const childIds = new Set<string>();

  for (const conversation of conversations) {
    if (conversation.parent_conversation_id) {
      childIds.add(conversation.id);
    }
    for (const childId of conversation.child_conversation_ids ?? []) {
      if (byId.has(childId)) childIds.add(childId);
    }
  }

  const build = (conversation: Conversation): ChatItem => {
    const linkedChildren = [
      ...new Set([
        ...(conversation.child_conversation_ids ?? []),
        ...conversations
          .filter((candidate) => candidate.parent_conversation_id === conversation.id)
          .map((candidate) => candidate.id),
      ]),
    ]
      .map((childId) => byId.get(childId))
      .filter((child): child is Conversation => Boolean(child))
      .sort((a, b) => b.updated_at - a.updated_at)
      .map(build);
    return { ...toChatItem(conversation), children: linkedChildren };
  };

  return conversations
    .filter((conversation) => !childIds.has(conversation.id))
    .map(build);
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
  const thinking = metadata.thinking as Record<string, unknown> | undefined;
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
          thinkingLabel: String(thinking?.state ?? ""),
          thinkingTranscript: String(thinking?.transcript ?? ""),
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

function optimisticAssistantMessage(conversationId: string, model: string): ChatMessage {
  return {
    id: `optimistic-assistant-${Date.now()}`,
    role: "assistant",
    content: [{ type: "text", text: "" }],
    raw_text: "",
    created_at: Date.now(),
    conversation_id: conversationId,
    parent_id: null,
    children_ids: [],
    sequence_number: 0,
    finish_reason: null,
    usage: null,
    widget: null,
    metadata: { model, thinking: { state: "streaming" }, attached_tool_count: 0 },
    events: [],
    tool_logs: [],
    model,
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

function previewLabel(preview: ToolPreviewItem | undefined): string {
  if (!preview) return "memo.md";
  const data = preview.data;
  if (data.type === "web") return data.title || data.url || "Web preview";
  if (data.type === "code") return data.filename || "Code preview";
  if (data.type === "file") return data.filename || "File preview";
  return data.alt || "Image preview";
}

function compactPreviewValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map(compactPreviewValue).filter(Boolean).join(", ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .slice(0, 6)
      .map(([key, entry]) => {
        const text = compactPreviewValue(entry);
        return text ? `${key}: ${text}` : key;
      })
      .join("\n");
  }
  return String(value);
}

function toolPreviewsFromMessages(messages: ChatMessage[]): ToolPreviewItem[] {
  return messages.flatMap((message) => (message.tool_logs ?? []).map((log, index) => {
    const toolName = String(log.tool_name ?? "tool");
    const result = log.result as Record<string, unknown> | undefined;
    const status = String(result?.status ?? "completed");
    const args = compactPreviewValue(log.arguments);
    const output = compactPreviewValue(result?.data ?? result ?? "");
    const content = [
      `tool: ${toolName}`,
      `status: ${status}`,
      args ? `input:\n${args}` : "",
      output ? `result:\n${output}` : "",
    ].filter(Boolean).join("\n\n");
    return {
      id: `message-tool-${message.id}-${index}`,
      toolStepId: toolName,
      timestamp: typeof log.timestamp === "number" ? log.timestamp : message.created_at,
      data: {
        type: "file" as const,
        filename: `${toolName}.tool`,
        size: status,
        content,
      },
    };
  })).sort((a, b) => b.timestamp - a.timestamp);
}

function CanvasPeek({
  previews,
  memo,
  activePreviewId,
  onOpen,
}: {
  previews: ToolPreviewItem[];
  memo: string;
  activePreviewId: string | null;
  onOpen: () => void;
}) {
  const items = buildToolPreviewDisplayItems(previews, memo, activePreviewId);
  if (items.length === 0) return null;

  const latest = items[0];
  const count = items.length;
  const isMemo = latest.id === "__memo__";
  const subLabel = isMemo ? "Canvas · memo" : "Canvas · tool activity";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="mx-auto mb-2 flex w-[min(620px,calc(100%_-_40px))] items-center justify-between gap-3 rounded-xl border border-zinc-800/90 bg-zinc-950/85 px-3 py-2 text-left shadow-[0_14px_38px_rgba(0,0,0,0.24)] transition-colors hover:border-zinc-700 hover:bg-zinc-900/90"
      title="Canvas を開く"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="h-8 w-8 flex-shrink-0 rounded-lg border border-zinc-800 bg-zinc-900/80" />
        <span className="min-w-0">
          <span className="block truncate text-[12px] font-medium text-zinc-300">
            {previewLabel(latest)}
          </span>
          <span className="block truncate text-[10px] text-zinc-600">{subLabel}</span>
        </span>
      </span>
      <span className="flex-shrink-0 rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-500">
        {count}
      </span>
    </button>
  );
}

function hasOperationsProfile(catalog: UICatalog | null): boolean {
  const profiles = catalog?.agent_service?.profiles ?? [];
  return profiles.some((profile) => String(profile.profile_id ?? profile.id ?? "") === "defaultspack.operations_company");
}

function isOperationsConversation(conversation: Conversation | null): boolean {
  if (!conversation) return false;
  return (
    conversation.conversation_kind === "operations_company"
    || conversation.metadata?.profile_id === "defaultspack.operations_company"
    || conversation.tags?.includes("operations-company")
  );
}

function settingList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function settingNumber(value: unknown, fallback: number): number {
  const numeric = Number(value ?? fallback);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function isAbortError(errorValue: unknown): boolean {
  return Boolean(
    errorValue
    && typeof errorValue === "object"
    && "name" in errorValue
    && String((errorValue as { name?: unknown }).name) === "AbortError",
  );
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

const LOCAL_MODEL_PROVIDER_IDS = new Set(["stub", "ollama", "lmstudio", "vllm", "llamacpp", "llama_cpp"]);
const API_KEY_PROVIDER_IDS = new Set([
  "anthropic",
  "deepseek",
  "glm",
  "google",
  "groq",
  "longcat",
  "mistral",
  "openai",
  "openai_compatible",
  "openrouter",
  "perplexity",
  "together",
  "xai",
]);

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
  if (!providerId || providerId === "rumi" || LOCAL_MODEL_PROVIDER_IDS.has(providerId)) return false;
  const availability = profile.availability ?? {};
  if (profile.local || availability.local || availability.offline || isConfiguredProfile(profile)) return false;
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
  if (profile.local || profile.availability?.local || profile.availability?.offline || LOCAL_MODEL_PROVIDER_IDS.has(providerId)) return true;
  return isConfiguredProfile(profile);
}

function modelProfileSortKey(profile: ModelProfile): [number, number, string] {
  const modelId = String(profile.model_id ?? "").trim();
  const providerId = String(profile.provider_id ?? "").trim();
  const isDefault = profile.profile_id === "stub/default";
  const isLocal = Boolean(
    profile.local
    || profile.availability?.local
    || profile.availability?.offline
    || LOCAL_MODEL_PROVIDER_IDS.has(providerId),
  );
  const isConfigured = isConfiguredProfile(profile);
  const providerOrder = isDefault ? 0 : isLocal ? 1 : isConfigured ? 2 : 9;
  const modelOrder = modelId === "default" ? 0 : 20;
  return [
    providerOrder,
    modelOrder,
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

function profileIdentity(profile: ModelProfile | null | undefined): string {
  if (!profile) return "";
  return profile.profile_id || profile.qualified_model_id || `${profile.provider_id ?? ""}/${profile.model_id ?? ""}`;
}

function profileDefaults(profile: ModelProfile | null | undefined): Record<string, unknown> {
  if (!profile) return {};
  const metadataDefaults = profile.metadata?.defaults;
  if (metadataDefaults && typeof metadataDefaults === "object" && !Array.isArray(metadataDefaults)) {
    return { ...(metadataDefaults as Record<string, unknown>), ...(profile.defaults ?? {}) };
  }
  return profile.defaults ?? {};
}

function profilePriceTier(profile: ModelProfile | null | undefined): string {
  if (!profile) return "";
  const defaults = profileDefaults(profile);
  const pricing = profile.pricing ?? (profile.metadata?.pricing as Record<string, unknown> | undefined) ?? {};
  const explicit = String(
    pricing.tier
    ?? pricing.price_tier
    ?? defaults.price
    ?? defaults.price_tier
    ?? "",
  ).toLowerCase();
  if (explicit) return explicit;
  const modelId = String(profile.model_id ?? profile.profile_id ?? "").toLowerCase();
  if (defaults.large || defaults.heavy) return "high";
  if (defaults.fast || /(?:mini|nano|lite|flash|free|small|cheap)/.test(modelId)) return "low";
  return "";
}

function profileSupportsFast(profile: ModelProfile | null | undefined): boolean {
  if (!profile) return false;
  const defaults = profileDefaults(profile);
  const tags = Array.isArray(profile.metadata?.tags) ? profile.metadata?.tags : [];
  const traits = Array.isArray(profile.metadata?.traits) ? profile.metadata?.traits : [];
  return Boolean(defaults.fast || tags.includes("fast") || traits.includes("fast_response"));
}

function profileSupportsThinking(profile: ModelProfile | null | undefined): boolean {
  return Boolean(profile?.supports_thinking && profile.thinking_levels?.length);
}

function bestConfiguredCandidate(candidates: ModelProfile[]): ModelProfile | null {
  if (candidates.length === 0) return null;
  return [...candidates].sort((a, b) => {
    const configured = Number(isConfiguredProfile(b)) - Number(isConfiguredProfile(a));
    if (configured) return configured;
    const local = Number(Boolean(b.local)) - Number(Boolean(a.local));
    if (local) return local;
    return (a.display_name || a.profile_id).localeCompare(b.display_name || b.profile_id);
  })[0] ?? null;
}

function fastCandidateForProfile(activeProfile: ModelProfile | null, profiles: ModelProfile[]): ModelProfile | null {
  if (!activeProfile) return null;
  if (profileSupportsFast(activeProfile)) return activeProfile;
  const providerId = String(activeProfile.provider_id ?? "");
  const providerDefaults = activeProfile.metadata?.default_model_for;
  const fastModel = providerDefaults && typeof providerDefaults === "object"
    ? String((providerDefaults as Record<string, unknown>).fast ?? "")
    : "";
  if (providerId && fastModel) {
    const providerFast = profiles.find((profile) => (
      profile.provider_id === providerId
      && (profile.model_id === fastModel || profile.qualified_model_id === `${providerId}/${fastModel}`)
      && profileSupportsFast(profile)
    ));
    if (providerFast) return providerFast;
  }
  const sameModelKey = String(activeProfile.same_model_across_providers_key ?? activeProfile.model_id ?? "").toLowerCase();
  const sameModelFast = profiles.filter((profile) => (
    profileIdentity(profile) !== profileIdentity(activeProfile)
    && profileSupportsFast(profile)
    && String(profile.same_model_across_providers_key ?? profile.model_id ?? "").toLowerCase() === sameModelKey
  ));
  if (sameModelFast.length) return bestConfiguredCandidate(sameModelFast);
  const providerFast = profiles.filter((profile) => (
    profile.provider_id === providerId
    && profileSupportsFast(profile)
    && String(profile.type ?? "chat").toLowerCase() === "chat"
  ));
  return bestConfiguredCandidate(providerFast);
}

function priceCandidateForProfile(activeProfile: ModelProfile | null, profiles: ModelProfile[], tier: string): ModelProfile | null {
  const normalizedTier = tier === "high" ? "high" : "low";
  if (!activeProfile) return null;
  if (profilePriceTier(activeProfile) === normalizedTier || profileDefaults(activeProfile)[`price_${normalizedTier}`]) {
    return activeProfile;
  }
  const sameModelKey = String(activeProfile.same_model_across_providers_key ?? activeProfile.model_id ?? "").toLowerCase();
  if (!sameModelKey) return null;
  const sameModelCandidates = profiles.filter((profile) => (
    profileIdentity(profile) !== profileIdentity(activeProfile)
    && String(profile.same_model_across_providers_key ?? profile.model_id ?? "").toLowerCase() === sameModelKey
    && (profilePriceTier(profile) === normalizedTier || Boolean(profileDefaults(profile)[`price_${normalizedTier}`]))
  ));
  if (sameModelCandidates.length) return bestConfiguredCandidate(sameModelCandidates);
  return null;
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
  url.pathname = "/chat";
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

function parseSlashCommandInput(input: string, commands: ComposerCommandItem[]) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return null;
  const match = trimmed.match(/^\/(\S+)(?:\s+([\s\S]*))?$/);
  if (!match) return null;
  const name = match[1].toLowerCase();
  const command = commands.find((item) => {
    const names = [item.id, item.name, ...(item.aliases ?? [])].map((value) => value.toLowerCase());
    return names.includes(name);
  });
  if (!command) return null;

  const rest = (match[2] ?? "").trim();
  const args: Record<string, unknown> = {};
  const specs = command.args ?? [];
  if (specs.length === 1 && rest) {
    args[specs[0].name] = rest;
  } else if (specs.length > 1 && rest) {
    const tokens = rest.split(/\s+/);
    specs.forEach((spec, index) => {
      if (index === specs.length - 1) {
        const remainder = tokens.slice(index).join(" ");
        if (remainder) args[spec.name] = remainder;
      } else if (tokens[index]) {
        args[spec.name] = tokens[index];
      }
    });
  }
  return { command, args, raw: trimmed };
}

function commandSearchText(command: ComposerCommandItem): string {
  return [
    command.id,
    command.name,
    ...(command.aliases ?? []),
    command.label,
    command.description ?? "",
  ].join(" ").toLowerCase();
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
  const [commandCatalog, setCommandCatalog] = useState<ComposerCommandItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useLocalStorage("rumi-input", "");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [requestedSettingsSectionId, setRequestedSettingsSectionId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useLocalStorage("rumi-show-preview", false);
  const [isHistoryMinimized, setIsHistoryMinimized] = useLocalStorage("rumi-history-minimized", false);
  const [isNewChatLaunching, setIsNewChatLaunching] = useState(false);
  const [previewMode, setPreviewMode] = useLocalStorage<ToolPreviewMode>("rumi-preview-mode", "auto");
  const [canvasMemo, setCanvasMemo] = useLocalStorage("rumi-canvas-memo", "");
  const [activePreviewId, setActivePreviewId] = useState<string | null>(null);
  const [previews, setPreviews] = useState<ToolPreviewItem[]>([]);
  const [health, setHealth] = useState<{ status: string; pack: string; ts: string } | null>(null);
  const [operationsStatus, setOperationsStatus] = useState<OperationsCompanyStatus | null>(null);
  const [operationsBusy, setOperationsBusy] = useState(false);
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
  const currentAbortControllerRef = useRef<AbortController | null>(null);

  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = buildChatItems(conversations);
  const activeModelId = activeConversation?.model ?? String(settingsValues.models?.preferred_model ?? "stub/default").trim();
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
    thinkingLevels[profileKey(activeProfile, preferredModel)]
    ?? settingsValues.models?.thinking_level
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
  const messageToolPreviews = useMemo(
    () => toolPreviewsFromMessages(activeConversation?.messages ?? []),
    [activeConversation?.messages],
  );
  const canvasPreviews = useMemo(() => {
    const seen = new Set(previews.map((preview) => preview.id));
    return [
      ...previews,
      ...messageToolPreviews.filter((preview) => !seen.has(preview.id)),
    ];
  }, [messageToolPreviews, previews]);
  const canShowCanvas = hasCanvasItems(canvasPreviews, canvasMemo);
  const effectiveShowPreview = showPreview && canShowCanvas;
  const composerCommands = useMemo(() => {
    const showAdvanced = settingsValues.commands?.show_advanced_commands === true;
    const fastCandidate = fastCandidateForProfile(activeProfile, selectableModelProfiles);
    const priceLowCandidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, "low");
    const priceHighCandidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, "high");
    return commandCatalog
      .filter((command) => command.visibility !== "hidden")
      .filter((command) => showAdvanced || command.visibility === "default")
      .filter((command) => !command.modes?.length || command.modes.includes(mode as ComposerCommandMode))
      .filter((command) => command.id !== "fast" || Boolean(fastCandidate))
      .filter((command) => command.id !== "price" || Boolean(priceLowCandidate || priceHighCandidate))
      .filter((command) => command.id !== "think" || profileSupportsThinking(activeProfile))
      .map((command) => ({
        ...command,
        active: command.id === "yolo" ? yoloMode : command.id === mode,
        enabled: command.id === "yolo" ? yoloMode : command.id === mode,
      }));
  }, [activeProfile, commandCatalog, mode, selectableModelProfiles, settingsValues.commands?.show_advanced_commands, yoloMode]);
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "hidden");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);
  const operationsProfileAvailable = hasOperationsProfile(catalog);

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
    const [catalogResult, settingsResult, profilesResult, commandsResult] = await Promise.allSettled([
      api.uiCatalog(),
      api.uiSettings(),
      api.listModelProfiles(),
      api.uiCommands(),
    ]);
    const nextCatalog = catalogResult.status === "fulfilled" ? catalogResult.value : null;
    const nextSettings = settingsResult.status === "fulfilled" ? settingsResult.value : null;
    if (nextCatalog) {
      setCatalog(nextCatalog);
    } else {
      if (catalogResult.status === "rejected") console.error(catalogResult.reason);
      setCatalog(null);
    }
    if (profilesResult.status === "fulfilled") {
      setModelProfiles(profilesResult.value.profiles);
    } else {
      console.error(profilesResult.reason);
      setModelProfiles([]);
    }
    if (nextSettings) {
      setSettingsSections(nextSettings.sections);
      setSettingsValues(nextSettings.values);
    } else {
      if (settingsResult.status === "rejected") console.error(settingsResult.reason);
    }
    if (commandsResult.status === "fulfilled") {
      setCommandCatalog(commandsResult.value.commands);
    } else {
      console.error(commandsResult.reason);
      setCommandCatalog([]);
    }
    const defaultMode = nextSettings?.values.preview?.default_mode;
    if (defaultMode === "auto" || defaultMode === "manual") {
      setPreviewMode(defaultMode);
    }
    return nextCatalog;
  }

  async function refreshOperationsStatus() {
    try {
      setOperationsStatus(await api.getOperationsCompanyStatus());
    } catch (statusError) {
      console.error(statusError);
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
        const [, nextCatalog] = await Promise.all([refreshHealth(), refreshCatalog()]);
        if (hasOperationsProfile(nextCatalog)) {
          await refreshOperationsStatus();
        }
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
    if (!operationsProfileAvailable) return;
    void refreshOperationsStatus();
  }, [operationsProfileAvailable]);

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
      }).catch((pollError) => {
        console.error(pollError);
        forgetPendingRequest(activeConversationId);
        replaceChatIdInUrl(activeConversationId, false);
        setIsGenerating(false);
        setError(pollError instanceof Error ? pollError.message : "stream 状態の確認に失敗しました。");
      });
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

  const handleStopGenerating = () => {
    currentAbortControllerRef.current?.abort();
    currentAbortControllerRef.current = null;
    if (activeConversationId) {
      forgetPendingRequest(activeConversationId);
      replaceChatIdInUrl(activeConversationId, false);
    }
    setIsGenerating(false);
    setIsNewChatLaunching(false);
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
          [fieldId]: field?.type === "secret" || field?.type === "api_keys" ? "" : value,
        },
      };
      if (field?.type === "api_keys") {
        const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
        const providerId = String(payload.provider_id ?? "").trim();
        const apiId = String(payload.api_id ?? payload.name ?? "").trim();
        const name = String(payload.name ?? apiId).trim();
        const secret = String(payload.value ?? "");
        const action = String(payload.action ?? "upsert").trim();
        if (action === "delete" && providerId && apiId) {
          void api.deleteProviderApiKey(providerId, apiId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "rename" && providerId && apiId && name) {
          void api.renameProviderApiKey(providerId, apiId, name)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (providerId && name && secret.trim()) {
          void api.saveProviderApiKey(providerId, secret, { apiId: name, name })
            .then(() => refreshCatalog())
            .catch(console.error);
        }
      } else if (field?.type === "secret") {
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

  const runFrontendCommandAction = (
    action: string | undefined,
    command: ComposerCommandItem,
    args: Record<string, unknown>,
  ) => {
    switch (action) {
      case "open_model_picker": {
        const query = String(args.query ?? "").trim().toLowerCase();
        if (query) {
          const profile = selectableModelProfiles.find((item) => commandSearchText({
            id: item.profile_id,
            name: item.profile_id,
            aliases: [item.qualified_model_id ?? "", `${item.provider_id ?? ""}/${item.model_id ?? ""}`],
            label: item.display_name,
            description: item.provider_display_name,
            category: "model",
            visibility: "default",
            risk: "low",
            execution: { type: "frontend", action: "open_model_picker" },
          }).includes(query));
          if (profile) {
            handleModelProfileSelect(profile.profile_id);
          } else {
            setError(`"${query}" に一致する model が見つかりません。`);
          }
        }
        return;
      }
      case "set_fast_mode": {
        const enabled = args.enabled === undefined ? true : Boolean(args.enabled);
        if (!enabled) {
          handleThinkingLevelChange("medium");
          return;
        }
        const candidate = fastCandidateForProfile(activeProfile, selectableModelProfiles);
        if (!candidate) {
          setError("このモデルには fast 対応モデル/プロバイダーがありません。");
          return;
        }
        if (profileIdentity(candidate) !== profileIdentity(activeProfile)) {
          handleModelProfileSelect(candidate.profile_id);
        }
        if (candidate.supports_thinking) {
          const levels = candidate.thinking_levels?.length ? candidate.thinking_levels : ["low", "medium", "high"];
          if (levels.includes("low")) handleThinkingLevelChange("low");
        }
        return;
      }
      case "set_price_mode": {
        const tier = String(args.tier ?? "low").trim().toLowerCase() === "high" ? "high" : "low";
        const candidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, tier);
        if (!candidate) {
          setError(`このモデルには price=${tier} の候補がありません。`);
          return;
        }
        if (profileIdentity(candidate) !== profileIdentity(activeProfile)) {
          handleModelProfileSelect(candidate.profile_id);
        }
        return;
      }
      case "new_conversation":
        handleNewTask();
        return;
      case "clear_composer_state":
        setInput("");
        setAttachedFiles([]);
        setDroppedWidgets([]);
        setSelectedTools([]);
        if (activeConversationId) {
          forgetPendingRequest(activeConversationId);
          replaceChatIdInUrl(activeConversationId, false);
        }
        return;
      case "set_mode_coding":
        setMode("coding");
        return;
      case "set_mode_chat":
        setMode("chat");
        return;
      case "set_mode_agent":
        setMode("agent");
        return;
      case "toggle_yolo":
        setYoloMode((value) => args.enabled === undefined ? !value : Boolean(args.enabled));
        return;
      case "open_tool_picker": {
        const query = String(args.query ?? "").trim().toLowerCase();
        if (query) {
          const item = composerExtensions.find((candidate) => (
            `${candidate.id} ${candidate.label} ${candidate.description ?? ""}`.toLowerCase().includes(query)
          ));
          if (item) {
            handleComposerExtensionSelect(item);
          } else {
            setError(`"${query}" に一致する tool が見つかりません。`);
          }
        }
        return;
      }
      case "show_status":
        setError(
          `status: mode=${mode}, model=${activeProfile?.display_name ?? preferredModel}, thinking=${selectedThinkingLevel}, yolo=${yoloMode ? "on" : "off"}, tools=${selectedTools.length}`,
        );
        return;
      case "open_settings":
      case "open_permissions":
      case "open_theme_settings":
      case "open_keymap_settings":
        if (action === "open_settings" && args.section) {
          const requested = String(args.section).trim().toLowerCase();
          const matchedSection = settingsSections.find((section) => (
            section.id.toLowerCase() === requested
            || section.label.toLowerCase() === requested
          ));
          setRequestedSettingsSectionId(matchedSection?.id ?? requested);
        } else if (action === "open_permissions") {
          setRequestedSettingsSectionId("permissions");
        } else if (action === "open_theme_settings") {
          setRequestedSettingsSectionId("theme");
        } else if (action === "open_keymap_settings") {
          setRequestedSettingsSectionId("keymap");
        }
        setIsSettingsOpen(true);
        return;
      case "open_command_help":
        setError(composerCommands.map((item) => `/${item.name}: ${item.description ?? item.label}`).join("\n"));
        return;
      case "open_diff_preview":
        setMode("coding");
        setInput("Preview the current git diff.");
        return;
      case "start_review":
        setMode("coding");
        setInput("Review the current diff and call out bugs, risks, and missing tests.");
        return;
      case "open_branch_picker":
        setMode("coding");
        if (args.name) setInput(`Create or switch to branch ${String(args.name)}.`);
        return;
      case "prepare_test_run":
        setMode("coding");
        setInput(args.target ? `Run tests for ${String(args.target)}.` : "Run the recommended tests.");
        return;
      case "prepare_lint_run":
        setMode("coding");
        setInput("Run lint and formatting checks.");
        return;
      case "open_file_search":
        setMode("coding");
        if (args.query) setInput(`Find workspace files matching ${String(args.query)}.`);
        return;
      default:
        if (command.risk === "high") {
          setError(`/${command.name} は high risk command のため approval center 経由で実行してください。`);
        }
    }
  };

  const executeComposerCommand = async (commandId: string, rawInput = `/${commandId}`) => {
    const parsed = parseSlashCommandInput(rawInput, commandCatalog) ?? {
      command: commandCatalog.find((command) => command.id === commandId || command.name === commandId),
      args: {},
      raw: rawInput,
    };
    if (!parsed.command) {
      setError(`/${commandId} は未登録の command です。`);
      return;
    }
    try {
      setError(null);
      const commandArgs = { ...parsed.args };
      if (parsed.command.id === "think" && commandArgs.level && activeProfile) {
        commandArgs.scope = "profile";
        commandArgs.profile_id = profileKey(activeProfile, preferredModel);
      }
      const result = await api.executeUiCommand({
        command: parsed.command.name ?? parsed.command.id,
        args: commandArgs,
        conversation_id: activeConversationId,
        mode: mode as ComposerCommandMode,
      });
      if (result.requires_approval) {
        setError(result.message ?? `/${parsed.command.name} は approval center 経由で実行してください。`);
        return;
      }
      if (result.action || parsed.command.execution.type === "frontend") {
        const frontendAction = parsed.command.execution.type === "frontend" ? parsed.command.execution.action : undefined;
        runFrontendCommandAction(result.action ?? frontendAction, parsed.command, parsed.args);
      }
      if (parsed.command.execution.type === "rumi_function") {
        await refreshCatalog();
      }
    } catch (commandError) {
      setError(commandError instanceof Error ? commandError.message : "command execution に失敗しました。");
    }
  };

  const handleComposerCommand = (commandId: string, rawInput?: string) => {
    void executeComposerCommand(commandId, rawInput);
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

  const operationsHeartbeatSchedule = () => (
    (operationsStatus?.schedules ?? []).find((schedule) => String(schedule.name ?? "").toLowerCase().includes("heartbeat"))
  );

  const preferredOperationsModel = () => {
    const allowlist = settingList(settingsValues.operations_company?.model_allowlist);
    const manifestAllowlist = operationsStatus?.manifest.model_self_selection?.allowlist ?? [];
    const effectiveAllowlist = allowlist.length ? allowlist : manifestAllowlist;
    if (effectiveAllowlist.includes(preferredModel)) return preferredModel;
    if (effectiveAllowlist.includes("stub/default")) return "stub/default";
    return effectiveAllowlist[0] ?? "stub/default";
  };

  const handleStartOperationsCompany = async () => {
    setOperationsBusy(true);
    setError(null);
    try {
      const status = await api.bootstrapOperationsCompany({
        start_nonstop: true,
        heartbeat_minutes: Math.max(1, Math.min(1440, settingNumber(settingsValues.operations_company?.heartbeat_minutes, 15))),
        model: preferredOperationsModel(),
      });
      setOperationsStatus(status);
      await refreshConversations(status.conversation_id ?? null);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Operations Company の起動に失敗しました。");
    } finally {
      setOperationsBusy(false);
    }
  };

  const handleOpenOperationsChat = async () => {
    if (!operationsStatus?.conversation_id) {
      await handleStartOperationsCompany();
      return;
    }
    setError(null);
    await loadConversation(operationsStatus.conversation_id);
  };

  const handleTriggerOperationsHeartbeat = async () => {
    const heartbeat = operationsHeartbeatSchedule();
    if (!heartbeat?.id) return;
    setOperationsBusy(true);
    setError(null);
    try {
      const result = await api.triggerSchedule(String(heartbeat.id));
      pushActionPreview(
        { id: "operations.heartbeat", label: "Operations Heartbeat", icon: "activity" },
        "operations-heartbeat",
        result,
      );
      await refreshOperationsStatus();
      if (operationsStatus?.conversation_id) {
        await refreshConversations(operationsStatus.conversation_id);
      }
    } catch (heartbeatError) {
      setError(heartbeatError instanceof Error ? heartbeatError.message : "Operations Company heartbeat に失敗しました。");
    } finally {
      setOperationsBusy(false);
    }
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
      } else if (action.id === "browser.profiles.list") {
        result = await api.browserComputer("browser.profiles.list", action.payload ?? {});
      } else if (action.id === "browser.profile.create") {
        result = await api.browserComputer("browser.profile.create", action.payload ?? {});
      } else if (action.id === "browser.cookies.list") {
        result = await api.browserComputer("browser.cookies.list", action.payload ?? {});
      } else if (action.id === "browser.profile.clear_cache.dry_run") {
        result = await api.browserComputer("browser.profile.clear_cache", { ...(action.payload ?? {}), dry_run: true });
      } else if (action.id === "browser.profile.clear_cookies.dry_run") {
        result = await api.browserComputer("browser.profile.clear_cookies", { ...(action.payload ?? {}), dry_run: true });
      } else if (action.id === "browser.screenshot.dry_run") {
        result = await api.browserComputer("computer.screenshot", { dry_run: true });
      } else if (action.id === "schedules.list") {
        result = await api.listSchedules();
      } else if (action.id === "channels.list") {
        result = await api.listChannels();
      } else if (action.id === "operations.status") {
        result = await api.getOperationsCompanyStatus();
        setOperationsStatus(result as OperationsCompanyStatus);
      } else if (action.id === "operations.bootstrap") {
        result = await api.bootstrapOperationsCompany({
          start_nonstop: true,
          heartbeat_minutes: Math.max(1, Math.min(1440, settingNumber(settingsValues.operations_company?.heartbeat_minutes, 15))),
          model: preferredOperationsModel(),
        });
        setOperationsStatus(result as OperationsCompanyStatus);
      } else if (action.endpoint) {
        if (!isSafeLocalEndpoint(action.endpoint) || action.requires_approval) {
          throw new Error("この action は安全な /api/ endpoint ではないか、承認が必要なため直接実行できません。");
        }
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

    const commandInput = parseSlashCommandInput(input, commandCatalog);
    if (commandInput) {
      await executeComposerCommand(commandInput.command.id, commandInput.raw);
      setInput("");
      return;
    }

    const trimmedInput = input.trim();
    const userText = (trimmedInput.startsWith("//") ? trimmedInput.slice(1) : trimmedInput) || "添付ファイルを確認してください。";
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
      const isOperationsMode = isOperationsConversation(conversation);
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
      const assistantDraft = optimisticAssistantMessage(conversation.id, preferredModel || "stub/default");
      const abortController = new AbortController();
      currentAbortControllerRef.current = abortController;
      const updateStreamingAssistant = (delta: string) => {
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          if (!existing) {
            return {
              ...current,
              messages: [
                ...current.messages,
                {
                  ...assistantDraft,
                  content: [{ type: "text", text: delta }],
                  raw_text: delta,
                },
              ],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => {
              if (message.id !== assistantDraft.id) return message;
              const nextText = `${message.raw_text ?? ""}${delta}`;
              return {
                ...message,
                content: [{ type: "text", text: nextText }],
                raw_text: nextText,
              };
            }),
          };
        });
      };
      const updateStreamingThinking = (delta: string) => {
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          const nextThinking = (message: ChatMessage) => {
            const metadata = { ...(message.metadata ?? {}) };
            const thinking = metadata.thinking as Record<string, unknown> | undefined;
            metadata.thinking = {
              ...(thinking ?? {}),
              state: "streaming",
              transcript: `${String(thinking?.transcript ?? "")}${delta}`,
            };
            return { ...message, metadata };
          };
          if (!existing) {
            return {
              ...current,
              messages: [...current.messages, nextThinking(assistantDraft)],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => message.id === assistantDraft.id ? nextThinking(message) : message),
          };
        });
      };
      const replaceStreamingAssistant = (message: ChatMessage) => {
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const hasDraft = current.messages.some((candidate) => candidate.id === assistantDraft.id);
          return {
            ...current,
            messages: hasDraft
              ? current.messages.map((candidate) => candidate.id === assistantDraft.id ? message : candidate)
              : [...current.messages, message],
          };
        });
      };

      const operationsModelAllowlist = settingList(settingsValues.operations_company?.model_allowlist);
      const operationsToolDenylist = settingList(settingsValues.operations_company?.tool_denylist);
      const operationsToolAllowlist = operationsStatus?.manifest.tool_policy?.allowlist ?? [];
      const operationsPolicy = isOperationsMode
        ? {
            profile_id: "defaultspack.operations_company",
            non_stop: true,
            allow_shell: false,
            allow_file_write: true,
            write_actions_require_approval: true,
            normal_status_silent: settingsValues.operations_company?.normal_status_silent !== false,
            max_concurrent_children: Math.max(1, Math.min(12, settingNumber(settingsValues.operations_company?.max_concurrent_children, 3))),
            ...(operationsModelAllowlist.length ? { model_allowlist: operationsModelAllowlist } : {}),
            ...(operationsToolAllowlist.length ? { tool_allowlist: operationsToolAllowlist } : {}),
            ...(operationsToolDenylist.length ? { tool_denylist: operationsToolDenylist } : {}),
          }
        : {};

      await api.streamMessage(conversation.id, userText, {
        thinking_level: activeProfile?.supports_thinking ? selectedThinkingLevel : null,
        tool_policy: {
          ...(yoloMode ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...operationsPolicy,
          ...(selectedToolIds.length ? { selected_tools: selectedToolIds } : {}),
        },
        attachments: submittedAttachments,
        tools: selectedToolIds,
        metadata: {
          mode: isOperationsMode ? "operations_company" : "chat",
          ...(isOperationsMode ? {
            profile_id: "defaultspack.operations_company",
            agent_id: "client_manager",
            conversation_strategy: "one_agent_one_conversation",
            internal_channel: "ops-company",
          } : {}),
          attachments: submittedAttachments.map(({ name, size, type, truncated, source, sourcePath }) => ({ name, size, type, truncated, source, sourcePath })),
          selected_tools: selectedToolIds,
          dropped_widgets: droppedWidgets
            .filter((widget) => widget.widgetKind === "tool_toggle" || widget.type === "tool" ? selectedToolIdSet.has(widget.sourceItemId || widget.id) : widget.enabled !== false)
            .map(({ id, type, label, widgetKind, sourceItemId }) => ({ id, type, label, widgetKind, sourceItemId })),
        },
      }, {
        onDelta: updateStreamingAssistant,
        onThinkingDelta: updateStreamingThinking,
        onMessage: replaceStreamingAssistant,
        signal: abortController.signal,
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
      if (isAbortError(submitError)) {
        if (submittedConversationId) {
          forgetPendingRequest(submittedConversationId);
          replaceChatIdInUrl(submittedConversationId, false);
          await refreshConversations(submittedConversationId).catch(console.error);
        }
        setError(null);
        return;
      }
      if (submittedConversationId && !isUnloadingRef.current && document.visibilityState !== "hidden") {
        forgetPendingRequest(submittedConversationId);
        replaceChatIdInUrl(submittedConversationId, false);
        await refreshConversations(submittedConversationId).catch(console.error);
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
      currentAbortControllerRef.current = null;
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
      onStopGenerating={handleStopGenerating}
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
          <div className="rumi-history-rail w-14 flex-shrink-0 overflow-hidden border-r border-zinc-800/60">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onRestore={() => setIsHistoryMinimized(false)}
              isCompact
            />
          </div>
        )}

        <main className="flex-1 flex min-w-0 bg-[#09090b] relative">
          <div className={cn("flex-1 flex flex-col min-w-0", effectiveShowPreview && "border-r border-zinc-800/40")}>
            {showRegion("chat_header") && (
              <Renderers.chatHeader
                title={activeChatTitle}
                showPreview={effectiveShowPreview}
                canShowPreview={showRegion("activity_preview") && canShowCanvas}
                canOpenSettings={showRegion("settings_modal")}
                onTogglePreview={() => {
                  if (canShowCanvas) setShowPreview((value) => !value);
                }}
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
                {showRegion("activity_preview") && !effectiveShowPreview && canShowCanvas && (
                  <CanvasPeek
                    previews={canvasPreviews}
                    memo={canvasMemo}
                    activePreviewId={activePreviewId}
                    onOpen={() => setShowPreview(true)}
                  />
                )}
                {browserApproval && !yoloMode && (
                  <div className="pointer-events-auto absolute bottom-full left-1/2 z-30 mb-2 w-[min(520px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-orange-500/30 bg-zinc-950 p-3 shadow-2xl">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">{browserApproval.action} の承認が必要です</p>
                        <details className="mt-1 text-[11px] text-zinc-500">
                          <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">payload を表示</summary>
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
                            {JSON.stringify(browserApproval.payload, null, 2)}
                          </pre>
                        </details>
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

          {showRegion("activity_preview") && effectiveShowPreview && (
            <Renderers.toolPreviewPanel
              previews={canvasPreviews}
              showPreview={effectiveShowPreview}
              onClose={() => setShowPreview(false)}
              previewMode={previewMode}
              onModeChange={setPreviewMode}
              activePreviewId={activePreviewId}
              memo={canvasMemo}
              onMemoChange={setCanvasMemo}
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
          activeSectionId={requestedSettingsSectionId}
          catalog={catalog}
          health={health}
          previewsCount={canvasPreviews.length}
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
