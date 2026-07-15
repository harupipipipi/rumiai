import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bell,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Inbox,
  MessageSquareReply,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";

import { listAgentNotifications } from "../../features/notifications/resources/agentNotificationResources";
import { formatRelativeTime } from "../../lib/chat";
import { cn } from "../../lib/cn";
import { layerClassName } from "../../ui/layers/layerTokens";

type AgentNotificationStatus = "waiting" | "running" | "done" | "failed";
type AgentNotificationFilter = "attention" | "running" | "done" | "all";

type AgentNotificationItem = {
  id: string;
  conversationId: string;
  title: string;
  status: AgentNotificationStatus;
  summary: string;
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

const READ_STATE_STORAGE_KEY = "rumi-agent-notification-read-state.v1";
const TOAST_SEEN_STORAGE_KEY = "rumi-agent-notification-toast-seen.v1";

const STATUS_LABELS: Record<AgentNotificationStatus, string> = {
  waiting: "回答待ち",
  running: "実行中",
  done: "完了",
  failed: "失敗",
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
    // Storage may be unavailable in restricted browser contexts.
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
  const [projectedItems, setProjectedItems] = useState<Omit<AgentNotificationItem, "unread">[]>([]);
  const [storageNamespace, setStorageNamespace] = useState("");
  const readStorageKey = storageNamespace ? `${READ_STATE_STORAGE_KEY}:${storageNamespace}` : "";
  const toastStorageKey = storageNamespace ? `${TOAST_SEEN_STORAGE_KEY}:${storageNamespace}` : "";
  const [readState, setReadState] = useState<Record<string, number>>({});
  const [readStateBootstrapped, setReadStateBootstrapped] = useState(false);
  const [filter, setFilter] = useState<AgentNotificationFilter>("attention");
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toastItem, setToastItem] = useState<AgentNotificationItem | null>(null);

  const updateReadState = useCallback((nextState: Record<string, number>) => {
    setReadState(nextState);
    if (readStorageKey) writeJsonRecord(readStorageKey, nextState);
  }, [readStorageKey]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const projection = await listAgentNotifications();
      const namespace = projection.storage_namespace;
      const scopedReadKey = `${READ_STATE_STORAGE_KEY}:${namespace}`;
      setStorageNamespace(namespace);
      setReadState(readNumericRecord(scopedReadKey));
      setReadStateBootstrapped(Object.keys(readJsonRecord(scopedReadKey)).length > 0);
      setProjectedItems(projection.items.map((item) => ({
        id: item.id,
        conversationId: item.conversation_id,
        title: item.title,
        status: item.status,
        summary: item.summary,
        source: item.source,
        toolNames: item.tool_names,
        updatedAt: item.updated_at,
        fingerprint: item.fingerprint,
      })));
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
    const interval = window.setInterval(() => void refresh(), 30_000);
    const handleFocus = () => void refresh();
    const handleStorage = (event: StorageEvent) => {
      if (!event.key || event.key === readStorageKey) {
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
  }, [readStorageKey, refresh]);

  const items = useMemo(() => {
    return projectedItems
      .map((item) => ({ ...item, unread: item.updatedAt > (readState[item.conversationId] ?? 0) && item.status !== "running" }))
      .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || b.updatedAt - a.updatedAt);
  }, [projectedItems, readState]);

  useEffect(() => {
    if (loading || readStateBootstrapped) return;
    if (!readStorageKey) return;
    const stored = readNumericRecord(readStorageKey);
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
  }, [items, loading, readStateBootstrapped, readStorageKey, updateReadState]);

  const counts = useMemo(() => {
    const base: Record<AgentNotificationStatus | AgentNotificationFilter | "unread", number> = {
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

  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return items
      .filter((item) => {
        if (filter === "attention") return item.status !== "done" || item.unread;
        if (filter === "all") return true;
        return item.status === filter;
      })
      .filter((item) => {
        if (!normalizedQuery) return true;
        return [item.title, item.summary, item.source, item.status, ...item.toolNames]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      });
  }, [filter, items, query]);

  useEffect(() => {
    if (!readStateBootstrapped) return;
    const candidate = items.find((item) => item.unread && (item.status === "done" || item.status === "waiting" || item.status === "failed"));
    if (!candidate) return;
    const toastKey = candidate.fingerprint;
    try {
      if (!toastStorageKey || window.localStorage.getItem(toastStorageKey) === toastKey) return;
      window.localStorage.setItem(toastStorageKey, toastKey);
    } catch {
      // Toast can still show even when storage is unavailable.
    }
    setToastItem(candidate);
    const timer = window.setTimeout(() => {
      setToastItem((current) => current?.fingerprint === toastKey ? null : current);
    }, 5_200);
    return () => window.clearTimeout(timer);
  }, [items, readStateBootstrapped, toastStorageKey]);

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

  const openItem = useCallback((item: AgentNotificationItem) => {
    markRead(item);
    openConversation(item.conversationId);
  }, [markRead]);

  const filterOptions: Array<{ id: AgentNotificationFilter; label: string; count: number }> = [
    { id: "attention", label: "見るべき", count: counts.attention },
    { id: "running", label: "実行中", count: counts.running },
    { id: "done", label: "完了", count: counts.done },
    { id: "all", label: "すべて", count: counts.all },
  ];

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl border border-zinc-800/80 bg-[#101114] shadow-[0_18px_55px_rgba(0,0,0,0.24)]",
        className,
      )}
      aria-label="Agent notification center"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/80 bg-[#121316] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-zinc-700/80 bg-zinc-950 text-zinc-100">
            <Bell size={17} />
            {counts.unread > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-300 px-1 text-[10px] font-bold text-zinc-950">
                {counts.unread > 9 ? "9+" : counts.unread}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-zinc-100">Agent 通知</h2>
            <p className="truncate text-xs text-zinc-500">見るべきチャットだけを上から処理します。</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="hidden rounded-full border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-500 sm:inline-flex">
            回答待ち {counts.waiting}
          </span>
          <span className="hidden rounded-full border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-500 sm:inline-flex">
            失敗 {counts.failed}
          </span>
          <button
            type="button"
            onClick={() => setShowSearch((value) => !value)}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100",
              showSearch && "border-zinc-600 bg-zinc-900 text-zinc-100",
            )}
            aria-label="通知を検索"
            title="検索"
          >
            <Search size={14} />
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-60"
            aria-label="通知を更新"
            title="更新"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            onClick={markAllRead}
            disabled={items.length === 0}
            className="h-8 rounded-lg border border-zinc-800 px-2.5 text-[11px] font-medium text-zinc-400 transition hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-60"
          >
            既読化
          </button>
        </div>
      </div>

      {toastItem && (
        <button
          type="button"
          onClick={() => openItem(toastItem)}
          // Keep the toast in normal flow below the controls so it cannot
          // intercept notification actions while remaining clickable.
          className={cn(layerClassName.toast, "mx-3 mt-3 flex w-[calc(100%-24px)] items-start gap-3 rounded-2xl border border-zinc-700/90 bg-zinc-950/95 p-3 text-left shadow-[0_24px_80px_rgba(0,0,0,0.55)] backdrop-blur transition hover:border-zinc-500")}
        >
          <span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border", statusTone(toastItem.status))}>
            <StatusIcon status={toastItem.status} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">通知</span>
            <span className="mt-1 block truncate text-sm font-semibold text-zinc-100">{toastItem.title}</span>
            <span className="mt-0.5 block truncate text-xs text-zinc-400">{toastItem.summary}</span>
          </span>
          <ExternalLink size={14} className="mt-1 shrink-0 text-zinc-500" />
        </button>
      )}

      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-zinc-800/70 px-4 py-2">
        {filterOptions.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setFilter(option.id)}
            className={cn(
              "whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-medium transition",
              filter === option.id
                ? "border-zinc-400 bg-zinc-100 text-zinc-950"
                : "border-zinc-800 bg-zinc-950/65 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
            )}
          >
            {option.label}
            <span className="ml-1 opacity-60">{option.count}</span>
          </button>
        ))}
      </div>

      {showSearch && (
        <div className="border-b border-zinc-800/70 px-4 py-2">
          <label className="relative block">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="タイトル・内容・toolで検索"
              className="h-9 w-full rounded-xl border border-zinc-800 bg-zinc-950 pl-9 pr-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-500"
            />
          </label>
        </div>
      )}

      {error && (
        <div className="mx-4 mt-3 rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-100">
          {error}
        </div>
      )}

      <div className="max-h-[460px] overflow-y-auto p-2">
        {loading && visibleItems.length === 0 ? (
          <div className="flex h-36 items-center justify-center text-sm text-zinc-500">
            通知を読み込んでいます…
          </div>
        ) : visibleItems.length === 0 ? (
          <div className="flex h-36 flex-col items-center justify-center gap-2 text-center text-sm text-zinc-500">
            <Inbox size={26} className="text-zinc-700" />
            <div>
              <p className="font-medium text-zinc-400">いま見るべき通知はありません</p>
              <p className="mt-1 text-xs text-zinc-600">完了・回答待ち・失敗が出たらここに残ります。</p>
            </div>
          </div>
        ) : (
          <div className="grid gap-1.5">
            {visibleItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => openItem(item)}
                className={cn(
                  "group flex min-w-0 items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition hover:border-zinc-700 hover:bg-zinc-900/70",
                  item.unread ? "border-zinc-700 bg-zinc-900/55" : "border-zinc-800/80 bg-[#0c0d10]",
                )}
              >
                <span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border", statusTone(item.status))}>
                  <StatusIcon status={item.status} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-center gap-2">
                    {item.unread && <span className="h-2 w-2 shrink-0 rounded-full bg-amber-300" aria-label="未読" />}
                    <span className="truncate text-sm font-semibold text-zinc-100">{item.title}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-xs leading-5 text-zinc-400">{item.summary}</span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className={cn("rounded-full border px-1.5 py-px text-[10px] font-medium", statusTone(item.status))}>
                      {STATUS_LABELS[item.status]}
                    </span>
                    <span className="rounded-full border border-zinc-800 bg-zinc-950 px-1.5 py-px text-[10px] text-zinc-500">
                      {item.source}
                    </span>
                    {item.toolNames[0] && (
                      <span className="rounded-full border border-zinc-800 bg-zinc-950 px-1.5 py-px text-[10px] text-zinc-500">
                        {item.toolNames[0]}
                      </span>
                    )}
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-2 pt-0.5">
                  <span className="text-[11px] text-zinc-600">{formatRelativeTime(item.updatedAt)}</span>
                  <span className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 px-2 py-1 text-[11px] font-medium text-zinc-500 transition group-hover:border-zinc-600 group-hover:text-zinc-100">
                    開く
                    <ExternalLink size={11} />
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
