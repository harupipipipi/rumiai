import { useState } from "react";
import { ChevronUp, ExternalLink, Loader2, MessageSquare, RefreshCcw, Search, ShieldCheck, X } from "lucide-react";

import { HistoryBoard, type ChatItem } from "../components/HistoryBoard";
import type { ModelSearchItem } from "../lib/api";
import { cn } from "../lib/cn";
import type { AmbientRoutingMode } from "./ambientTriggerClient";
import { modelIdForSearchItem, modelLabelForSearchItem, modelLabelFromId } from "./ambientRouting";

export function RoutingSettings({
  busy,
  mode,
  summary,
  selectedConversationId,
  groupEnabled,
  groupId,
  groupTitle,
  model,
  modelQuery,
  modelResults,
  modelLoading,
  needsNewChatSettings,
  aiSendApprovalRequired,
  onModeChange,
  onPickChat,
  onGroupEnabledChange,
  onGroupIdChange,
  onGroupTitleChange,
  onGroupCommit,
  onModelChange,
  onModelCommit,
  onModelQueryChange,
  onModelSearch,
  onAiSendApprovalRequiredChange,
}: {
  busy: boolean;
  mode: AmbientRoutingMode;
  summary: string;
  selectedConversationId: string | null;
  groupEnabled: boolean;
  groupId: string;
  groupTitle: string;
  model: string;
  modelQuery: string;
  modelResults: ModelSearchItem[];
  modelLoading: boolean;
  needsNewChatSettings: boolean;
  aiSendApprovalRequired: boolean;
  onModeChange: (mode: AmbientRoutingMode) => void;
  onPickChat: () => void;
  onGroupEnabledChange: (enabled: boolean) => void;
  onGroupIdChange: (value: string) => void;
  onGroupTitleChange: (value: string) => void;
  onGroupCommit: () => void;
  onModelChange: (value: string) => void;
  onModelCommit: (model: string) => void;
  onModelQueryChange: (value: string) => void;
  onModelSearch: () => void;
  onAiSendApprovalRequiredChange: (enabled: boolean) => void;
}) {
  const [modelChangeOpen, setModelChangeOpen] = useState(false);
  const modelLabel = model ? modelLabelFromId(model) : "未指定";

  return (
    <section className="space-y-2 border-l border-sky-400/35 pl-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase text-zinc-500">話す先</span>
        <span className="min-w-0 truncate text-[11px] text-zinc-300">{summary}</span>
      </div>
      <div className="grid grid-cols-3 gap-1">
        <RouteModeButton label="選ぶ" active={mode === "selected_chat"} disabled={busy} onClick={() => onModeChange("selected_chat")} />
        <RouteModeButton label="起動ごと" active={mode === "startup_new_chat"} disabled={busy} onClick={() => onModeChange("startup_new_chat")} />
        <RouteModeButton label="毎回新規" active={mode === "always_new_chat"} disabled={busy} onClick={() => onModeChange("always_new_chat")} />
      </div>
      {mode === "selected_chat" && (
        <button type="button" onClick={onPickChat} disabled={busy} className="ambient-mini-button w-full justify-between">
          <span className="inline-flex min-w-0 items-center gap-2">
            <MessageSquare size={14} />
            <span className="truncate">{selectedConversationId ? "チャットを変更" : "チャットを選ぶ"}</span>
          </span>
          <ChevronUp size={13} className="rotate-90 text-zinc-500" />
        </button>
      )}
      {needsNewChatSettings && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => onGroupEnabledChange(!groupEnabled)}
            disabled={busy}
            className={cn(
              "flex h-8 w-full items-center justify-between rounded-md border px-2 text-[11px] transition",
              groupEnabled
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
                : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
            )}
          >
            <span>グループ内に作成</span>
            <span className="font-semibold">{groupEnabled ? "有効" : "無効"}</span>
          </button>
          {groupEnabled && (
            <div className="grid grid-cols-[0.75fr_1fr] gap-1.5">
              <label className="block text-[10px] text-zinc-500">
                グループID
                <input
                  value={groupId}
                  onChange={(event) => onGroupIdChange(event.target.value)}
                  onBlur={onGroupCommit}
                  className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                />
              </label>
              <label className="block text-[10px] text-zinc-500">
                表示名
                <input
                  value={groupTitle}
                  onChange={(event) => onGroupTitleChange(event.target.value)}
                  onBlur={onGroupCommit}
                  className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                />
              </label>
            </div>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={() => onAiSendApprovalRequiredChange(!aiSendApprovalRequired)}
        disabled={busy}
        className={cn(
          "flex h-8 w-full items-center justify-between rounded-md border px-2 text-[11px] transition",
          aiSendApprovalRequired
            ? "border-amber-300/35 bg-amber-400/10 text-amber-50"
            : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
        )}
      >
        <span className="inline-flex min-w-0 items-center gap-2">
          <ShieldCheck size={13} />
          <span className="truncate">AI送信前に確認</span>
        </span>
        <span className="shrink-0 font-semibold">{aiSendApprovalRequired ? "有効" : "無効"}</span>
      </button>
      <div className="space-y-1.5 rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold text-zinc-500">送信モデル</span>
          {model && (
            <span className="min-w-0 truncate rounded border border-emerald-400/25 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] text-emerald-100" title={model}>
              モデル: {modelLabel}
            </span>
          )}
        </div>
        {!modelChangeOpen && (
          <button
            type="button"
            onClick={() => {
              setModelChangeOpen(true);
              onModelQueryChange("");
            }}
            disabled={busy}
            className="ambient-mini-button w-full justify-between"
          >
            <span>{model ? "変更" : "モデルを選ぶ"}</span>
            <Search size={13} />
          </button>
        )}
        {modelChangeOpen && (
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              <input
                value={modelQuery}
                onChange={(event) => onModelQueryChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onModelSearch();
                  }
                  if (event.key === "Escape") {
                    setModelChangeOpen(false);
                  }
                }}
                placeholder="すべてから探す"
                className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
                autoFocus
              />
              <button type="button" onClick={onModelSearch} disabled={modelLoading} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
                {modelLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
              </button>
              <button type="button" onClick={() => setModelChangeOpen(false)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
                <X size={13} />
              </button>
            </div>
            {model && (
              <button
                type="button"
                onClick={() => {
                  onModelCommit("");
                  setModelChangeOpen(false);
                }}
                className="text-[11px] text-zinc-400 hover:text-zinc-100"
              >
                モデル指定を外す
              </button>
            )}
            {modelResults.length > 0 && (
              <div className="max-h-28 overflow-auto border-l border-zinc-800 pl-2">
                {modelResults
                  .map((item) => ({ item, id: modelIdForSearchItem(item) }))
                  .filter(({ id }) => Boolean(id))
                  .slice(0, 6)
                  .map(({ item, id }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => {
                        onModelChange(id);
                        onModelCommit(id);
                        onModelQueryChange("");
                        setModelChangeOpen(false);
                      }}
                      className="block w-full truncate py-1 text-left text-[11px] text-zinc-300 hover:text-zinc-50"
                    >
                      {modelLabelForSearchItem(item)}
                    </button>
                  ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export function CompactRoutingControl({
  busy,
  mode,
  summary,
  selectedConversationId,
  sessionConversationId,
  model,
  modelQuery,
  modelResults,
  modelLoading,
  onModeChange,
  onPickChat,
  onModelChange,
  onModelCommit,
  onModelQueryChange,
  onModelSearch,
}: {
  busy: boolean;
  mode: AmbientRoutingMode;
  summary: string;
  selectedConversationId: string | null;
  sessionConversationId?: string | null;
  model: string;
  modelQuery: string;
  modelResults: ModelSearchItem[];
  modelLoading: boolean;
  onModeChange: (mode: AmbientRoutingMode) => void;
  onPickChat: () => void;
  onModelChange: (value: string) => void;
  onModelCommit: (model: string) => void;
  onModelQueryChange: (value: string) => void;
  onModelSearch: (query?: string) => void;
}) {
  const [modelChangeOpen, setModelChangeOpen] = useState(false);
  const modelLabel = model ? modelLabelFromId(model) : "モデル指定なし";
  const concreteChatId = mode === "selected_chat" ? selectedConversationId : mode === "startup_new_chat" ? sessionConversationId ?? null : null;
  const createsNewChat = mode === "startup_new_chat" || mode === "always_new_chat";

  function openConcreteChat() {
    if (!concreteChatId) return;
    const url = new URL("/chat", window.location.origin);
    url.searchParams.set("chat", concreteChatId);
    window.location.assign(url.toString());
  }

  return (
    <section className="space-y-2 border-t border-zinc-800/75 pt-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Defaultspack</span>
        <span className="min-w-0 truncate text-[11px] text-zinc-400">送信先</span>
      </div>
      <div className="grid grid-cols-3 rounded-md border border-zinc-800 bg-zinc-950 p-0.5">
        <SegmentedRouteModeButton label="選ぶ" active={mode === "selected_chat"} disabled={busy} onClick={() => onModeChange("selected_chat")} />
        <SegmentedRouteModeButton label="起動ごと" active={mode === "startup_new_chat"} disabled={busy} onClick={() => onModeChange("startup_new_chat")} />
        <SegmentedRouteModeButton label="毎回新規" active={mode === "always_new_chat"} disabled={busy} onClick={() => onModeChange("always_new_chat")} />
      </div>

      <div className="flex min-w-0 items-center gap-1.5 text-[11px]">
        <span className="inline-flex min-w-0 flex-1 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950/75 px-2 py-1.5 text-zinc-200">
          <MessageSquare size={13} className="shrink-0 text-zinc-500" />
          <span className="truncate">{summary}</span>
        </span>
        {concreteChatId ? (
          <button type="button" onClick={openConcreteChat} className="ambient-mini-button h-7 shrink-0 px-2" title={`/chat?chat=${concreteChatId}`}>
            <ExternalLink size={12} />
            開く
          </button>
        ) : createsNewChat ? (
          <span className="shrink-0 rounded-md border border-zinc-800 px-2 py-1.5 text-[10px] font-semibold text-zinc-400">次の送信で作成</span>
        ) : null}
        {mode === "selected_chat" && (
          <button type="button" onClick={onPickChat} disabled={busy} className="ambient-mini-button h-7 shrink-0 px-2">
            {selectedConversationId ? "変更" : "選択"}
          </button>
        )}
      </div>

      {!modelChangeOpen && (
        <button
          type="button"
          onClick={() => {
            setModelChangeOpen(true);
            onModelQueryChange("");
          }}
          disabled={busy}
          className={cn(
            "inline-flex h-7 max-w-full items-center gap-1.5 rounded-md border px-2 text-[11px] font-semibold transition",
            model
              ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100"
              : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
          )}
          title={model || modelLabel}
        >
          <Search size={12} className="shrink-0" />
          <span className="truncate">{modelLabel}</span>
        </button>
      )}

      {modelChangeOpen && (
        <div className="space-y-1.5">
          <div className="flex gap-1.5">
            <input
              value={modelQuery}
              onChange={(event) => onModelQueryChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onModelSearch(modelQuery);
                }
                if (event.key === "Escape") {
                  setModelChangeOpen(false);
                }
              }}
              placeholder="モデルを探す"
              className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200"
              autoFocus
            />
            <button type="button" onClick={() => onModelSearch(modelQuery)} disabled={modelLoading} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
              {modelLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            </button>
            <button type="button" onClick={() => setModelChangeOpen(false)} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
              <X size={13} />
            </button>
          </div>
          <div className="flex items-center justify-between gap-2 text-[11px]">
            {model ? (
              <button
                type="button"
                onClick={() => {
                  onModelCommit("");
                  setModelChangeOpen(false);
                }}
                className="text-zinc-400 hover:text-zinc-100"
              >
                指定を外す
              </button>
            ) : (
              <span className="text-zinc-500">未指定ならDefaultspackの通常設定を使います。</span>
            )}
          </div>
          {modelResults.length > 0 && (
            <div className="max-h-24 overflow-auto border-l border-zinc-800 pl-2">
              {modelResults
                .map((item) => ({ item, id: modelIdForSearchItem(item) }))
                .filter(({ id }) => Boolean(id))
                .slice(0, 6)
                .map(({ item, id }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => {
                      onModelChange(id);
                      onModelCommit(id);
                      onModelQueryChange("");
                      setModelChangeOpen(false);
                    }}
                    className="block w-full truncate py-1 text-left text-[11px] text-zinc-300 hover:text-zinc-50"
                  >
                    {modelLabelForSearchItem(item)}
                  </button>
                ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function ChatPickerDialog({
  activeChatId,
  selectedChatId,
  chatItems,
  loading,
  onRefresh,
  onSelect,
  onClose,
}: {
  activeChatId: string | null;
  selectedChatId: string | null;
  chatItems: ChatItem[];
  loading: boolean;
  onRefresh: () => void;
  onSelect: (chatId: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 rumi-layer-modal flex items-end justify-center bg-black/60 px-3 py-4 backdrop-blur-sm sm:items-center">
      <section className="flex h-[min(720px,calc(100vh-32px))] w-[min(390px,calc(100vw-24px))] flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl shadow-black/50">
        <header className="flex h-10 items-center gap-2 border-b border-zinc-800 px-3">
          <MessageSquare size={15} className="text-sky-200" />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">チャットを選ぶ</span>
          <button type="button" onClick={onRefresh} disabled={loading} className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCcw size={13} />}
          </button>
          <button type="button" onClick={onClose} className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100">
            <X size={13} />
          </button>
        </header>
        <div className="min-h-0 flex-1">
          <HistoryBoard
            activeChatId={activeChatId}
            selectedChatId={selectedChatId}
            selectionMode
            selectionLabel="送信先"
            chatItems={chatItems}
            onChatSelect={onSelect}
            onNewTask={() => undefined}
            onSettingsClick={() => undefined}
            isCompact
          />
        </div>
      </section>
    </div>
  );
}

function RouteModeButton({ label, active, disabled, onClick }: { label: string; active: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-8 rounded-md border px-2 text-[11px] font-medium transition",
        active
          ? "border-sky-300/35 bg-sky-400/15 text-sky-100"
          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
      )}
    >
      {label}
    </button>
  );
}

function SegmentedRouteModeButton({ label, active, disabled, onClick }: { label: string; active: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-7 min-w-0 rounded px-1.5 text-[11px] font-semibold transition",
        active
          ? "bg-zinc-100 text-zinc-950"
          : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100",
      )}
    >
      <span className="block truncate">{label}</span>
    </button>
  );
}
