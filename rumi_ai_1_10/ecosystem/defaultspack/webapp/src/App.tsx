import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Activity, Building2, MessageSquare, PanelLeftOpen, Play, RefreshCw, ShieldCheck, Users, Zap } from "lucide-react";

import type { ChatItem } from "./components/HistoryBoard";
import type { ApprovalPreview, ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { buildToolPreviewDisplayItems, hasCanvasItems } from "./components/ToolPreview";
import { api, type ChatActivityEvent, type ChatContentBlock, type ChatMessage, type ChatStreamEvent, type ComposerWidgetAction, type Conversation, type ModelProfile, type OperationsCompanyStatus, type SettingsSection, type SidebarAction, type SidebarItem, type ToolLogEntry, type UICatalog } from "./lib/api";
import { deriveConversationTitle, formatRelativeTime, messageToText } from "./lib/chat";
import { cn } from "./lib/cn";
import { canExecuteComposerEndpointAction } from "./lib/composerWidgets";
import { extractToolVisual } from "./lib/toolVisuals";
import { hasShellRegion } from "./lib/uiShell";
import { hasWorkspaceAttachment, workspaceFileToAttachment } from "./lib/workspaceAttachments";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { AppMode, AttachedFile, ChatUiMessage, CodingContext, ComposerExtensionItem, ContextUsageInfo, DroppedWidget } from "./renderers/types";

type BrowserApproval = {
  approvalId: string;
  action: string;
  payload: Record<string, unknown>;
  token?: string;
  riskLevel?: string;
  reason?: string;
};

type ApprovalIdSet = Set<string> | null;
type ApprovalStatusById = Record<string, string>;

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
  if (data.type === "approval") return data.action || "Approval";
  return data.alt || "Image preview";
}

function previewThumbnail(preview: ToolPreviewItem | undefined): string {
  if (!preview || preview.data.type !== "image") return "";
  return preview.data.url;
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

function approvalFromToolResult(
  result: unknown,
  pendingApprovalIds: ApprovalIdSet = null,
  resolvedApprovalIds?: Set<string>,
  approvalStatuses?: ApprovalStatusById,
): ApprovalPreview | null {
  if (!result || typeof result !== "object") return null;
  const record = result as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : record;
  const widget = data.widget && typeof data.widget === "object" ? data.widget as Record<string, unknown> : data;
  if (widget.requires_approval !== true && widget.approval_required !== true) return null;
  const approvalId = String(widget.approval_id ?? "");
  if (!approvalId) return null;
  const approvalStatus = approvalStatusForWidget(widget, approvalId, approvalStatuses);
  if (approvalStatus && approvalStatus !== "pending") return null;
  if (resolvedApprovalIds?.has(approvalId)) return null;
  if (pendingApprovalIds !== null && !pendingApprovalIds.has(approvalId)) return null;
  const payload = widget.payload && typeof widget.payload === "object" ? widget.payload as Record<string, unknown> : {};
  return {
    type: "approval",
    approvalId,
    action: String(widget.action ?? "computer.action"),
    riskLevel: String(widget.risk_level ?? ""),
    reason: String(widget.risk_reason ?? widget.reason ?? ""),
    payload,
  };
}

function approvalStatusForWidget(
  widget: Record<string, unknown>,
  approvalId: string,
  approvalStatuses?: ApprovalStatusById,
): string {
  const centralStatus = approvalStatuses?.[approvalId];
  if (centralStatus) return centralStatus.toLowerCase();
  const explicit = String(widget.approval_status ?? widget.approval_state ?? "").toLowerCase();
  if (explicit) return explicit;
  const generic = String(widget.status ?? "").toLowerCase();
  if (["pending", "approved", "consumed", "denied", "rejected", "expired"].includes(generic)) return generic;
  return "pending";
}

function approvalIdsFromMessages(messages: ChatMessage[]): string[] {
  return Array.from(new Set(messages.flatMap((message) => (message.tool_logs ?? [])
    .map((log) => approvalFromToolResult(log.result)?.approvalId)
    .filter((approvalId): approvalId is string => Boolean(approvalId)))));
}

function toolLogTimestamp(logTimestamp: unknown, fallback: number): number {
  if (typeof logTimestamp === "number" && Number.isFinite(logTimestamp)) return logTimestamp;
  if (typeof logTimestamp === "string") {
    const parsed = Date.parse(logTimestamp);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function toolPreviewsFromMessages(
  messages: ChatMessage[],
  pendingApprovalIds: ApprovalIdSet = null,
  resolvedApprovalIds?: Set<string>,
  approvalStatuses?: ApprovalStatusById,
): ToolPreviewItem[] {
  return messages.flatMap((message) => (message.tool_logs ?? []).map((log, index) => {
    const toolName = String(log.tool_name ?? "tool");
    const args = log.arguments && typeof log.arguments === "object" ? log.arguments as Record<string, unknown> : {};
    const result = log.result as Record<string, unknown> | undefined;
    const status = String(result?.status ?? "completed");
    const approval = approvalFromToolResult(result, pendingApprovalIds, resolvedApprovalIds, approvalStatuses);
    if (approval) {
      return {
        id: `message-approval-${approval.approvalId}`,
        toolStepId: `${toolName}:${approval.approvalId}`,
        timestamp: toolLogTimestamp(log.timestamp, message.created_at),
        priority: 20,
        data: approval,
      };
    }
    const visual = extractToolVisual(result);
    if (visual) {
      const action = String(args.action ?? result?.action ?? "").toLowerCase();
      const isClickFeedback = action.includes("click") || visual.points.length > 0;
      return {
        id: `message-tool-${message.id}-${index}`,
        toolStepId: toolName,
        timestamp: toolLogTimestamp(log.timestamp, message.created_at),
        priority: isClickFeedback ? 10 : visual.kind === "zoom" ? 6 : 1,
        data: {
          type: "image" as const,
          url: visual.src,
          alt: isClickFeedback ? `${toolName} click feedback` : `${toolName} ${visual.kind}`,
          prompt: [
            visual.sourceLabel,
            visual.points.length ? `${visual.points.length} point${visual.points.length === 1 ? "" : "s"}` : "",
          ].filter(Boolean).join(" · "),
        },
      };
    }
    const argsPreview = compactPreviewValue(log.arguments);
    const output = compactPreviewValue(result?.data ?? result ?? "");
    const content = [
      `tool: ${toolName}`,
      `status: ${status}`,
      argsPreview ? `input:\n${argsPreview}` : "",
      output ? `result:\n${output}` : "",
    ].filter(Boolean).join("\n\n");
    return {
      id: `message-tool-${message.id}-${index}`,
      toolStepId: toolName,
      timestamp: toolLogTimestamp(log.timestamp, message.created_at),
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
  const thumbnail = previewThumbnail(latest);
  const subLabel = isMemo ? "Canvas · memo" : "Canvas · tool activity";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="mx-auto mb-2 flex w-[min(620px,calc(100%_-_40px))] items-center justify-between gap-3 rounded-xl border border-zinc-800/90 bg-zinc-950/85 px-3 py-2 text-left shadow-[0_14px_38px_rgba(0,0,0,0.24)] transition-colors hover:border-zinc-700 hover:bg-zinc-900/90"
      title="Canvas を開く"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="flex h-9 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/80">
          {thumbnail ? (
            <img src={thumbnail} alt="" className="h-full w-full object-cover" />
          ) : null}
        </span>
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

function OperationsCompanyPanel({
  status,
  isBusy,
  active,
  onStart,
  onOpenChat,
  onRefresh,
  onTriggerHeartbeat,
}: {
  status: OperationsCompanyStatus | null;
  isBusy: boolean;
  active: boolean;
  onStart: () => void;
  onOpenChat: () => void;
  onRefresh: () => void;
  onTriggerHeartbeat: () => void;
}) {
  const roleCount = status?.manifest.roles?.length ?? 7;
  const activeSchedules = (status?.schedules ?? []).filter((schedule) => schedule.status === "active").length;
  const modelCount = status?.manifest.model_self_selection?.allowlist?.length ?? 0;
  const heartbeat = (status?.schedules ?? []).find((schedule) => String(schedule.name ?? "").toLowerCase().includes("heartbeat"));
  const nextExecution = heartbeat?.next_execution_at ? Date.parse(String(heartbeat.next_execution_at)) : 0;
  const heartbeatLabel = nextExecution ? `next ${formatRelativeTime(nextExecution)}` : "not scheduled";
  const bootstrapped = status?.bootstrapped === true;

  return (
    <section className={cn(
      "border-b border-zinc-800/60 bg-zinc-950/70 px-4 py-3",
      active && "bg-emerald-950/10",
    )}>
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-[260px] flex-1 items-center gap-3">
          <span className={cn(
            "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border",
            bootstrapped ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900 text-zinc-400",
          )}>
            <Building2 size={19} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-zinc-100">Rumi Operations Company</h2>
              <span className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                bootstrapped ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900 text-zinc-500",
              )}>
                {bootstrapped ? "24/7 active" : "not started"}
              </span>
              {active && <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-300">client chat</span>}
            </div>
            <p className="mt-1 line-clamp-1 text-[11px] text-zinc-500">
              ops-company · Client Manager · PM · Coding · Research · Review · Monitor · Scheduler
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
          <span className="inline-flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/70 px-2">
            <Users size={13} /> {roleCount} roles
          </span>
          <span className="inline-flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/70 px-2">
            <Activity size={13} /> {activeSchedules} schedules
          </span>
          <span className="inline-flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/70 px-2">
            <ShieldCheck size={13} /> {modelCount} models
          </span>
          <span className="hidden h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 lg:inline-flex">
            <Zap size={13} /> {heartbeatLabel}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isBusy}
            className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            title="Refresh operations status"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            onClick={bootstrapped ? onOpenChat : onStart}
            disabled={isBusy}
            className="flex h-8 items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
            title={bootstrapped ? "Open Client Manager chat" : "Start 24/7 company agent"}
          >
            {bootstrapped ? <MessageSquare size={14} /> : <Play size={14} />}
            {bootstrapped ? "Open Chat" : "Start 24/7"}
          </button>
          {bootstrapped && (
            <button
              type="button"
              onClick={onTriggerHeartbeat}
              disabled={isBusy || !heartbeat}
              className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              title="Trigger heartbeat schedule"
            >
              <Activity size={14} /> Tick
            </button>
          )}
        </div>
      </div>
    </section>
  );
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

function pendingBrowserApproval(
  messages: ChatUiMessage[],
  pendingApprovalIds: ApprovalIdSet = null,
  resolvedApprovalIds?: Set<string>,
  approvalStatuses?: ApprovalStatusById,
): BrowserApproval | null {
  const approvalTools = new Set(["browser_computer", "browser_use", "computer_use", "zoom"]);
  for (const message of [...messages].reverse()) {
    for (const log of [...(message.toolLogs ?? [])].reverse()) {
      if (!approvalTools.has(String(log.tool_name ?? ""))) continue;
      const result = log.result as Record<string, unknown> | undefined;
      const data = (result?.data ?? result) as Record<string, unknown> | undefined;
      const widget = data?.widget as Record<string, unknown> | undefined;
      const candidate = (widget?.requires_approval ? widget : data) as Record<string, unknown> | undefined;
      if (!candidate?.requires_approval && !candidate?.approval_required) continue;
      const approvalId = String(candidate.approval_id ?? "");
      if (!approvalId) continue;
      const approvalStatus = approvalStatusForWidget(candidate, approvalId, approvalStatuses);
      if (approvalStatus && approvalStatus !== "pending") continue;
      if (resolvedApprovalIds?.has(approvalId)) continue;
      if (pendingApprovalIds !== null && !pendingApprovalIds.has(approvalId)) continue;
      const rawPayload = candidate.payload;
      const rawToken = String(candidate.approval_token ?? "");
      return {
        approvalId,
        action: String(candidate.action ?? "browser.session"),
        payload: rawPayload && typeof rawPayload === "object" ? rawPayload as Record<string, unknown> : {},
        token: rawToken && rawToken !== "[redacted]" ? rawToken : undefined,
        riskLevel: String(candidate.risk_level ?? ""),
        reason: String(candidate.risk_reason ?? candidate.reason ?? ""),
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
  const [canvasMemo, setCanvasMemo] = useLocalStorage("rumi-canvas-memo", "");
  const [activePreviewId, setActivePreviewId] = useState<string | null>(null);
  const [previews, setPreviews] = useState<ToolPreviewItem[]>([]);
  const [pendingApprovalIds, setPendingApprovalIds] = useState<Set<string> | null>(null);
  const [approvalStatuses, setApprovalStatuses] = useState<ApprovalStatusById>({});
  const [resolvedApprovalIds, setResolvedApprovalIds] = useState<Set<string>>(() => new Set());
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
  const streamingConversationIdRef = useRef<string | null>(null);

  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = buildChatItems(conversations);
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
  const approvalIdsKey = useMemo(
    () => approvalIdsFromMessages(activeConversation?.messages ?? []).join("|"),
    [activeConversation?.messages],
  );
  const browserApproval = pendingBrowserApproval(messages, pendingApprovalIds, resolvedApprovalIds, approvalStatuses);
  const messageToolPreviews = useMemo(
    () => toolPreviewsFromMessages(activeConversation?.messages ?? [], pendingApprovalIds, resolvedApprovalIds, approvalStatuses),
    [activeConversation?.messages, pendingApprovalIds, resolvedApprovalIds, approvalStatuses],
  );
  const canvasPreviews = useMemo(() => {
    const seen = new Set(messageToolPreviews.map((preview) => preview.id));
    return [
      ...messageToolPreviews,
      ...previews.filter((preview) => !seen.has(preview.id)),
    ];
  }, [messageToolPreviews, previews]);

  useEffect(() => {
    const latestToolPreview = messageToolPreviews[0];
    if (previewMode === "auto" && latestToolPreview) {
      setActivePreviewId(latestToolPreview.id);
      if (latestToolPreview.data.type === "approval" || latestToolPreview.data.type === "image") {
        setShowPreview(true);
      }
    }
  }, [messageToolPreviews, previewMode, setShowPreview]);
  const canShowCanvas = hasCanvasItems(canvasPreviews, canvasMemo);
  const effectiveShowPreview = showPreview && canShowCanvas;
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
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "hidden");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);
  const operationsProfileAvailable = hasOperationsProfile(catalog);
  const operationsConversationActive = isOperationsConversation(activeConversation);

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
      setActivePreviewId(null);
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
        await refreshOperationsStatus();
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
    const approvalIds = approvalIdsKey ? approvalIdsKey.split("|").filter(Boolean) : [];
    if (approvalIds.length === 0) {
      setPendingApprovalIds(null);
      setApprovalStatuses({});
      return;
    }
    let cancelled = false;
    void api.listApprovals().then((result) => {
      if (cancelled) return;
      const statusById: ApprovalStatusById = {};
      const pendingIds = new Set<string>();
      for (const approval of result.approvals ?? []) {
        if (!approvalIds.includes(approval.id)) continue;
        const status = String(approval.status ?? "").toLowerCase();
        statusById[approval.id] = status;
        if (status === "pending") pendingIds.add(approval.id);
      }
      for (const approvalId of approvalIds) {
        if (!statusById[approvalId]) pendingIds.add(approvalId);
      }
      setApprovalStatuses(statusById);
      setPendingApprovalIds(pendingIds);
    }).catch(() => {
      if (!cancelled) {
        setApprovalStatuses({});
        setPendingApprovalIds(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [approvalIdsKey]);

  useEffect(() => {
    if (!activeConversationId || !isConversationPending) return;
    if (streamingConversationIdRef.current === activeConversationId) return;
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

  const approveComputerApproval = async (approval: BrowserApproval | ApprovalPreview) => {
    setError(null);
    setResolvedApprovalIds((current) => new Set(current).add(approval.approvalId));
    setApprovalStatuses((current) => ({ ...current, [approval.approvalId]: "approved" }));
    setPendingApprovalIds((current) => {
      if (!current) return current;
      const next = new Set(current);
      next.delete(approval.approvalId);
      return next;
    });
    setPreviews((current) => current.filter((preview) => (
      preview.data.type !== "approval" || preview.data.approvalId !== approval.approvalId
    )));
    try {
      const decision = await api.approveApproval(approval.approvalId) as unknown as Record<string, unknown>;
      const approvalToken = String(decision.approval_token ?? "");
      const result = await api.browserComputer(approval.action, {
        ...(approval.payload ?? {}),
        approval_id: approval.approvalId,
        ...(approvalToken ? { approval_token: approvalToken } : {}),
      });
      pushActionPreview(
        { id: "browser.approval", label: "Approved Browser Action", icon: "browser" },
        approval.action,
        result,
      );
      if (activeConversationId) {
        await refreshPreview(activeConversationId);
        await loadConversation(activeConversationId, false);
      }
    } catch (approvalError) {
      setResolvedApprovalIds((current) => {
        const next = new Set(current);
        next.delete(approval.approvalId);
        return next;
      });
      setApprovalStatuses((current) => ({ ...current, [approval.approvalId]: "pending" }));
      setPendingApprovalIds((current) => {
        if (current?.has(approval.approvalId)) return current;
        const next = new Set(current ?? []);
        next.add(approval.approvalId);
        return next;
      });
      setError(approvalError instanceof Error ? approvalError.message : "browser/computer の承認に失敗しました。");
    }
  };

  const rejectComputerApproval = async (approval: BrowserApproval | ApprovalPreview) => {
    setError(null);
    setResolvedApprovalIds((current) => new Set(current).add(approval.approvalId));
    setApprovalStatuses((current) => ({ ...current, [approval.approvalId]: "denied" }));
    setPendingApprovalIds((current) => {
      if (!current) return current;
      const next = new Set(current);
      next.delete(approval.approvalId);
      return next;
    });
    setPreviews((current) => current.filter((preview) => (
      preview.data.type !== "approval" || preview.data.approvalId !== approval.approvalId
    )));
    try {
      await api.rejectApproval(approval.approvalId);
      if (activeConversationId) {
        await refreshPreview(activeConversationId);
        await loadConversation(activeConversationId, false);
      }
    } catch (approvalError) {
      setResolvedApprovalIds((current) => {
        const next = new Set(current);
        next.delete(approval.approvalId);
        return next;
      });
      setApprovalStatuses((current) => ({ ...current, [approval.approvalId]: "pending" }));
      setPendingApprovalIds((current) => {
        if (current?.has(approval.approvalId)) return current;
        const next = new Set(current ?? []);
        next.add(approval.approvalId);
        return next;
      });
      setError(approvalError instanceof Error ? approvalError.message : "browser/computer の拒否に失敗しました。");
    }
  };

  const approveBrowserAction = async () => {
    if (!browserApproval) return;
    await approveComputerApproval(browserApproval);
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
      const isOperationsMode = isOperationsConversation(conversation);
      submittedConversationId = conversation.id;
      streamingConversationIdRef.current = conversation.id;
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
      const appendAssistantEvent = (streamEvent: ChatStreamEvent) => {
        const eventType = String(streamEvent.type ?? "");
        if (!eventType || ["delta", "message", "done", "user_message", "error"].includes(eventType)) return;
        const activityEvent = streamEvent as ChatActivityEvent;
        const liveToolLog = (
          activityEvent.tool_log
          && typeof activityEvent.tool_log === "object"
          && !Array.isArray(activityEvent.tool_log)
        ) ? activityEvent.tool_log as ToolLogEntry : null;
        const appendLiveToolLog = (logs: ToolLogEntry[] | null | undefined): ToolLogEntry[] => {
          if (!liveToolLog) return logs ?? [];
          const key = String(liveToolLog.tool_call_id ?? "");
          const existing = logs ?? [];
          if (key && existing.some((log) => String(log.tool_call_id ?? "") === key)) {
            return existing.map((log) => String(log.tool_call_id ?? "") === key ? liveToolLog : log);
          }
          return [...existing, liveToolLog];
        };
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          const nextEvent = activityEvent;
          if (!existing) {
            return {
              ...current,
              messages: [
                ...current.messages,
                {
                  ...assistantDraft,
                  events: [nextEvent],
                  tool_logs: appendLiveToolLog(assistantDraft.tool_logs),
                },
              ],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => (
              message.id === assistantDraft.id
                ? { ...message, events: [...(message.events ?? []), nextEvent], tool_logs: appendLiveToolLog(message.tool_logs) }
                : message
            )),
          };
        });
        if (activityEvent.type === "status" && activityEvent.message) {
          rememberPendingRequest({
            conversationId: conversation.id,
            startedAt: Date.now(),
            status: String(activityEvent.message),
            toolNames: selectedToolLabels,
          });
        } else if (activityEvent.type === "tool_call_started" && activityEvent.tool_name) {
          const toolName = String(activityEvent.tool_name);
          rememberPendingRequest({
            conversationId: conversation.id,
            startedAt: Date.now(),
            status: `${toolName} を使用中`,
            toolNames: Array.from(new Set([...selectedToolLabels, toolName])),
          });
        } else if (activityEvent.type === "tool_call_completed" && activityEvent.tool_name) {
          const toolName = String(activityEvent.tool_name);
          rememberPendingRequest({
            conversationId: conversation.id,
            startedAt: Date.now(),
            status: `${toolName} の結果を反映中`,
            toolNames: Array.from(new Set([...selectedToolLabels, toolName])),
          });
        }
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
        onEvent: appendAssistantEvent,
        onMessage: replaceStreamingAssistant,
        onUserMessage: (message) => {
          setActiveConversation((current) => {
            if (!current || current.id !== conversation.id) return current;
            return {
              ...current,
              messages: current.messages.map((candidate) => (
                candidate.id.startsWith("optimistic-") && candidate.role === "user" ? message : candidate
              )),
            };
          });
        },
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
      if (submittedConversationId && streamingConversationIdRef.current === submittedConversationId) {
        streamingConversationIdRef.current = null;
      }
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

            {operationsProfileAvailable && operationsConversationActive && (
              <OperationsCompanyPanel
                status={operationsStatus}
                isBusy={operationsBusy}
                active={operationsConversationActive}
                onStart={handleStartOperationsCompany}
                onOpenChat={handleOpenOperationsChat}
                onRefresh={() => void refreshOperationsStatus()}
                onTriggerHeartbeat={handleTriggerOperationsHeartbeat}
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
                approvalStatuses={approvalStatuses}
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
                        <p className="mt-0.5 truncate text-[11px] text-amber-200">
                          {browserApproval.riskLevel || "risk"} · {browserApproval.reason || browserApproval.approvalId}
                        </p>
                        <details className="mt-1 text-[11px] text-zinc-500">
                          <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">payload を表示</summary>
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
                            {JSON.stringify(browserApproval.payload, null, 2)}
                          </pre>
                        </details>
                      </div>
                      <div className="flex flex-shrink-0 items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void rejectComputerApproval(browserApproval)}
                          className="h-8 rounded-lg border border-zinc-800 bg-zinc-900 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
                        >
                          拒否
                        </button>
                        <button
                          type="button"
                          onClick={approveBrowserAction}
                          className="h-8 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
                        >
                          許可
                        </button>
                      </div>
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
              onApproveApproval={(approval) => void approveComputerApproval(approval)}
              onRejectApproval={(approval) => void rejectComputerApproval(approval)}
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
