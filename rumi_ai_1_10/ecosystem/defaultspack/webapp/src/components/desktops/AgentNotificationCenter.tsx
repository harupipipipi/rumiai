import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Bell,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Filter,
  Inbox,
  MessageSquareReply,
  RefreshCw,
  Search,
  Sparkles,
  TimerReset,
  XCircle,
} from "lucide-react";

import { api, type ChatMessage, type Conversation } from "../../lib/api";
import { formatRelativeTime, messageToText, orderConversationMessages } from "../../lib/chat";
import { cn } from "../../lib/cn";
import { PENDING_CHAT_REQUEST_TTL_MS, isAssistantMessageStillRunning, type PendingChatRequest } from "../../lib/pendingChat";

type AgentNotificationStatus = "waiting" | "running" | "done" | "failed";
type AgentNotificationFilter = "attention" | AgentNotificationStatus | "all";
type AgentNotificationPriority = "high" | "normal" | "low";

type AgentNotificationItem = {
  id: string;
  conversationId: string;
  title: string;
  status: AgentNotificationStatus;
  priority: AgentNotificationPriority;
  summary: string;
  detail: string;
  source: string;
  toolNames: string[];
  updatedAt: number;
  startedAt?: number;
  unread: boolean;
  fingerprint: string;
};

type AgentNotificationCenterProps = {
  className?: string;
};

const PENDING_REQUESTS_STORAGE_KEY = "rumi-pending-chat-requests";
const READ_STATE_STORAGE_KEY = "rumi-agent-notification-read-state.v1";
const SNOOZE_STATE_STORAGE_KEY = "rumi-agent-notification-snooze-state.v1";
const TOAST_SEEN_STORAGE_KEY = "rumi-agent-notification-toast-seen.v1";

const STATUS_LABELS: Record<AgentNotificationStatus, string> = {
  waiting: "回答待ち",
  running: "実行中",
  done: "完了",
  failed: "失敗",
};

const STATUS_HELP: Record<AgentNotificationStatus, string> = {
  waiting: "あなたの返信、承認、判断を待っています。",
  running: "Agent が処理中です。完了したらここに残ります。",
  done: "Agent の応答が完了しました。未読の完了は要対応に残します。",
  failed: "失敗または中断を検知しました。会話を開いて詳細を確認できます。",
};

const STATUS_ORDER: Record<AgentNotificationStatus, number> = {
  waiting: 0,
  failed: 1,
  running: 2,
  done: 3,
};

function readJsonRecord(key: string): Record<string, unknown> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function writeJsonRecord(key: string, value: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage failures in private or restricted browser contexts.
  }
}

function readNumericRecord(key: string): Record<string, number> {
  const raw = readJsonRecord(key);
  const result: Record<string, number> = {};
  for (const [entryKey, value] of Object.entries(raw)) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) result[entryKey] = numeric;
  }
  return result;
}

function readPendingRequests(now = Date.now()): Record<string, PendingChatRequest> {
  const raw = readJsonRecord(PENDING_REQUESTS_STORAGE_KEY);
  const result: Record<string, PendingChatRequest> = {};
  for (const [conversationId, value] of Object.entries(raw)) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const record = value as Record<string, unknown>;
    const startedAt = Number(record.startedAt);
    if (!conversationId || !Number.isFinite(startedAt)) continue;
    if (now - startedAt >= PENDING_CHAT_REQUEST_TTL_MS) continue;
    const toolNames = Array.isArray(record.toolNames)
      ? record.toolNames.map((item) => String(item).trim()).filter(Boolean)
      : [];
    const toolStartedAtRaw = record.toolStartedAt && typeof record.toolStartedAt === "object" && !Array.isArray(record.toolStartedAt)
      ? record.toolStartedAt as Record<string, unknown>
      : {};
    const toolStartedAt: Record<string, number> = {};
    for (const [toolName, value] of Object.entries(toolStartedAtRaw)) {
      const numeric = Number(value);
      if (Number.isFinite(numeric)) toolStartedAt[toolName] = numeric;
    }
    result[conversationId] = {
      conversationId,
      startedAt,
      status: String(record.status ?? "Agent が実行中"),
      toolNames,
      toolStartedAt,
      recoveredFromLocation: record.recoveredFromLocation === true,
    };
  }
  return result;
}

function latestMessage(conversation: Conversation): ChatMessage | undefined {
  const ordered = orderConversationMessages(conversation.messages ?? []);
  return ordered[ordered.length - 1];
}

function conversationEvents(conversation: Conversation) {
  return (conversation.messages ?? []).flatMap((message) => message.events ?? []);
}

function metadataRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function messageHasPendingApproval(message: ChatMessage | undefined): boolean {
  if (!message) return false;
  const metadata = metadataRecord(message.metadata);
  if (metadata.pending_approval || metadata.pendingApproval) return true;
  if (metadata.pending_authority_approval || metadata.pendingAuthorityApproval) return true;
  return (message.events ?? []).some((event) => event.type === "approval_requested");
}

function messageFailed(message: ChatMessage | undefined): boolean {
  if (!message) return false;
  const finishReason = String(message.finish_reason ?? "").toLowerCase();
  if (["failed", "error", "cancelled", "interrupted"].includes(finishReason)) return true;
  const metadata = metadataRecord(message.metadata);
  const transport = metadataRecord(metadata.transport);
  const transportStatus = String(transport.status ?? "").toLowerCase();
  if (["failed", "error", "interrupted"].includes(transportStatus)) return true;
  return (message.events ?? []).some((event) => {
    const eventType = String(event.type ?? "").toLowerCase();
    const status = String(event.status ?? "").toLowerCase();
    return eventType === "task_failed" || status === "failed" || status === "error";
  });
}

function eventFailed(conversation: Conversation): boolean {
  return conversationEvents(conversation).some((event) => {
    const eventType = String(event.type ?? "").toLowerCase();
    const status = String(event.status ?? "").toLowerCase();
    return eventType === "task_failed" || status === "failed" || status === "error";
  });
}

function collectToolNames(conversation: Conversation, pending?: PendingChatRequest): string[] {
  const toolNames = new Set<string>();
  for (const toolName of pending?.toolNames ?? []) {
    if (toolName.trim()) toolNames.add(toolName.trim());
  }
  for (const event of conversationEvents(conversation)) {
    const eventToolName = typeof event.tool_name === "string" ? event.tool_name.trim() : "";
    if (eventToolName) toolNames.add(eventToolName);
  }
  return [...toolNames].slice(0, 6);
}

function firstUsefulLine(text: string): string {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean) ?? "";
}

function truncateText(text: string, maxLength: number): string {
  const normalized = text.trim().replace(/\s+/g, " ");
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1).trim()}…`;
}

function sourceLabel(conversation: Conversation): string {
  const metadata = conversation.metadata ?? {};
  const workspaceLabel = typeof metadata.workspace_label === "string" ? metadata.workspace_label.trim() : "";
  const workspaceId = typeof metadata.workspace_id === "string" ? metadata.workspace_id.trim() : "";
  const externalProvider = typeof metadata.external_provider === "string" ? metadata.external_provider.trim() : "";
  if (workspaceLabel) return workspaceLabel;
  if (workspaceId) return workspaceId;
  if (externalProvider) return externalProvider.toUpperCase();
  if (conversation.conversation_kind === "coding" || conversation.tags?.includes("coding")) return "Coding";
  if (conversation.conversation_kind === "operations_company") return "Operations";
  if (conversation.conversation_kind === "mimo_coding_company") return "Mimo Coding";
  return "Chat";
}

function buildSummary(
  conversation: Conversation,
  status: AgentNotificationStatus,
  latest: ChatMessage | undefined,
  pending?: PendingChatRequest,
): { summary: string; detail: string } {
  const latestText = latest ? messageToText(latest) : "";
  const firstLine = firstUsefulLine(latestText);
  if (status === "running") {
    return {
      summary: pending?.status || "Agent が実行中です",
      detail: pending?.toolNames?.length
        ? `${pending.toolNames.join(", ")} を使って処理しています。`
        : "処理状況は自動更新されます。",
    };
  }
  if (status === "waiting") {
    return {
      summary: messageHasPendingApproval(latest) ? "承認または判断を待っています" : "あなたの返信待ちです",
      detail: firstLine ? truncateText(firstLine, 220) : "会話を開いて、次に必要な返信や承認を確認してください。",
    };
  }
  if (status === "failed") {
    const failedEvent = [...conversationEvents(conversation)].reverse().find((event) => {
      const eventType = String(event.type ?? "").toLowerCase();
      const eventStatus = String(event.status ?? "").toLowerCase();
      return eventType === "task_failed" || eventStatus === "failed" || eventStatus === "error";
    });
    const eventMessage = typeof failedEvent?.message === "string" ? failedEvent.message.trim() : "";
    return {
      summary: eventMessage || firstLine || "Agent の実行が失敗しました",
      detail: firstLine && firstLine !== eventMessage ? truncateText(firstLine, 220) : "会話を開いてエラーと次の復旧手順を確認してください。",
    };
  }
  return {
    summary: firstLine ? truncateText(firstLine, 180) : "Agent の応答が完了しました",
    detail: firstLine ? truncateText(latestText, 260) : "クリックすると完了した回答へ移動できます。",
  };
}

function classifyConversation(conversation: Conversation, pendingRequests: Record<string, PendingChatRequest>, readState: Record<string, number>, now = Date.now()): AgentNotificationItem {
  const pending = pendingRequests[conversation.id];
  const latest = latestMessage(conversation);
  let status: AgentNotificationStatus = "done";
  if (pending || isAssistantMessageStillRunning(latest)) {
    status = "running";
  } else if (messageHasPendingApproval(latest) || latest?.role === "user") {
    status = "waiting";
  } else if (messageFailed(latest) || eventFailed(conversation)) {
    status = "failed";
  }
  const { summary, detail } = buildSummary(conversation, status, latest, pending);
  const updatedAt = Number(conversation.updated_at || latest?.created_at || now);
  const readAt = readState[conversation.id] ?? 0;
  const fingerprint = `${conversation.id}:${status}:${updatedAt}:${summary}`;
  const priority: AgentNotificationPriority = status === "failed" || status === "waiting"
    ? "high"
    : status === "running"
      ? "normal"
      : "low";
  return {
    id: `${conversation.id}:${status}`,
    conversationId: conversation.id,
    title: conversation.title?.trim() || "Untitled conversation",
    status,
    priority,
    summary,
    detail,
    source: sourceLabel(conversation),
    toolNames: collectToolNames(conversation, pending),
    updatedAt,
    startedAt: pending?.startedAt,
    unread: updatedAt > readAt && status !== "running",
    fingerprint,
  };
}

function statusTone(status: AgentNotificationStatus): string {
  if (status === "waiting") return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  if (status === "running") return "border-blue-500/30 bg-blue-500/10 text-blue-100";
  if (status === "failed") return "border-red-500/30 bg-red-500/10 text-red-100";
  return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
}

function StatusIcon({ status, className }: { status: AgentNotificationStatus; className?: string }) {
  if (status === "waiting") return <MessageSquareReply className={className} size={15} />;
  if (status === "running") return <Clock3 className={className} size={15} />;
  if (status === "failed") return <XCircle className={className} size={15} />;
  return <CheckCircle2 className={className} size={15} />;
}

function openConversation(conversationId: string) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.pathname = "/chat";
  url.searchParams.set("chat", conversationId);
  url.searchParams.set("chat_id", conversationId);
  url.searchParams.set("conversation_id", conversationId);
  url.searchParams.delete("pending");
  window.location.assign(`${url.pathname}${url.search}${url.hash}`);
}

export function AgentNotificationCenter({ className }: AgentNotificationCenterProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [pendingRequests, setPendingRequests] = useState<Record<string, PendingChatRequest>>({});
  const [readState, setReadState] = useState<Record<string, number>>(() => readNumericRecord(READ_STATE_STORAGE_KEY));
  const [readStateBootstrapped, setReadStateBootstrapped] = useState(() => Object.keys(readJsonRecord(READ_STATE_STORAGE_KEY)).length > 0);
  const [snoozeState, setSnoozeState] = useState<Record<string, number>>(() => readNumericRecord(SNOOZE_STATE_STORAGE_KEY));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<AgentNotificationFilter>("attention");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toastItem, setToastItem] = useState<AgentNotificationItem | null>(null);

  const updateReadState = useCallback((nextState: Record<string, number>) => {
    setReadState(nextState);
    writeJsonRecord(READ_STATE_STORAGE_KEY, nextState);
  }, []);

  const refresh = useCallback(async () => {
    const now = Date.now();
    setRefreshing(true);
    setPendingRequests(readPendingRequests(now));
    setReadState(readNumericRecord(READ_STATE_STORAGE_KEY));
    setSnoozeState(readNumericRecord(SNOOZE_STATE_STORAGE_KEY));
    try {
      const result = await api.listConversations({
        include_messages: true,
        is_archived: false,
        limit: 120,
      });
      setConversations(result.conversations);
      setError(null);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "通知の読み込みに失敗しました。");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 8_000);
    const handleFocus = () => void refresh();
    const handleStorage = (event: StorageEvent) => {
      if (!event.key || [PENDING_REQUESTS_STORAGE_KEY, READ_STATE_STORAGE_KEY, SNOOZE_STATE_STORAGE_KEY].includes(event.key)) {
        void refresh();
      }
    };
    window.addEventListener("focus", handleFocus);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("storage", handleStorage);
    };
  }, [refresh]);

  const items = useMemo(() => {
    const now = Date.now();
    return conversations
      .map((conversation) => classifyConversation(conversation, pendingRequests, readState, now))
      .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || b.updatedAt - a.updatedAt);
  }, [conversations, pendingRequests, readState]);

  const visibleItems = useMemo(() => {
    const now = Date.now();
    const normalizedQuery = query.trim().toLowerCase();
    return items
      .filter((item) => {
        const snoozedUntil = snoozeState[item.conversationId] ?? 0;
        if (filter !== "all" && snoozedUntil > now) return false;
        if (filter === "attention") return item.status !== "done" || item.unread;
        if (filter === "all") return true;
        return item.status === filter;
      })
      .filter((item) => {
        if (!normalizedQuery) return true;
        return [
          item.title,
          item.summary,
          item.detail,
          item.source,
          item.status,
          ...item.toolNames,
        ].join(" ").toLowerCase().includes(normalizedQuery);
      });
  }, [filter, items, query, snoozeState]);

  const selectedItem = useMemo(() => {
    return visibleItems.find((item) => item.id === selectedId)
      ?? visibleItems[0]
      ?? items[0]
      ?? null;
  }, [items, selectedId, visibleItems]);

  useEffect(() => {
    if (!selectedItem) return;
    setSelectedId(selectedItem.id);
  }, [selectedItem?.id]);

  useEffect(() => {
    if (loading || readStateBootstrapped) return;
    const stored = readNumericRecord(READ_STATE_STORAGE_KEY);
    if (Object.keys(stored).length > 0) {
      setReadState(stored);
      setReadStateBootstrapped(true);
      return;
    }
    const nextState: Record<string, number> = {};
    for (const item of items) {
      if (item.status === "done") nextState[item.conversationId] = item.updatedAt;
    }
    updateReadState(nextState);
    setReadStateBootstrapped(true);
  }, [items, loading, readStateBootstrapped, updateReadState]);

  const counts = useMemo(() => {
    const base: Record<AgentNotificationStatus | "attention" | "all" | "unread", number> = {
      attention: 0,
      waiting: 0,
      running: 0,
      done: 0,
      failed: 0,
      all: items.length,
      unread: 0,
    };
    for (const item of items) {
      base[item.status] += 1;
      if (item.unread) base.unread += 1;
      if (item.status !== "done" || item.unread) base.attention += 1;
    }
    return base;
  }, [items]);

  useEffect(() => {
    if (!readStateBootstrapped) return;
    const candidate = items.find((item) => item.unread && (item.status === "done" || item.status === "waiting" || item.status === "failed"));
    if (!candidate) return;
    const toastKey = candidate.fingerprint;
    try {
      if (window.localStorage.getItem(TOAST_SEEN_STORAGE_KEY) === toastKey) return;
      window.localStorage.setItem(TOAST_SEEN_STORAGE_KEY, toastKey);
    } catch {
      // Toast can still show even when storage is unavailable.
    }
    setToastItem(candidate);
    const timer = window.setTimeout(() => {
      setToastItem((current) => current?.fingerprint === toastKey ? null : current);
    }, 5_200);
    return () => window.clearTimeout(timer);
  }, [items, readStateBootstrapped]);

  const markRead = useCallback((item: AgentNotificationItem) => {
    updateReadState({
      ...readState,
      [item.conversationId]: Math.max(readState[item.conversationId] ?? 0, item.updatedAt),
    });
  }, [readState, updateReadState]);

  const markAllRead = useCallback(() => {
    const nextState = { ...readState };
    for (const item of items) nextState[item.conversationId] = Math.max(nextState[item.conversationId] ?? 0, item.updatedAt);
    updateReadState(nextState);
  }, [items, readState, updateReadState]);

  const snooze = useCallback((item: AgentNotificationItem) => {
    const nextState = {
      ...snoozeState,
      [item.conversationId]: Date.now() + 60 * 60_000,
    };
    setSnoozeState(nextState);
    writeJsonRecord(SNOOZE_STATE_STORAGE_KEY, nextState);
  }, [snoozeState]);

  const openItem = useCallback((item: AgentNotificationItem) => {
    markRead(item);
    openConversation(item.conversationId);
  }, [markRead]);

  const filterOptions: Array<{ id: AgentNotificationFilter; label: string; count: number }> = [
    { id: "attention", label: "要対応", count: counts.attention },
    { id: "waiting", label: "回答待ち", count: counts.waiting },
    { id: "running", label: "実行中", count: counts.running },
    { id: "done", label: "完了", count: counts.done },
    { id: "failed", label: "失敗", count: counts.failed },
    { id: "all", label: "すべて", count: counts.all },
  ];

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl border border-zinc-800/80 bg-[#101114] shadow-[0_18px_55px_rgba(0,0,0,0.28)]",
        className,
      )}
      aria-label="Agent notification center"
    >
      {toastItem && (
        <button
          type="button"
          onClick={() => openItem(toastItem)}
          className="absolute right-3 top-3 z-20 w-[min(360px,calc(100%-24px))] rounded-2xl border border-zinc-700/90 bg-zinc-950/95 p-3 text-left shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur transition hover:border-zinc-500"
        >
          <div className="flex items-start gap-3">
            <span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border", statusTone(toastItem.status))}>
              <StatusIcon status={toastItem.status} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                通知
                <span className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[10px] normal-case tracking-normal text-zinc-300">
                  {STATUS_LABELS[toastItem.status]}
                </span>
              </span>
              <span className="mt-1 block truncate text-sm font-semibold text-zinc-100">{toastItem.title}</span>
              <span className="mt-0.5 block line-clamp-2 text-xs leading-5 text-zinc-400">{toastItem.summary}</span>
            </span>
            <ExternalLink size={14} className="mt-1 shrink-0 text-zinc-500" />
          </div>
        </button>
      )}

      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-800/80 bg-[#121316] px-4 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-zinc-700/80 bg-zinc-950 text-zinc-100">
              <Bell size={17} />
              {counts.unread > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-300 px-1 text-[10px] font-bold text-zinc-950">
                  {counts.unread > 9 ? "9+" : counts.unread}
                </span>
              )}
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-zinc-100">Agent 通知センター</h2>
              <p className="truncate text-xs text-zinc-500">完了、回答待ち、実行中のチャットをここでまとめて捌きます。</p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            更新
          </button>
          <button
            type="button"
            onClick={markAllRead}
            disabled={items.length === 0}
            className="h-8 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs font-medium text-zinc-300 transition hover:border-zinc-600 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            すべて既読
          </button>
        </div>
      </div>

      <div className="grid gap-2 border-b border-zinc-800/70 px-4 py-3 sm:grid-cols-2 min-[1180px]:grid-cols-4">
        {(["waiting", "running", "done", "failed"] as AgentNotificationStatus[]).map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setFilter(status)}
            className={cn(
              "flex items-center justify-between rounded-xl border px-3 py-2 text-left transition",
              filter === status
                ? "border-zinc-500 bg-zinc-900/90"
                : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700 hover:bg-zinc-900/60",
            )}
          >
            <span className="flex items-center gap-2">
              <span className={cn("flex h-7 w-7 items-center justify-center rounded-lg border", statusTone(status))}>
                <StatusIcon status={status} />
              </span>
              <span>
                <span className="block text-xs font-semibold text-zinc-100">{STATUS_LABELS[status]}</span>
                <span className="block text-[10px] text-zinc-600">{STATUS_HELP[status]}</span>
              </span>
            </span>
            <span className="text-lg font-semibold text-zinc-200">{counts[status]}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800/70 px-4 py-3">
        <label className="relative min-w-[220px] flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="タイトル・内容・toolで検索"
            className="h-9 w-full rounded-xl border border-zinc-800 bg-zinc-950 pl-9 pr-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-500"
          />
        </label>
        <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
          <span className="mr-1 hidden items-center gap-1 text-[11px] text-zinc-600 sm:inline-flex">
            <Filter size={12} />
            filter
          </span>
          {filterOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setFilter(option.id)}
              className={cn(
                "whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-medium transition",
                filter === option.id
                  ? "border-zinc-400 bg-zinc-100 text-zinc-950"
                  : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
              )}
            >
              {option.label}
              <span className="ml-1 opacity-60">{option.count}</span>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-3 rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-100">
          {error}
        </div>
      )}

      <div className="grid min-h-[360px] gap-3 p-4 min-[1180px]:grid-cols-[minmax(0,1fr)_330px]">
        <div className="min-h-0 overflow-hidden rounded-xl border border-zinc-800/70 bg-zinc-950/25">
          <div className="flex items-center justify-between border-b border-zinc-800/70 px-3 py-2">
            <div className="text-xs font-medium text-zinc-400">
              {loading ? "読み込み中" : `${visibleItems.length}件を表示`}
            </div>
            <div className="flex items-center gap-1 text-[11px] text-zinc-600">
              <Sparkles size={12} />
              新しい完了は自動で上に出ます
            </div>
          </div>
          <div className="max-h-[520px] overflow-y-auto p-2">
            {loading && visibleItems.length === 0 ? (
              <div className="flex h-44 items-center justify-center text-sm text-zinc-500">
                通知を読み込んでいます…
              </div>
            ) : visibleItems.length === 0 ? (
              <div className="flex h-44 flex-col items-center justify-center gap-2 text-center text-sm text-zinc-500">
                <Inbox size={28} className="text-zinc-700" />
                <div>
                  <p className="font-medium text-zinc-400">いま見るべき通知はありません</p>
                  <p className="mt-1 text-xs text-zinc-600">完了・回答待ち・失敗はここに集まります。</p>
                </div>
              </div>
            ) : (
              <div className="grid gap-2">
                {visibleItems.map((item) => (
                  <article
                    key={item.id}
                    className={cn(
                      "rounded-xl border p-3 transition",
                      selectedItem?.id === item.id
                        ? "border-zinc-500 bg-zinc-900/80"
                        : "border-zinc-800/90 bg-[#0c0d10] hover:border-zinc-700 hover:bg-zinc-900/55",
                      item.unread && "shadow-[inset_3px_0_0_rgba(251,191,36,0.9)]",
                    )}
                    onMouseEnter={() => setSelectedId(item.id)}
                  >
                    <div className="flex items-start gap-3">
                      <button
                        type="button"
                        onClick={() => openItem(item)}
                        className={cn("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition hover:scale-[1.02]", statusTone(item.status))}
                        aria-label={`${item.title}を開く`}
                      >
                        <StatusIcon status={item.status} />
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-start justify-between gap-3">
                          <button
                            type="button"
                            onClick={() => openItem(item)}
                            className="min-w-0 text-left"
                          >
                            <div className="flex min-w-0 items-center gap-2">
                              {item.unread && <span className="h-2 w-2 shrink-0 rounded-full bg-amber-300" aria-label="未読" />}
                              <h3 className="truncate text-sm font-semibold text-zinc-100">{item.title}</h3>
                            </div>
                            <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-400">{item.summary}</p>
                          </button>
                          <span className="shrink-0 text-[11px] text-zinc-600">{formatRelativeTime(item.updatedAt)}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium", statusTone(item.status))}>
                            {STATUS_LABELS[item.status]}
                          </span>
                          <span className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">
                            {item.source}
                          </span>
                          {item.toolNames.slice(0, 3).map((toolName) => (
                            <span key={toolName} className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">
                              {toolName}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => markRead(item)}
                        className="rounded-lg border border-zinc-800 px-2.5 py-1 text-[11px] font-medium text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100"
                      >
                        既読
                      </button>
                      <button
                        type="button"
                        onClick={() => snooze(item)}
                        className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 px-2.5 py-1 text-[11px] font-medium text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100"
                      >
                        <TimerReset size={12} />
                        1h スヌーズ
                      </button>
                      <button
                        type="button"
                        onClick={() => openItem(item)}
                        className="inline-flex items-center gap-1 rounded-lg bg-zinc-100 px-2.5 py-1 text-[11px] font-semibold text-zinc-950 transition hover:bg-white"
                      >
                        開く
                        <ExternalLink size={12} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>

        <aside className="min-h-0 rounded-xl border border-zinc-800/70 bg-[#0c0d10] p-3">
          {selectedItem ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex items-start gap-3">
                <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border", statusTone(selectedItem.status))}>
                  <StatusIcon status={selectedItem.status} />
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-600">selected</p>
                  <h3 className="mt-1 line-clamp-2 text-sm font-semibold text-zinc-100">{selectedItem.title}</h3>
                </div>
              </div>

              <div className="mt-4 grid gap-2 text-xs">
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/45 p-3">
                  <p className="font-medium text-zinc-200">{selectedItem.summary}</p>
                  <p className="mt-2 leading-5 text-zinc-500">{selectedItem.detail}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/45 p-3">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">状態</p>
                    <p className="mt-1 font-medium text-zinc-200">{STATUS_LABELS[selectedItem.status]}</p>
                  </div>
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/45 p-3">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">更新</p>
                    <p className="mt-1 font-medium text-zinc-200">{formatRelativeTime(selectedItem.updatedAt)}</p>
                  </div>
                </div>
                {selectedItem.startedAt && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/45 p-3">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">開始から</p>
                    <p className="mt-1 font-medium text-zinc-200">{formatRelativeTime(selectedItem.startedAt)}</p>
                  </div>
                )}
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/45 p-3">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-600">Source</p>
                  <p className="mt-1 font-medium text-zinc-200">{selectedItem.source}</p>
                  {selectedItem.toolNames.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {selectedItem.toolNames.map((toolName) => (
                        <span key={toolName} className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">
                          {toolName}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-auto flex flex-col gap-2 pt-4">
                <button
                  type="button"
                  onClick={() => openItem(selectedItem)}
                  className="inline-flex h-9 items-center justify-center gap-2 rounded-xl bg-zinc-100 text-xs font-semibold text-zinc-950 transition hover:bg-white"
                >
                  このチャットへ移動
                  <ExternalLink size={13} />
                </button>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => markRead(selectedItem)}
                    className="h-8 rounded-xl border border-zinc-800 text-xs font-medium text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100"
                  >
                    既読にする
                  </button>
                  <button
                    type="button"
                    onClick={() => snooze(selectedItem)}
                    className="h-8 rounded-xl border border-zinc-800 text-xs font-medium text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100"
                  >
                    1h隠す
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-2 text-center text-sm text-zinc-500">
              <AlertCircle size={26} className="text-zinc-700" />
              <p>通知を選択すると、ここに詳細が出ます。</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
