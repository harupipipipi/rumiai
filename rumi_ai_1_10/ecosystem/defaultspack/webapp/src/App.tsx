import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { CompanyWorkspacePanel } from "./components/company/CompanyWorkspacePanel";
import { CodingCockpit } from "./components/coding/CodingCockpit";
import { ConversationSpotlight } from "./components/ConversationSpotlight";
import { WarmActionIcon } from "./components/WarmActionIcon";
import type { ChatItem } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { buildToolPreviewDisplayItems, hasCanvasItems } from "./components/ToolPreview";
import { api, defaultspackApiFetch, type ChatActivityEvent, type ChatContentBlock, type ChatMessage, type ChatStreamEvent, type ChatToolStreamEvent, type CodingWorkspaceRecord, type ComposerCommandExecuteResult, type ComposerCommandItem, type ComposerCommandMode, type ComposerWidgetAction, type Conversation, type ConversationSearchResult, type ConversationSteerItem, type ModelCommandCandidate, type ModelProfile, type OperationsCompanyStatus, type SettingsSection, type SidebarAction, type SidebarItem, type UICatalog } from "./lib/api";
import { reduceBrowserStateFromEvents } from "./lib/browserState";
import { deriveConversationTitle, formatRelativeTime, messageToText, orderConversationMessages } from "./lib/chat";
import { cn } from "./lib/cn";
import { canExecuteComposerEndpointAction, isSafeLocalEndpoint } from "./lib/composerWidgets";
import { conversationMatchesSpotlightFilter, conversationToSearchResult, type SpotlightFilter } from "./lib/conversationSpotlight";
import { boundedDurationLabel } from "./lib/duration";
import { normalizeLocale } from "./lib/i18n";
import { PENDING_CHAT_REQUEST_TTL_MS, shouldClearPendingAfterConversationRefresh, type PendingChatRequest } from "./lib/pendingChat";
import { isRecord, toolPreviewsFromMessages, upsertStreamActivityEvent } from "./lib/toolPreviews";
import { hasShellRegion } from "./lib/uiShell";
import { hasWorkspaceAttachment, workspaceFileToAttachment } from "./lib/workspaceAttachments";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { AppMode, AttachedFile, ChatUiMessage, CodingContext, ComposerExtensionItem, ContextUsageInfo, DroppedWidget } from "./renderers/types";

type BrowserApproval = {
  action: string;
  payload: Record<string, unknown>;
  token: string;
  toolName: string;
};

type ComposerCandidateMenuState = {
  mode: "model";
  query: string;
  candidates: ModelCommandCandidate[];
} | null;

type WorkspacePanelMode = "composer" | "calendar";

type CalendarMemo = {
  id?: string;
  title?: string;
  content?: string;
  updated_at?: string;
  folder_slug?: string;
};

type CalendarTask = {
  id?: string;
  name?: string;
  description?: string;
  status?: string;
  schedule_type?: string;
  schedule_config?: Record<string, unknown>;
  task?: Record<string, unknown>;
  task_config?: Record<string, unknown>;
  next_run_at?: string | null;
};

function recordArray(value: unknown, keys: string[]): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.filter((item): item is Record<string, unknown> => isRecord(item));
  if (!isRecord(value)) return [];
  for (const key of keys) {
    const child = value[key];
    if (Array.isArray(child)) return child.filter((item): item is Record<string, unknown> => isRecord(item));
  }
  const data = value.data;
  if (isRecord(data)) {
    for (const key of keys) {
      const child = data[key];
      if (Array.isArray(child)) return child.filter((item): item is Record<string, unknown> => isRecord(item));
    }
  }
  return [];
}

function CalendarComposerPanel({
  onClose,
  onResult,
}: {
  onClose: () => void;
  onResult: (label: string, result: unknown) => void;
}) {
  const [memos, setMemos] = useState<CalendarMemo[]>([]);
  const [tasks, setTasks] = useState<CalendarTask[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const refreshCalendar = useCallback(async () => {
    setBusy(true);
    setStatus(null);
    try {
      const [scheduleResult, memoResult] = await Promise.allSettled([
        api.listSchedules(),
        api.invokeTool("memo_list_notes", { folder_id: "calendar", limit: 12 }),
      ]);
      if (scheduleResult.status === "fulfilled") {
        setTasks(recordArray(scheduleResult.value, ["schedules", "items", "tasks"]) as CalendarTask[]);
      }
      if (memoResult.status === "fulfilled") {
        setMemos(recordArray(memoResult.value, ["notes", "results", "items"]) as CalendarMemo[]);
      }
      const failed = [scheduleResult, memoResult].filter((item) => item.status === "rejected").length;
      setStatus(failed ? `${failed}件のカレンダー情報を読めませんでした` : null);
    } catch (calendarError) {
      setStatus(calendarError instanceof Error ? calendarError.message : "Calendar refresh failed");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refreshCalendar();
  }, [refreshCalendar]);

  const createRecurringTask = async () => {
    const message = prompt.trim();
    if (!message) return;
    setBusy(true);
    setStatus(null);
    try {
      const result = await api.createSchedule({
        name: message.slice(0, 48),
        description: "Created from Rumi calendar composer",
        schedule_type: "interval",
        schedule_config: { interval: { value: 1, unit: "days" } },
        task: { message, model: "default", timeout: 300 },
      });
      onResult("calendar-schedule-create", result);
      setPrompt("");
      await refreshCalendar();
    } catch (createError) {
      setStatus(createError instanceof Error ? createError.message : "Task creation failed");
    } finally {
      setBusy(false);
    }
  };

  const triggerTask = async (taskId: string) => {
    const result = await api.triggerSchedule(taskId);
    onResult("calendar-schedule-trigger", result);
    await refreshCalendar();
  };

  const pauseOrResumeTask = async (task: CalendarTask) => {
    const taskId = String(task.id ?? "");
    if (!taskId) return;
    const paused = String(task.status ?? "").toLowerCase() === "paused";
    const result = paused ? await api.resumeSchedule(taskId) : await api.pauseSchedule(taskId);
    onResult(paused ? "calendar-schedule-resume" : "calendar-schedule-pause", result);
    await refreshCalendar();
  };

  return (
    <section className="mx-auto mb-4 w-[min(920px,calc(100vw-32px))] rounded-[28px] border border-amber-200/12 bg-gradient-to-br from-[#17130f]/96 via-[#10100f]/96 to-[#0b0b0c]/96 p-4 shadow-[0_24px_80px_rgba(0,0,0,0.42)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <WarmActionIcon kind="calendar" size="lg" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-zinc-100">AI Calendar</h2>
            <p className="truncate text-xs text-zinc-500">AIカレンダーメモと定期タスクを入力欄の代わりに確認します。</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void refreshCalendar()} className="rounded-xl border border-zinc-800 px-3 py-2 text-xs text-zinc-300 hover:border-amber-200/20 hover:bg-zinc-900" disabled={busy}>
            Refresh
          </button>
          <button type="button" onClick={onClose} className="rounded-xl border border-zinc-800 px-3 py-2 text-xs text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900">
            Composer
          </button>
        </div>
      </div>

      {status && <div className="mb-3 rounded-xl border border-orange-400/20 bg-orange-300/10 px-3 py-2 text-xs text-orange-100">{status}</div>}

      <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
        <div className="rounded-2xl border border-zinc-800/80 bg-black/20 p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-200">Calendar memos</h3>
            <span className="text-[10px] text-zinc-600">{memos.length} notes</span>
          </div>
          <div className="space-y-2">
            {memos.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-6 text-center text-xs text-zinc-600">calendarフォルダのメモはまだありません。</p>
            ) : memos.map((memo) => (
              <article key={String(memo.id ?? memo.title)} className="rounded-xl border border-zinc-800 bg-zinc-950/55 px-3 py-2">
                <div className="truncate text-xs font-medium text-zinc-200">{String(memo.title ?? "Untitled memo")}</div>
                <p className="mt-1 line-clamp-3 text-[11px] leading-5 text-zinc-500">{String(memo.content ?? "")}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-black/20 p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-200">Recurring tasks</h3>
            <span className="text-[10px] text-zinc-600">{tasks.length} tasks</span>
          </div>
          <div className="space-y-2">
            {tasks.length === 0 ? (
              <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-6 text-center text-xs text-zinc-600">定期タスクはまだありません。</p>
            ) : tasks.map((task) => {
              const taskId = String(task.id ?? "");
              const paused = String(task.status ?? "").toLowerCase() === "paused";
              return (
                <article key={taskId || String(task.name)} className="rounded-xl border border-zinc-800 bg-zinc-950/55 px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-zinc-200">{String(task.name ?? taskId ?? "Scheduled task")}</div>
                      <p className="mt-1 text-[10px] text-zinc-600">{String(task.schedule_type ?? "schedule")} · {String(task.status ?? "active")}</p>
                    </div>
                    {taskId && (
                      <div className="flex shrink-0 gap-1">
                        <button type="button" onClick={() => void triggerTask(taskId)} className="rounded-lg border border-zinc-800 px-2 py-1 text-[10px] text-zinc-300 hover:border-amber-200/20">Run</button>
                        <button type="button" onClick={() => void pauseOrResumeTask(task)} className="rounded-lg border border-zinc-800 px-2 py-1 text-[10px] text-zinc-300 hover:border-amber-200/20">{paused ? "Resume" : "Pause"}</button>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl border border-zinc-800/80 bg-zinc-950/45 p-3">
        <label className="mb-2 block text-xs font-medium text-zinc-300" htmlFor="calendar-task-prompt">定期タスクを追加</label>
        <div className="flex gap-2">
          <input
            id="calendar-task-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="例: 毎朝、昨日の作業を要約して今日のTODOを作って"
            className="min-w-0 flex-1 rounded-xl border border-zinc-800 bg-black/35 px-3 py-2 text-sm text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-amber-200/30"
          />
          <button type="button" onClick={() => void createRecurringTask()} disabled={busy || !prompt.trim()} className="rounded-xl bg-gradient-to-br from-amber-100 to-orange-300 px-4 py-2 text-xs font-semibold text-zinc-950 disabled:opacity-50">
            Add daily
          </button>
        </div>
      </div>
    </section>
  );
}

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

function externalConversationSection(conversation: Conversation): { id: string; title: string } | null {
  const metadata = conversation.metadata ?? {};
  const provider = typeof metadata.external_provider === "string" ? metadata.external_provider.trim().toLowerCase() : "";
  if (!provider) return null;
  if (provider === "line") {
    return { id: "integration-line", title: "LINE" };
  }
  return {
    id: `integration-${provider}`,
    title: provider.slice(0, 1).toUpperCase() + provider.slice(1),
  };
}

function toChatItem(conversation: Conversation): ChatItem {
  const section = externalConversationSection(conversation);
  const metadata = conversation.metadata ?? {};
  return {
    id: conversation.id,
    title: conversation.title,
    date: formatBoardDate(conversation.updated_at),
    type: "chat",
    parentId: conversation.parent_conversation_id ?? null,
    conversationKind: conversation.conversation_kind ?? "chat",
    sectionId: section?.id ?? null,
    sectionTitle: section?.title ?? null,
    tags: conversation.tags ?? [],
    isStarred: conversation.is_starred,
    isPinned: Boolean(conversation.is_pinned),
    companyId: typeof metadata.company_id === "string" ? metadata.company_id : null,
    workspaceId: typeof metadata.workspace_id === "string" ? metadata.workspace_id : null,
    metadata,
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
  const timing = metadata.timing as Record<string, unknown> | undefined;
  const attachedToolCount = Number(metadata.attached_tool_count ?? 0);
  const thinkingDuration = String(timing?.thinking_duration_label ?? "")
    || boundedDurationLabel(timing?.thinking_started_at, timing?.completed_at);
  return {
    id: message.id,
    conversationId: message.conversation_id,
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
          thinkingDuration,
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

function isCancelledStreamError(errorValue: unknown): boolean {
  if (isAbortError(errorValue)) return true;
  const message = errorValue instanceof Error ? errorValue.message : String(errorValue ?? "");
  return message.trim().toLowerCase() === "cancelled";
}

function isActivityStreamEvent(event: ChatStreamEvent): event is ChatToolStreamEvent {
  return (
    event.type === "status"
    || event.type === "tool_call"
    || event.type === "tool_call_started"
    || event.type === "tool_call_delta"
    || event.type === "tool_call_completed"
    || event.type === "tool_result"
    || event.type === "browser_state_invalidated"
    || event.type === "browser_state_snapshot"
    || event.type === "browser_dom_snapshot"
    || event.type === "browser_screenshot"
    || event.type === "approval_requested"
    || event.type === "ai_retry_scheduled"
    || event.type === "task_failed"
  );
}

function isConversationSteerItem(value: unknown): value is ConversationSteerItem {
  return Boolean(
    value
    && typeof value === "object"
    && "id" in value
    && "prompt" in value
  );
}

function activeComposerSteerItems(items: ConversationSteerItem[], isRunning: boolean): ConversationSteerItem[] {
  return items
    .filter((item) => item.visible !== false && String(item.prompt ?? "").trim())
    .filter((item) => {
      const status = String(item.status || "").toLowerCase();
      return status === "queued" || status === "sending" || (isRunning && status === "injected");
    })
    .slice(-3)
    .reverse();
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
  if (profile.cost_tier) return String(profile.cost_tier);
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
  if (profile.supports_fast || profile.speed_tier === "fast") return true;
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
  url.pathname = window.location.pathname === "/coding" ? "/coding" : "/chat";
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

export function parseCommandBoolean(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return fallback;
    if (["false", "0", "off", "no", "n", "disable", "disabled"].includes(normalized)) return false;
    if (["true", "1", "on", "yes", "y", "enable", "enabled"].includes(normalized)) return true;
  }
  return Boolean(value);
}

export function frontendCommandArgs(
  parsedArgs: Record<string, unknown>,
  backendArgs: unknown,
): Record<string, unknown> {
  return isRecord(backendArgs) ? { ...backendArgs } : parsedArgs;
}

export function keepSelectedToolsAfterSend(settingsValues: Record<string, Record<string, unknown>>): boolean {
  return parseCommandBoolean(settingsValues.tools?.keep_selected_tools_after_send, false);
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

function isModelCommand(command: ComposerCommandItem | undefined): boolean {
  if (!command) return false;
  return [command.id, command.name, ...(command.aliases ?? [])]
    .map((value) => String(value ?? "").toLowerCase())
    .includes("model");
}

function modelCandidateProfileId(candidate: ModelCommandCandidate): string {
  return String(candidate.profile_id ?? candidate.qualified_model_id ?? "").trim();
}

function selectedModelProfileId(value: ComposerCommandExecuteResult["selected_model"]): string {
  if (typeof value === "string") return value.trim();
  if (value && typeof value === "object") return modelCandidateProfileId(value);
  return "";
}

function modelCommandInputQuery(value: string): string | null {
  const match = value.trim().match(/^\/models?(?:\s+([\s\S]*))?$/i);
  if (!match) return null;
  return String(match[1] ?? "").trim();
}

function pendingBrowserApproval(messages: ChatUiMessage[]): BrowserApproval | null {
  const approvalFromCandidate = (candidate: Record<string, unknown> | undefined, fallbackToolName = "browser_computer"): BrowserApproval | null => {
    if (!candidate?.requires_approval && !candidate?.approval_required) return null;
    if (!candidate.approval_token) return null;
    const rawPayload = candidate.payload;
    const toolName = String(candidate.tool_name ?? fallbackToolName);
    return {
      action: String(candidate.action ?? "browser.session"),
      payload: rawPayload && typeof rawPayload === "object" ? rawPayload as Record<string, unknown> : {},
      token: String(candidate.approval_token),
      toolName,
    };
  };

  for (const message of [...messages].reverse()) {
    if (message.role === "user") return null;
    if (message.role !== "agent") continue;
    for (const event of [...(message.events ?? [])].reverse()) {
      if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
      const approval = approvalFromCandidate(event as Record<string, unknown>, String(event.tool_name ?? "browser_computer"));
      if (approval) return approval;
    }
    for (const log of [...(message.toolLogs ?? [])].reverse()) {
      if (!["browser_computer", "browser_companion", "browser_use", "computer_use"].includes(String(log.tool_name))) continue;
      const result = log.result as Record<string, unknown> | undefined;
      const data = (result?.data ?? result) as Record<string, unknown> | undefined;
      const widget = data?.widget as Record<string, unknown> | undefined;
      const candidate = (widget?.requires_approval || widget?.approval_required ? widget : data) as Record<string, unknown> | undefined;
      const approval = approvalFromCandidate(candidate, String(log.tool_name));
      if (approval) return approval;
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
  const [composerCandidateMenu, setComposerCandidateMenu] = useState<ComposerCandidateMenuState>(null);
  const [isSpotlightOpen, setIsSpotlightOpen] = useState(false);
  const [spotlightQuery, setSpotlightQuery] = useState("");
  const [spotlightFilter, setSpotlightFilter] = useState<SpotlightFilter>("all");
  const [spotlightResults, setSpotlightResults] = useState<ConversationSearchResult[]>([]);
  const [spotlightSelectedIndex, setSpotlightSelectedIndex] = useState(0);
  const [spotlightLoading, setSpotlightLoading] = useState(false);
  const [modelPickerRequestId, setModelPickerRequestId] = useState(0);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [requestedSettingsSectionId, setRequestedSettingsSectionId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useLocalStorage("rumi-show-preview", false);
  const [workspacePanelMode, setWorkspacePanelMode] = useState<WorkspacePanelMode>("composer");
  const [isHistoryMinimized, setIsHistoryMinimized] = useLocalStorage("rumi-history-minimized", false);
  const [isNewChatLaunching, setIsNewChatLaunching] = useState(false);
  const [modelSteerStatus, setModelSteerStatus] = useState<string | null>(null);
  const [modelSteerBusy, setModelSteerBusy] = useState(false);
  const [steerItems, setSteerItems] = useState<ConversationSteerItem[]>([]);
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
  const [codingWorkspaces, setCodingWorkspaces] = useState<CodingWorkspaceRecord[]>([]);
  const [selectedCodingWorkspaceId, setSelectedCodingWorkspaceId] = useState<string | null>(null);
  const [codingDirectory, setCodingDirectory] = useState(".");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [droppedWidgets, setDroppedWidgets] = useState<DroppedWidget[]>([]);
  const [storedSelectedToolIds, setStoredSelectedToolIds] = useLocalStorage<string[]>("rumi-selected-tool-ids", []);
  const pendingStorageKey = "rumi-pending-chat-requests";
  const [pendingRequests, setPendingRequests] = useLocalStorage<Record<string, PendingChatRequest>>(pendingStorageKey, {});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isUnloadingRef = useRef(false);
  const currentAbortControllerRef = useRef<AbortController | null>(null);
  const streamingConversationIdRef = useRef<string | null>(null);

  const sidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = buildChatItems(conversations);
  const recentSpotlightResults = useMemo(
    () => conversations
      .filter((conversation) => conversationMatchesSpotlightFilter(conversation, spotlightFilter))
      .slice(0, 10)
      .map(conversationToSearchResult),
    [conversations, spotlightFilter],
  );
  const visibleSpotlightResults = spotlightQuery.trim() ? spotlightResults : recentSpotlightResults;
  const activeModelId = activeConversation?.model ?? String(settingsValues.models?.preferred_model ?? "stub/default").trim();
  const activeProfile = findProfile(modelProfiles, activeModelId);
  const orderedMessages = useMemo(
    () => activeConversation ? orderConversationMessages(activeConversation.messages) : [],
    [activeConversation?.messages],
  );
  const messages = orderedMessages.map((message) => toUiMessage(message, activeProfile));
  const activeChatTitle = activeConversation?.title ?? "New Conversation";
  const isNewConversation = activeConversation === null || activeConversation.messages.length === 0;
  const placeholder = String(settingsValues.general?.composer_placeholder ?? "メッセージを入力...");
  const locale = normalizeLocale(settingsValues.general?.language);
  const keyboardButtonNavigation = parseCommandBoolean(settingsValues.general?.keyboard_button_navigation, false);
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
  const selectedTools = useMemo(() => storedSelectedToolIds
    .map((toolId) => composerExtensions.find((tool) => tool.id === toolId))
    .filter((tool): tool is ComposerExtensionItem => Boolean(tool)), [composerExtensions, storedSelectedToolIds]);
  const selectedToolIds = useMemo(() => selectedTools.map((tool) => tool.id), [selectedTools]);
  const selectedToolIdSet = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);
  const pendingRequest = activeConversationId ? pendingRequests[activeConversationId] : null;
  const isConversationPending = Boolean(
    pendingRequest && Date.now() - pendingRequest.startedAt < PENDING_CHAT_REQUEST_TTL_MS,
  );
  const browserApproval = pendingBrowserApproval(messages);
  const messageToolPreviews = useMemo(
    () => toolPreviewsFromMessages(activeConversation?.messages ?? []),
    [activeConversation?.messages],
  );
  const liveBrowserState = useMemo(
    () => reduceBrowserStateFromEvents((activeConversation?.messages ?? []).flatMap((message) => message.events ?? [])),
    [activeConversation?.messages],
  );
  const canvasPreviews = useMemo(() => {
    const seen = new Set(previews.map((preview) => preview.id));
    return [
      ...previews,
      ...messageToolPreviews.filter((preview) => !seen.has(preview.id)),
    ].sort((a, b) => b.timestamp - a.timestamp);
  }, [messageToolPreviews, previews]);
  const canShowCanvas = hasCanvasItems(canvasPreviews, canvasMemo) || liveBrowserState.state_revision >= 0;
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
  const modelCommandCandidates = composerCandidateMenu?.mode === "model" ? composerCandidateMenu.candidates : [];
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "hidden");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);
  const isActivityPreviewVisible = showRegion("activity_preview") && effectiveShowPreview;
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

  const loadCodingWorkspaces = useCallback(async () => {
    try {
      const result = await api.listCodingWorkspaces();
      setCodingWorkspaces(result.workspaces);
      setSelectedCodingWorkspaceId((current) => current ?? result.selected_workspace_id ?? result.workspaces[0]?.workspace_id ?? null);
      return result;
    } catch {
      setCodingWorkspaces([]);
      return { workspaces: [], selected_workspace_id: null };
    }
  }, []);

  const loadCodingContext = useCallback(async () => {
    const workspaceId = selectedCodingWorkspaceId;
    try {
      const [result, branchInfo] = await Promise.all([
        api.getCodingContext({ directory: codingDirectory, workspace_id: workspaceId }),
        api.getGitBranch({ workspace_id: workspaceId }).catch(() => null),
      ]);
      setCodingContext({
        branch: result.branch,
        rootFolder: result.root_folder,
        workspaceId: result.workspace_id ?? workspaceId,
        directory: result.directory ?? codingDirectory,
        branches: branchInfo?.branches ?? [],
        files: result.files,
        entries: result.entries,
        git: result.git,
      });
    } catch {
      setCodingContext(null);
    }
  }, [codingDirectory, selectedCodingWorkspaceId]);

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
    const handleOauthMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const payload = event.data;
      if (!payload || typeof payload !== "object") return;
      if ((payload as Record<string, unknown>).type !== "rumi_provider_oauth") return;
      const providerId = String((payload as Record<string, unknown>).provider_id ?? "").trim();
      if (providerId) {
        void refreshProviderOAuthStatus(providerId).catch(console.error);
        return;
      }
      void refreshCatalog().catch(console.error);
    };
    window.addEventListener("message", handleOauthMessage);
    return () => {
      window.removeEventListener("message", handleOauthMessage);
    };
  }, []);

  useEffect(() => {
    if (mode === "coding") {
      void loadCodingWorkspaces().then(() => loadCodingContext());
    }
  }, [mode, loadCodingContext, loadCodingWorkspaces]);

  useEffect(() => {
    if (window.location.pathname !== "/coding") return;
    setMode("coding");
  }, [setMode]);

  async function refreshHealth() {
    try {
      setHealth(await api.health());
    } catch (healthError) {
      console.error(healthError);
    }
  }

  function mergeProviderOAuthStatus(providerId: string, oauthStatus: Record<string, unknown>) {
    setSettingsValues((current) => {
      const apiSection = current.apis;
      const apiKeys = apiSection?.api_keys;
      if (!Array.isArray(apiKeys)) return current;

      let updated = false;
      const nextApiKeys = apiKeys.map((entry) => {
        if (!entry || typeof entry !== "object") return entry;
        const provider = entry as Record<string, unknown>;
        if (String(provider.provider_id ?? "").trim() !== providerId) return provider;

        updated = true;
        const existingOauth = provider.oauth && typeof provider.oauth === "object" && !Array.isArray(provider.oauth)
          ? provider.oauth as Record<string, unknown>
          : {};
        return {
          ...provider,
          oauth: {
            ...existingOauth,
            ...oauthStatus,
          },
        };
      });

      if (!updated) return current;
      return {
        ...current,
        apis: {
          ...(apiSection ?? {}),
          api_keys: nextApiKeys,
        },
      };
    });
  }

  async function refreshProviderOAuthStatus(providerId: string) {
    const result = await api.providerOAuthStatus(providerId);
    if (result.provider && typeof result.provider === "object" && !Array.isArray(result.provider)) {
      mergeProviderOAuthStatus(providerId, result.provider as Record<string, unknown>);
    }
    void refreshCatalog().catch(console.error);
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
            recoveredFromLocation: true,
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
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey && event.key.toLowerCase() === "k")) return;
      event.preventDefault();
      setIsSpotlightOpen(true);
      setSpotlightSelectedIndex(0);
    };
    document.addEventListener("keydown", handleGlobalKeyDown);
    return () => document.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  useEffect(() => {
    if (!isSpotlightOpen) return;
    const query = spotlightQuery.trim();
    if (!query) {
      setSpotlightResults([]);
      setSpotlightLoading(false);
      return;
    }
    let cancelled = false;
    setSpotlightLoading(true);
    const timeout = window.setTimeout(() => {
      void api.searchConversations(query, {
        date_filter: spotlightFilter === "starred" ? "all" : spotlightFilter,
        is_starred: spotlightFilter === "starred" ? true : undefined,
        role: "all",
        limit: 12,
      }).then((result) => {
        if (cancelled) return;
        setSpotlightResults(result.results);
      }).catch((searchError) => {
        if (cancelled) return;
        console.error(searchError);
        setSpotlightResults([]);
      }).finally(() => {
        if (!cancelled) setSpotlightLoading(false);
      });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [isSpotlightOpen, spotlightFilter, spotlightQuery]);

  useEffect(() => {
    setSpotlightSelectedIndex(0);
  }, [spotlightFilter, spotlightQuery, spotlightResults.length]);

  useEffect(() => {
    if (!activeConversationId || !isConversationPending) return;
    if (streamingConversationIdRef.current === activeConversationId) return;
    setIsGenerating(true);
    const interval = window.setInterval(() => {
      void api.getConversation(activeConversationId).then((conversation) => {
        setActiveConversation(conversation);
        const latest = conversation.messages[conversation.messages.length - 1];
        if (shouldClearPendingAfterConversationRefresh(latest, pendingRequest, Date.now())) {
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
  }, [activeConversationId, isConversationPending, pendingRequest]);

  useEffect(() => {
    const staleIds = Object.entries(pendingRequests)
      .filter(([, request]) => Date.now() - request.startedAt >= PENDING_CHAT_REQUEST_TTL_MS)
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
    const conversationId = activeConversationId;
    if (conversationId) {
      void api.stopMessage(conversationId).catch(console.error);
    }
    currentAbortControllerRef.current?.abort();
    currentAbortControllerRef.current = null;
    if (conversationId) {
      forgetPendingRequest(conversationId);
      replaceChatIdInUrl(conversationId, false);
    }
    setIsGenerating(false);
    setIsNewChatLaunching(false);
  };

  const handleHistoryClick = (conversationId: string) => {
    setError(null);
    void loadConversation(conversationId);
  };

  const handleHistoryMetadataChange = (conversationId: string, updates: { is_pinned?: boolean; is_starred?: boolean; tags?: string[] }) => {
    setError(null);
    void api.updateConversation(conversationId, updates as Partial<Conversation>)
      .then((conversation) => {
        setConversations((current) => current.map((item) => item.id === conversation.id ? { ...conversation, messages: [] } : item));
        if (activeConversationId === conversation.id) setActiveConversation(conversation);
      })
      .catch((updateError) => setError(updateError instanceof Error ? updateError.message : "会話メタデータの更新に失敗しました。"));
  };

  const closeSpotlight = () => {
    setIsSpotlightOpen(false);
    setSpotlightQuery("");
    setSpotlightResults([]);
    setSpotlightSelectedIndex(0);
  };

  const openSpotlightResult = (result: ConversationSearchResult | undefined) => {
    if (!result?.conversation_id) return;
    closeSpotlight();
    setError(null);
    void loadConversation(result.conversation_id);
  };

  const handleSpotlightKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSpotlight();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSpotlightSelectedIndex((index) => Math.min(index + 1, Math.max(visibleSpotlightResults.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSpotlightSelectedIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      openSpotlightResult(visibleSpotlightResults[spotlightSelectedIndex] ?? visibleSpotlightResults[0]);
    }
  };

  const handleSettingChange = (sectionId: string, fieldId: string, value: unknown) => {
    setSettingsValues((current) => {
      const section = settingsSections.find((item) => item.id === sectionId);
      const field = section?.fields.find((item) => item.id === fieldId);
      const sectionPatch = {
        ...(current[sectionId] ?? {}),
        [fieldId]: field?.type === "secret" || field?.type === "api_keys" || field?.type === "external_tokens" ? "" : value,
      };
      if (sectionId === "external_input" && fieldId === "input_provider") {
        const provider = String(value ?? "line");
        const templateByProvider: Record<string, { template: string; profile: string; endpoint: string; route: string }> = {
          line: { template: "line.input.default", profile: "line.default", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          discord: { template: "discord.input.default", profile: "discord.default", endpoint: "discord-main", route: "/api/integrations/discord/interactions" },
          slack: { template: "slack.input.default", profile: "slack.default", endpoint: "slack-main", route: "/api/integrations/slack/events" },
          generic: { template: "generic.input.default", profile: "generic.webhook.default", endpoint: "generic-main", route: "/api/webhooks/inbound/{webhook_id}" },
        };
        const mapped = templateByProvider[provider] ?? templateByProvider.line;
        sectionPatch.input_template_id = mapped.template;
        sectionPatch.input_profile_id = mapped.profile;
        sectionPatch.input_endpoint_id = mapped.endpoint;
        sectionPatch.public_url_launcher = {
          ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
          route_path: mapped.route,
        };
      } else if (sectionId === "external_input" && fieldId === "input_template_id") {
        const templateId = String(value ?? "");
        const inputByTemplate: Record<string, { provider: string; profile: string; endpoint: string; route: string }> = {
          "line.input.default": { provider: "line", profile: "line.default", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          "line.input.computer_use": { provider: "line", profile: "line.computer_use", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          "discord.input.default": { provider: "discord", profile: "discord.default", endpoint: "discord-main", route: "/api/integrations/discord/interactions" },
          "slack.input.default": { provider: "slack", profile: "slack.default", endpoint: "slack-main", route: "/api/integrations/slack/events" },
          "generic.input.default": { provider: "generic", profile: "generic.webhook.default", endpoint: "generic-main", route: "/api/webhooks/inbound/{webhook_id}" },
        };
        const mapped = inputByTemplate[templateId];
        const provider = mapped?.provider ?? (templateId.split(".")[0] || "line");
        const routeByProvider: Record<string, string> = {
          line: "/api/integrations/line/webhook",
          discord: "/api/integrations/discord/interactions",
          slack: "/api/integrations/slack/events",
          generic: "/api/webhooks/inbound/{webhook_id}",
        };
        sectionPatch.input_provider = provider;
        sectionPatch.input_profile_id = mapped?.profile ?? (provider === "discord" ? "discord.default" : provider === "slack" ? "slack.default" : provider === "generic" ? "generic.webhook.default" : "line.default");
        sectionPatch.input_endpoint_id = mapped?.endpoint ?? `${provider}-main`;
        sectionPatch.public_url_launcher = {
          ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
          route_path: mapped?.route ?? routeByProvider[provider] ?? routeByProvider.line,
        };
      } else if (sectionId === "external_input" && fieldId === "input_response_preset") {
        const preset = String(value ?? "");
        if (preset === "computer_use_line_biz") {
          sectionPatch.input_provider = "line";
          sectionPatch.input_template_id = "line.input.computer_use";
          sectionPatch.input_profile_id = "line.computer_use";
          sectionPatch.input_endpoint_id = "line-main";
          sectionPatch.public_url_launcher = {
            ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
            route_path: "/api/integrations/line/webhook",
          };
        }
      } else if (sectionId === "external_output" && fieldId === "output_provider") {
        const provider = String(value ?? "line");
        const templateByProvider: Record<string, { template: string; profile: string; mode: string }> = {
          line: { template: "line.output.default", profile: "line.default", mode: "reply_to_origin" },
          discord: { template: "discord.output.bot_channel", profile: "discord.bot_channel", mode: "discord_bot_channel" },
          slack: { template: "slack.output.default", profile: "slack.default", mode: "slack_channel" },
          generic: { template: "generic.output.webhook", profile: "generic.webhook", mode: "generic_webhook" },
          web: { template: "generic.output.webhook", profile: "generic.webhook", mode: "web_local" },
        };
        const mapped = templateByProvider[provider] ?? templateByProvider.line;
        sectionPatch.output_template_id = mapped.template;
        sectionPatch.output_profile_id = mapped.profile;
        sectionPatch.output_send_mode = mapped.mode;
      } else if (sectionId === "external_output" && fieldId === "output_template_id") {
        const templateId = String(value ?? "");
        const outputByTemplate: Record<string, { provider: string; profile: string; mode: string }> = {
          "line.output.default": { provider: "line", profile: "line.default", mode: "reply_to_origin" },
          "discord.output.bot_channel": { provider: "discord", profile: "discord.bot_channel", mode: "discord_bot_channel" },
          "discord.output.webhook": { provider: "discord", profile: "discord.webhook", mode: "discord_webhook_url" },
          "slack.output.default": { provider: "slack", profile: "slack.default", mode: "slack_channel" },
          "generic.output.webhook": { provider: "generic", profile: "generic.webhook", mode: "generic_webhook" },
        };
        const mapped = outputByTemplate[templateId];
        if (mapped) {
          sectionPatch.output_provider = mapped.provider;
          sectionPatch.output_profile_id = mapped.profile;
          sectionPatch.output_send_mode = mapped.mode;
        }
      }
      const next = {
        ...current,
        [sectionId]: sectionPatch,
      };
      if (field?.type === "api_keys") {
        const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
        const providerId = String(payload.provider_id ?? "").trim();
        const apiId = String(payload.api_id ?? payload.name ?? "").trim();
        const name = String(payload.name ?? apiId).trim();
        const secret = String(payload.value ?? "");
        const action = String(payload.action ?? "upsert").trim();
        if (action === "oauth_refresh") {
          if (providerId) {
            void refreshProviderOAuthStatus(providerId).catch(console.error);
          } else {
            void refreshCatalog().catch(console.error);
          }
          return current;
        } else if (action === "delete" && providerId && apiId) {
          void api.deleteProviderApiKey(providerId, apiId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "rename" && providerId && apiId && name) {
          void api.renameProviderApiKey(providerId, apiId, name)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (providerId && name && secret.trim()) {
          void api.saveProviderApiKey(providerId, secret, {
            apiId: name,
            name,
            baseUrl: String(payload.base_url ?? "").trim() || undefined,
            allowedModels: Array.isArray(payload.allowed_models)
              ? payload.allowed_models.map((item) => String(item ?? "").trim()).filter(Boolean)
              : undefined,
            defaultModel: String(payload.default_model ?? "").trim() || undefined,
            quotaLabel: String(payload.quota_label ?? "").trim() || undefined,
            notes: String(payload.notes ?? "").trim() || undefined,
          })
            .then(() => refreshCatalog())
            .catch(console.error);
        }
      } else if (field?.type === "external_tokens") {
        const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
        const providerId = String(payload.provider_id ?? "").trim();
        const tokenId = String(payload.token_id ?? payload.name ?? "").trim();
        const name = String(payload.name ?? tokenId).trim();
        const kind = String(payload.kind ?? "token").trim();
        const secret = String(payload.value ?? "");
        const action = String(payload.action ?? "upsert").trim();
        if (action === "delete" && providerId && tokenId) {
          void api.deleteExternalToken(providerId, tokenId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "rename" && providerId && tokenId && name) {
          void api.renameExternalToken(providerId, tokenId, name)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (providerId && name && secret.trim()) {
          void api.saveExternalToken(providerId, secret, { tokenId: name, name, kind })
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

  const refreshSteerQueue = useCallback(async (conversationIdOverride?: string) => {
    const conversationId = conversationIdOverride ?? activeConversationId;
    if (!conversationId) {
      setSteerItems([]);
      return;
    }
    setModelSteerBusy(true);
    try {
      const result = await api.conversationSteer({
        action: "list",
        conversation_id: conversationId,
      });
      const items = "items" in result && Array.isArray(result.items) ? result.items : [];
      setSteerItems(items);
      const queuedCount = items.filter((item) => item.status === "queued").length;
      setModelSteerStatus(queuedCount ? `${queuedCount}件のステアが待機中` : null);
    } catch (steerError) {
      setModelSteerStatus(steerError instanceof Error ? steerError.message : "Steer refresh failed");
    } finally {
      setModelSteerBusy(false);
    }
  }, [activeConversationId]);

  const queueConversationSteer = useCallback(async (promptOverride?: string) => {
    const prompt = String(promptOverride ?? input).trim();
    if (!activeConversationId || !prompt) return;
    setModelSteerBusy(true);
    try {
      await api.conversationSteer({
        action: "enqueue",
        prompt,
        target_type: "conversation",
        target_id: activeConversationId,
        conversation_id: activeConversationId,
        visible: true,
        auto_send: true,
        metadata: {
          source: "composer_steer",
          live: isGenerating || isConversationPending,
        },
      });
      setInput("");
      setModelSteerStatus(isGenerating || isConversationPending ? "ステアを送りました" : "ステアを予約しました");
      await refreshSteerQueue();
    } catch (steerError) {
      setModelSteerStatus(steerError instanceof Error ? steerError.message : "Steer queue failed");
    } finally {
      setModelSteerBusy(false);
    }
  }, [activeConversationId, input, isConversationPending, isGenerating, refreshSteerQueue, setInput]);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshSteerQueue();
  }, [activeConversationId, refreshSteerQueue]);

  const handleComposerExtensionSelect = (item: ComposerExtensionItem) => {
    setActiveSidebarItemId(item.id);
    setSidebarSelectionTick((value) => value + 1);
    toggleSelectedTool(item);
  };

  const toggleSelectedTool = (item: ComposerExtensionItem) => {
    setStoredSelectedToolIds((current) => {
      if (current.includes(item.id)) {
        return current.filter((selectedId) => selectedId !== item.id);
      }
      return [...current, item.id];
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
        setComposerCandidateMenu(null);
        if (!query) {
          setModelPickerRequestId((value) => value + 1);
          return;
        }
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
        const enabled = parseCommandBoolean(args.enabled, true);
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
        if (activeConversationId) {
          forgetPendingRequest(activeConversationId);
          replaceChatIdInUrl(activeConversationId, false);
        }
        return;
      case "set_mode_coding":
        handleModeChange("coding");
        return;
      case "set_mode_chat":
        handleModeChange("chat");
        return;
      case "set_mode_agent":
        handleModeChange("agent");
        return;
      case "toggle_yolo":
        setYoloMode((value) => parseCommandBoolean(args.enabled, !value));
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
        handleModeChange("coding");
        setInput("Preview the current git diff.");
        return;
      case "start_review":
        handleModeChange("coding");
        setInput("Review the current diff and call out bugs, risks, and missing tests.");
        return;
      case "open_branch_picker":
        handleModeChange("coding");
        if (args.name) setInput(`Create or switch to branch ${String(args.name)}.`);
        return;
      case "prepare_test_run":
        handleModeChange("coding");
        setInput(args.target ? `Run tests for ${String(args.target)}.` : "Run the recommended tests.");
        return;
      case "prepare_lint_run":
        handleModeChange("coding");
        setInput("Run lint and formatting checks.");
        return;
      case "open_file_search":
        handleModeChange("coding");
        if (args.query) setInput(`Find workspace files matching ${String(args.query)}.`);
        return;
      default:
        if (command.risk === "high") {
          setError(`/${command.name} は high risk command のため approval center 経由で実行してください。`);
        }
    }
  };

  const executeComposerCommand = async (commandId: string, rawInput = `/${commandId}`): Promise<boolean | void> => {
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
      if (isModelCommand(parsed.command)) {
        if (result.action === "show_model_candidates") {
          setComposerCandidateMenu({
            mode: "model",
            query: String(result.args?.query ?? commandArgs.query ?? "").trim(),
            candidates: Array.isArray(result.candidates) ? result.candidates : [],
          });
          if (result.message) setError(result.message);
          return false;
        }
        if (result.action === "open_model_picker") {
          setComposerCandidateMenu(null);
          setModelPickerRequestId((value) => value + 1);
          if (result.message) setError(result.message);
          return true;
        }
        if (result.executed) {
          const selectedProfileId = selectedModelProfileId(result.selected_model);
          setComposerCandidateMenu(null);
          setInput("");
          if (result.message) setError(result.message);
          await refreshCatalog();
          if (activeConversationId && selectedProfileId) {
            const conversation = await api.updateConversation(activeConversationId, { model: selectedProfileId });
            setActiveConversation(conversation);
            await refreshConversations(conversation.id);
          } else if (activeConversationId) {
            await refreshConversations(activeConversationId);
          }
          return true;
        }
      }

      if (result.action || parsed.command.execution.type === "frontend") {
        const frontendAction = parsed.command.execution.type === "frontend" ? parsed.command.execution.action : undefined;
        runFrontendCommandAction(result.action ?? frontendAction, parsed.command, frontendCommandArgs(parsed.args, result.args));
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

  const handleModelCommandCandidateSelect = (candidate: ModelCommandCandidate) => {
    const profileId = modelCandidateProfileId(candidate);
    if (!profileId) {
      setError("Selected model candidate is missing a profile id.");
      return;
    }
    void executeComposerCommand("model", `/model ${profileId}`);
  };

  const handleComposerInputChange = (value: string) => {
    setInput(value);
    if (isGenerating || isConversationPending) {
      setComposerCandidateMenu(null);
      return;
    }
    const modelQuery = modelCommandInputQuery(value);
    if (composerCandidateMenu && modelQuery !== composerCandidateMenu.query) {
      setComposerCandidateMenu(null);
    }
  };

  const handleModeChange = (newMode: AppMode) => {
    setMode(newMode);
    if (newMode === "coding" && window.location.pathname !== "/coding") {
      const url = new URL(window.location.href);
      url.pathname = "/coding";
      window.history.pushState({ mode: "coding", conversationId: activeConversationId }, "", `${url.pathname}${url.search}${url.hash}`);
    } else if (newMode !== "coding" && window.location.pathname === "/coding") {
      const url = new URL(window.location.href);
      url.pathname = "/chat";
      if (activeConversationId) url.searchParams.set("chat", activeConversationId);
      else url.searchParams.delete("chat");
      url.searchParams.delete("pending");
      window.history.pushState({ mode: newMode, conversationId: activeConversationId }, "", `${url.pathname}${url.search}${url.hash}`);
    }
  };

  const handleCodingBranchSwitch = (branch: string, create = false) => {
    void api.switchGitBranch(branch, create, { workspace_id: selectedCodingWorkspaceId })
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

    void api.readWorkspaceFile(path, { workspace_id: selectedCodingWorkspaceId })
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

  const handleCodingWorkspaceSelect = (workspaceId: string) => {
    handleModeChange("coding");
    setSelectedCodingWorkspaceId(workspaceId);
    void api.selectCodingWorkspace(workspaceId)
      .then(() => loadCodingWorkspaces())
      .then(() => loadCodingContext())
      .catch((workspaceError) => setError(workspaceError instanceof Error ? workspaceError.message : "workspace selection failed."));
  };

  const handleCodingWorkspaceTrust = (workspaceId: string) => {
    void api.trustCodingWorkspace(workspaceId)
      .then(() => loadCodingWorkspaces())
      .then(() => loadCodingContext())
      .catch((workspaceError) => setError(workspaceError instanceof Error ? workspaceError.message : "workspace trust failed."));
  };

  const handleCodingWorkspaceCreate = () => {
    const rootPath = codingContext?.rootFolder;
    if (!rootPath) {
      setError("Current coding context has no workspace root to add.");
      return;
    }
    void api.createCodingWorkspace({ root_path: rootPath, trusted: false })
      .then((result) => api.selectCodingWorkspace(result.workspace.workspace_id))
      .then((result) => {
        setSelectedCodingWorkspaceId(result.selected_workspace_id);
        return loadCodingWorkspaces();
      })
      .then(() => loadCodingContext())
      .catch((workspaceError) => setError(workspaceError instanceof Error ? workspaceError.message : "workspace creation failed."));
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
        setStoredSelectedToolIds((current) => current.includes(item.id) ? current : [...current, item.id]);
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

  const handleToolBatchSet = (toolIds: string[], enabled: boolean) => {
    const validIds = new Set(composerExtensions.map((tool) => tool.id));
    const requestedIds = [...new Set(toolIds.filter((toolId) => validIds.has(toolId)))];
    if (requestedIds.length === 0) return;
    setStoredSelectedToolIds((current) => {
      if (enabled) return [...new Set([...current, ...requestedIds])];
      const requestedIdSet = new Set(requestedIds);
      return current.filter((toolId) => !requestedIdSet.has(toolId));
    });
  };

  const handleComposerEndpointAction = async (widget: DroppedWidget, action: Extract<ComposerWidgetAction, { type: "call_endpoint" }>) => {
    if (!canExecuteComposerEndpointAction(action)) {
      setError("この widget action は安全な /api/ endpoint ではないか、承認が必要なため直接実行できません。");
      return;
    }

    const method = (action.method ?? "GET").toUpperCase();
    const result = await defaultspackApiFetch(action.endpoint, {
      method,
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
    if (!activeConversationId) return;
    setError(null);
    setIsGenerating(true);
    const approvalToolIds = selectedToolIds.length
      ? selectedToolIds
      : [browserApproval.toolName].filter(Boolean);
    rememberPendingRequest({
      conversationId: activeConversationId,
      startedAt: Date.now(),
      status: "ユーザー承認をAIへ伝えています",
      toolNames: approvalToolIds,
    });
    try {
      const approvedArguments = {
        ...browserApproval.payload,
        approval_token: browserApproval.token,
      };
      const result = browserApproval.toolName === "browser_computer"
        ? await api.browserComputer(browserApproval.action, approvedArguments)
        : await api.invokeTool(browserApproval.toolName, { ...approvedArguments, action: browserApproval.action });
      pushActionPreview(
        { id: "browser.approval", label: "Approved Browser Action", icon: "browser" },
        "browser-approval",
        result,
      );
      await api.sendMessage(activeConversationId, "ユーザーが許可しました。承認済みの操作を踏まえて続行してください。", {
        tool_policy: {
          ...(yoloMode ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...(approvalToolIds.length ? { selected_tools: approvalToolIds } : {}),
        },
        tools: approvalToolIds.length ? approvalToolIds : undefined,
        metadata: {
          mode: "chat",
          approval_followup: {
            action: browserApproval.action,
            tool_name: browserApproval.toolName,
          },
          selected_tools: approvalToolIds,
        },
      });
      forgetPendingRequest(activeConversationId);
      replaceChatIdInUrl(activeConversationId, false);
      await loadConversation(activeConversationId, false);
      await refreshConversations(activeConversationId);
    } catch (approvalError) {
      forgetPendingRequest(activeConversationId);
      setError(approvalError instanceof Error ? approvalError.message : "browser/computer の承認に失敗しました。");
    } finally {
      setIsGenerating(false);
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
        result = await defaultspackApiFetch(action.endpoint, { method: action.method ?? "GET" }).then((response) => response.json());
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
      const shouldClearInput = await executeComposerCommand(commandInput.command.id, commandInput.raw);
      if (shouldClearInput !== false) setInput("");
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
    const shouldKeepSelectedToolsAfterSend = keepSelectedToolsAfterSend(settingsValues);
    const selectedToolLabels = [
      ...selectedTools.map((item) => item.label || item.id),
    ];

    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await api.createConversation({
          model: preferredModel || "stub/default",
          conversation_kind: mode === "coding" ? "coding" : null,
          tags: mode === "coding" ? ["coding"] : undefined,
          metadata: mode === "coding"
            ? {
                mode: "coding",
                workspace_id: selectedCodingWorkspaceId,
                workspace_label: codingWorkspaces.find((workspace) => workspace.workspace_id === selectedCodingWorkspaceId)?.label,
              }
            : undefined,
        });
        setActiveConversationId(conversation.id);
      }
      const isOperationsMode = isOperationsConversation(conversation);
      submittedConversationId = conversation.id;
      const requestStartedAt = Date.now();
      rememberPendingRequest({
        conversationId: conversation.id,
        startedAt: requestStartedAt,
        status: `${activeProfile?.display_name ?? preferredModel} が思考中`,
        toolNames: selectedToolLabels,
        toolStartedAt: {},
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
      streamingConversationIdRef.current = conversation.id;
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
      const updateStreamingActivity = (streamEvent: ChatStreamEvent) => {
        if (!isActivityStreamEvent(streamEvent)) return;
        const eventTimestamp = Date.now();
        const activityEvent: ChatActivityEvent = { timestamp: eventTimestamp, ...streamEvent };
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          const appendEvent = (message: ChatMessage): ChatMessage => ({
            ...message,
            events: upsertStreamActivityEvent(message.events ?? [], activityEvent),
          });
          if (!existing) {
            return {
              ...current,
              messages: [...current.messages, appendEvent(assistantDraft)],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => message.id === assistantDraft.id ? appendEvent(message) : message),
          };
        });

        if (activityEvent.phase === "conversation_steer") {
          const processed = Array.isArray(activityEvent.processed)
            ? activityEvent.processed.filter(isConversationSteerItem)
            : [];
          if (processed.length > 0) {
            setSteerItems((current) => {
              const byId = new Map(current.map((item) => [item.id, item]));
              for (const item of processed) byId.set(item.id, item);
              return Array.from(byId.values());
            });
            setModelSteerStatus("ステアを反映しました");
          }
        }

        const status = typeof activityEvent.message === "string" && activityEvent.message.trim()
          ? activityEvent.message.trim()
          : pendingRequests[conversation.id]?.status ?? `${activeProfile?.display_name ?? preferredModel} が思考中`;
        const toolName = typeof activityEvent.tool_name === "string" ? activityEvent.tool_name.trim() : "";
        updatePendingRequests((current) => {
          const existing = current[conversation.id] ?? {
            conversationId: conversation.id,
            startedAt: requestStartedAt,
            status,
            toolNames: selectedToolLabels,
            toolStartedAt: {},
          };
          const toolNames = toolName ? [...new Set([...existing.toolNames, toolName])] : existing.toolNames;
          const toolStartedAt = { ...(existing.toolStartedAt ?? {}) };
          if (toolName && toolStartedAt[toolName] === undefined) {
            toolStartedAt[toolName] = eventTimestamp;
          }
          return {
            ...current,
            [conversation.id]: {
              ...existing,
              status,
              toolNames,
              toolStartedAt,
            },
          };
        });
      };
      const replaceStreamingAssistant = (message: ChatMessage) => {
        const completedAt = Date.now();
        const enhancedMessage: ChatMessage = {
          ...message,
          metadata: {
            ...(message.metadata ?? {}),
            timing: {
              ...((message.metadata?.timing && typeof message.metadata.timing === "object") ? message.metadata.timing as Record<string, unknown> : {}),
              thinking_started_at: requestStartedAt,
              completed_at: completedAt,
              thinking_duration_ms: completedAt - requestStartedAt,
              thinking_duration_label: boundedDurationLabel(requestStartedAt, completedAt),
            },
          },
        };
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const withoutDraft = current.messages.filter((candidate) => candidate.id !== assistantDraft.id);
          const hasFinalMessage = withoutDraft.some((candidate) => candidate.id === enhancedMessage.id);
          return {
            ...current,
            messages: hasFinalMessage
              ? withoutDraft.map((candidate) => candidate.id === enhancedMessage.id ? enhancedMessage : candidate)
              : [...withoutDraft, enhancedMessage],
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
          ...(mode === "coding" && selectedCodingWorkspaceId ? { workspace_id: selectedCodingWorkspaceId } : {}),
          ...(selectedToolIds.length ? { selected_tools: selectedToolIds } : {}),
        },
        attachments: submittedAttachments,
        tools: selectedToolIds.length ? selectedToolIds : undefined,
        metadata: {
          mode: isOperationsMode ? "operations_company" : mode,
          ...(isOperationsMode ? {
            profile_id: "defaultspack.operations_company",
            agent_id: "client_manager",
            conversation_strategy: "one_agent_one_conversation",
            internal_channel: "ops-company",
          } : {}),
          ...(mode === "coding" ? {
            workspace_id: selectedCodingWorkspaceId,
            workspace_label: codingWorkspaces.find((workspace) => workspace.workspace_id === selectedCodingWorkspaceId)?.label,
          } : {}),
          attachments: submittedAttachments.map(({ name, size, type, truncated, source, sourcePath }) => ({ name, size, type, truncated, source, sourcePath })),
          selected_tools: selectedToolIds,
          dropped_widgets: droppedWidgets
            .filter((widget) => widget.widgetKind === "tool_toggle" || widget.type === "tool" ? selectedToolIdSet.has(widget.sourceItemId || widget.id) : widget.enabled !== false)
            .map(({ id, type, label, widgetKind, sourceItemId, metadata }) => ({ id, type, label, widgetKind, sourceItemId, metadata })),
        },
      }, {
        onEvent: updateStreamingActivity,
        onDelta: updateStreamingAssistant,
        onThinkingDelta: updateStreamingThinking,
        onMessage: replaceStreamingAssistant,
        signal: abortController.signal,
      });
      setAttachedFiles([]);
      setDroppedWidgets([]);
      if (!shouldKeepSelectedToolsAfterSend) {
        setStoredSelectedToolIds([]);
      }
      forgetPendingRequest(conversation.id);
      replaceChatIdInUrl(conversation.id, false);

      if (title !== conversation.title) {
        await api.updateConversation(conversation.id, { title });
      }

      await refreshConversations(conversation.id);
      await refreshSteerQueue(conversation.id).catch(console.error);
    } catch (submitError) {
      console.error("Chat error:", submitError);
      if (isCancelledStreamError(submitError)) {
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
      streamingConversationIdRef.current = null;
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
      modelCommandCandidates={modelCommandCandidates}
      modelPickerRequestId={modelPickerRequestId}
      yoloMode={yoloMode}
      mode={mode}
      codingContext={codingContext}
      codingWorkspaces={codingWorkspaces}
      selectedCodingWorkspaceId={selectedCodingWorkspaceId}
      attachedFiles={attachedFiles}
      droppedWidgets={droppedWidgets}
      selectedToolIds={selectedToolIds}
      keyboardButtonNavigation={keyboardButtonNavigation}
      steerStatus={modelSteerStatus}
      steerBusy={modelSteerBusy}
      steerQueuedCount={steerItems.filter((item) => item.status === "queued").length}
      steerPreviewItems={isCentered ? [] : activeComposerSteerItems(steerItems, isGenerating || isConversationPending)}
      onExtensionSelect={handleComposerExtensionSelect}
      onCommandSelect={handleComposerCommand}
      onModelCommandCandidateSelect={handleModelCommandCandidateSelect}
      onModelCommandCandidatesClose={() => setComposerCandidateMenu(null)}
      onModelProfileSelect={handleModelProfileSelect}
      onProviderApiKeySave={handleProviderApiKeySave}
      onThinkingLevelChange={handleThinkingLevelChange}
      onInputChange={handleComposerInputChange}
      onSubmit={handleSubmit}
      onStopGenerating={handleStopGenerating}
      onSteerSubmit={(prompt) => void queueConversationSteer(prompt)}
      onModeChange={handleModeChange}
      onFileAttach={handleFileAttach}
      onAtFileAttach={handleAtFileAttach}
      onFileRemove={handleFileRemove}
      onDropWidget={handleDropWidget}
      onWidgetAction={handleWidgetAction}
      onWidgetToggle={handleWidgetToggle}
      onCodingBranchSwitch={handleCodingBranchSwitch}
      onCodingDirectoryChange={handleCodingDirectoryChange}
      onCodingWorkspaceSelect={handleCodingWorkspaceSelect}
      onCodingWorkspaceTrust={handleCodingWorkspaceTrust}
      onCodingWorkspaceCreate={handleCodingWorkspaceCreate}
      onCodingWorkspacesRefresh={() => void loadCodingWorkspaces()}
      onCodingContextRefresh={loadCodingContext}
    />
  );

  return (
    <RendererBoundary>
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-zinc-800">
      {showRegion("title_bar") && <Renderers.titleBar appName={catalog?.app?.name} appIcon={catalog?.app?.icon} />}

      <div className="flex flex-1 min-h-0">
        {showRegion("history") && !isHistoryMinimized && (
          <div className="w-[286px] max-w-[30vw] min-w-[240px] flex-shrink-0 overflow-hidden border-r border-zinc-800/60 animate-in slide-in-from-left-2 fade-in duration-200 ease-out max-[900px]:w-[260px]">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              onCalendarOpen={() => setWorkspacePanelMode("calendar")}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onChatMetadataChange={handleHistoryMetadataChange}
              onMinimize={() => setIsHistoryMinimized(true)}
            />
          </div>
        )}

        {showRegion("history") && isHistoryMinimized && (
          <div className="rumi-history-rail w-14 flex-shrink-0 overflow-hidden border-r border-zinc-800/60 animate-in slide-in-from-left-1 fade-in duration-150 ease-out">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              onCalendarOpen={() => setWorkspacePanelMode("calendar")}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onChatMetadataChange={handleHistoryMetadataChange}
              onRestore={() => setIsHistoryMinimized(false)}
              isCompact
            />
          </div>
        )}

        <main className={cn("rumi-workspace-main flex-1 flex min-w-0 bg-[#09090b] relative", isActivityPreviewVisible && "has-activity-preview")}>
          <div className={cn("rumi-chat-pane flex-1 flex flex-col min-w-0", isActivityPreviewVisible && "border-r border-zinc-800/40")}>
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
                  {workspacePanelMode === "calendar" ? (
                    <CalendarComposerPanel
                      onClose={() => setWorkspacePanelMode("composer")}
                      onResult={(label, result) => pushActionPreview({ id: label, label, icon: "calendar" }, label, result)}
                    />
                  ) : renderComposer(true)}
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
                pendingStartedAt={pendingRequest?.startedAt ?? null}
                pendingToolStartedAt={pendingRequest?.toolStartedAt ?? {}}
                messages={messages}
                messagesEndRef={messagesEndRef}
                unknownBlockStrategy={unknownBlockStrategy}
                showActivityInMessages={showActivityInMessages}
                showWidgets={showWidgets}
                onSuggestionClick={(text) => setInput(text)}
                onOpenToolPreview={(previewId) => {
                  setActivePreviewId(previewId);
                  setShowPreview(true);
                }}
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
                {workspacePanelMode === "calendar" ? (
                  <CalendarComposerPanel
                    onClose={() => setWorkspacePanelMode("composer")}
                    onResult={(label, result) => pushActionPreview({ id: label, label, icon: "calendar" }, label, result)}
                  />
                ) : renderComposer(false)}
              </div>
            )}
          </div>

          {mode === "coding" && (
            <CodingCockpit
              workspaces={codingWorkspaces}
              selectedWorkspaceId={selectedCodingWorkspaceId}
              onWorkspaceSelect={handleCodingWorkspaceSelect}
              onWorkspacesRefresh={() => void loadCodingWorkspaces()}
            />
          )}

          {isActivityPreviewVisible && (
            <aside className="rumi-activity-preview-pane" aria-label="Activity preview">
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
            </aside>
          )}
        </main>

        {showRegion("right_sidebar") && (
          <Renderers.rightSidebar
            items={sidebarItems}
            activeItemId={activeSidebarItemId ? `${activeSidebarItemId}:${sidebarSelectionTick}` : null}
            settingsValues={settingsValues}
            settingsSections={settingsSections}
            selectedToolIds={selectedToolIds}
            companyPanel={<CompanyWorkspacePanel />}
            keyboardButtonNavigation={keyboardButtonNavigation}
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
            onToolBatchSet={handleToolBatchSet}
            onPanelAction={handlePanelAction}
          />
        )}
      </div>

      <ConversationSpotlight
        isOpen={isSpotlightOpen}
        query={spotlightQuery}
        filter={spotlightFilter}
        results={visibleSpotlightResults}
        selectedIndex={spotlightSelectedIndex}
        loading={spotlightLoading}
        locale={locale}
        onQueryChange={setSpotlightQuery}
        onFilterChange={setSpotlightFilter}
        onKeyDown={handleSpotlightKeyDown}
        onClose={closeSpotlight}
        onOpenResult={openSpotlightResult}
      />

      {showRegion("settings_modal") && (
        <Renderers.settingsModal
          isOpen={isSettingsOpen}
          activeSectionId={requestedSettingsSectionId}
          catalog={catalog}
          health={health}
          previewsCount={canvasPreviews.length}
          settingsSections={settingsSections}
          settingsValues={settingsValues}
          locale={locale}
          onClose={() => setIsSettingsOpen(false)}
          onSettingChange={handleSettingChange}
        />
      )}
    </div>
    </RendererBoundary>
  );
}
