import { AlertTriangle, Check, CheckCircle2, ChevronDown, Clock, Copy, Image as ImageIcon, Loader2, Pencil } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { cn } from "../lib/cn";
import { buildToolActivityGroups, toolFolderFor, type ToolActivityItem } from "../lib/toolActivity";
import type { ChatContentBlock } from "../lib/api";
import type { ChatMessagesRendererProps } from "./types";

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

  if (blockType === "image" || blockType === "image_url") {
    const imageUrl = block.image_url;
    const url = String(
      block.url
      ?? (typeof imageUrl === "object" && imageUrl !== null && "url" in imageUrl ? imageUrl.url : "")
      ?? "",
    );
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

function messageVisibleText(message: ChatMessagesRendererProps["messages"][number]): string {
  const blockText = message.content
    .map((block) => {
      if (String(block.type ?? "text") === "text" || String(block.type ?? "") === "markdown") {
        return String(block.text ?? "");
      }
      return "";
    })
    .join("")
    .trim();
  return blockText || String(message.rawText ?? "").trim();
}

export function messageCopyText(message: ChatMessagesRendererProps["messages"][number]): string {
  const blockText = message.content
    .map((block) => {
      const blockType = String(block.type ?? "text");
      if (blockType === "text" || blockType === "markdown" || blockType === "code") {
        return String(block.text ?? "");
      }
      if (blockType === "image" || blockType === "image_url") {
        const imageUrl = block.image_url;
        const url = String(
          block.url
          ?? (typeof imageUrl === "object" && imageUrl !== null && "url" in imageUrl ? imageUrl.url : "")
          ?? "",
        );
        return url;
      }
      return "";
    })
    .filter((text) => text.trim().length > 0)
    .join("\n\n")
    .trim();
  return blockText || String(message.rawText ?? "").trim();
}

async function writeClipboardText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function MessageActionBar({
  message,
  onEdit,
}: {
  message: ChatMessagesRendererProps["messages"][number];
  onEdit?: (text: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  const text = messageCopyText(message);
  const actions: Array<{
    id: string;
    label: string;
    icon: typeof Copy;
    run: () => Promise<void> | void;
  }> = [
    {
      id: "copy",
      label: copied ? "コピー済み" : "コピー",
      icon: copied ? Check : Copy,
      run: async () => {
        if (!text) return;
        await writeClipboardText(text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      },
    },
  ];

  if (message.role === "user" && onEdit && text) {
    actions.push({
      id: "edit",
      label: "編集",
      icon: Pencil,
      run: () => onEdit(text),
    });
  }

  return (
    <div className="rumi-message-actions mt-1.5 flex min-h-6 items-center justify-start gap-1 opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100">
      {actions.map((action) => {
        const Icon = action.icon;
        return (
          <button
            key={action.id}
            type="button"
            aria-label={action.label}
            title={action.label}
            onClick={() => {
              void action.run();
            }}
            className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800/85 hover:text-zinc-100 focus-visible:bg-zinc-800/85 focus-visible:text-zinc-100 focus-visible:outline-none"
          >
            <Icon size={14} />
          </button>
        );
      })}
    </div>
  );
}

function WidgetCard({ widget }: { widget: Record<string, unknown> }) {
  return (
    <details className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3">
      <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-blue-300">
        Widget details
      </summary>
      <pre className="mt-2 overflow-x-auto text-[11px] font-mono text-zinc-200">{JSON.stringify(widget, null, 2)}</pre>
    </details>
  );
}

function ToolStatusIcon({ item }: { item: ToolActivityItem }) {
  if (item.status === "running") return <Loader2 size={12} className="shrink-0 animate-spin text-blue-300" />;
  if (item.status === "failed") return <AlertTriangle size={12} className="shrink-0 text-red-300" />;
  return <CheckCircle2 size={12} className="shrink-0 text-zinc-400" />;
}

function toolStatusLabel(item: ToolActivityItem): string {
  if (item.status === "running") return "実行中";
  if (item.status === "failed") return "失敗";
  return "完了";
}

function isJsonLikeDetail(value: string): boolean {
  const trimmed = value.trim();
  return (
    (trimmed.startsWith("{") && trimmed.endsWith("}"))
    || (trimmed.startsWith("[") && trimmed.endsWith("]"))
  );
}

function ToolResultDetail({ detail }: { detail: string }) {
  if (isJsonLikeDetail(detail)) {
    return (
      <details className="min-w-0 flex-1 text-[12px] leading-relaxed">
        <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">
          詳細データ
        </summary>
        <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono text-[11px] text-zinc-500">
          {detail}
        </pre>
      </details>
    );
  }

  return <span className="min-w-0 break-words text-[12px] leading-relaxed">{detail}</span>;
}

function ToolActivityTray({ message }: { message: ChatMessagesRendererProps["messages"][number] }) {
  const groups = buildToolActivityGroups(message.toolLogs ?? [], message.events ?? []);
  if (groups.length === 0) return null;
  const items = groups.flatMap((group) => group.items);
  const total = items.length;

  return (
    <details className="rumi-tool-activity mb-4 w-full rounded-xl border border-zinc-800/90 bg-zinc-950/70 px-4 py-3 text-zinc-300 shadow-[0_16px_44px_rgba(0,0,0,0.22)]" open>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[13px] text-zinc-300">
        <span className="flex min-w-0 items-center gap-2 font-medium">
          <span className="truncate">使用した tool</span>
          <span className="rounded-full border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">{total}</span>
        </span>
        <ChevronDown size={16} className="rumi-tool-caret shrink-0 text-zinc-500" />
      </summary>
      <div className="mt-3 grid gap-2">
        {items.map((item) => (
          <div key={item.id} className="rumi-tool-card rounded-lg border border-zinc-800/80 bg-zinc-900/55 px-3.5 py-3">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-2.5">
                <span className="mt-0.5">
                  <ToolStatusIcon item={item} />
                </span>
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded-md border border-zinc-800 bg-zinc-950/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                      {item.folderLabel}
                    </span>
                    <span className="min-w-0 truncate font-mono text-[12px] text-zinc-200">{item.toolName}</span>
                  </div>
                  {item.input && (
                    <div className="mt-1 flex min-w-0 items-center gap-1.5 text-[10px] leading-4 text-zinc-600">
                      <span className="shrink-0 text-zinc-700">入力</span>
                      <span className="min-w-0 truncate font-mono">{item.input}</span>
                    </div>
                  )}
                </div>
              </div>
              <span className="shrink-0 rounded-full border border-zinc-800 bg-zinc-950/70 px-2 py-0.5 text-[10px] text-zinc-500">
                {toolStatusLabel(item)}
              </span>
            </div>
            {item.detail && (
              <div className="mt-2 flex min-w-0 items-start gap-2 rounded-md border border-zinc-800/70 bg-black/20 px-3 py-2 text-zinc-300">
                <span className="shrink-0 text-[10px] font-medium text-zinc-600">結果</span>
                <ToolResultDetail detail={item.detail} />
              </div>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function PendingToolTray({ toolNames }: { toolNames: string[] }) {
  if (toolNames.length === 0) return null;
  const groups = new Map<string, { label: string; names: string[] }>();
  for (const name of toolNames) {
    const folder = toolFolderFor(name);
    const existing = groups.get(folder.id);
    if (existing) {
      existing.names.push(name);
    } else {
      groups.set(folder.id, { label: folder.label, names: [name] });
    }
  }

  return (
    <div className="mt-2 ml-5 w-[min(820px,calc(100vw-64px))] rounded-xl border border-zinc-800 bg-zinc-950/70 px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-zinc-400">
        <Loader2 size={12} className="animate-spin text-blue-300" />
        <span>接続中の tool</span>
      </div>
      <div className="space-y-2">
        {[...groups.entries()].map(([id, group]) => (
          <div key={id} className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
              <ChevronDown size={11} className="rotate-180" />
              <span>{group.label}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {group.names.map((name) => (
                <span key={name} className="max-w-[220px] truncate rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-[11px] text-zinc-300">
                  {name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChatMessagesRenderer({
  error,
  isMessagesRegionVisible,
  isLoading,
  isNewConversation,
  isGenerating,
  pendingStatus,
  pendingToolNames = [],
  messages,
  messagesEndRef,
  unknownBlockStrategy,
  showActivityInMessages,
  showWidgets,
  onSuggestionClick,
}: ChatMessagesRendererProps) {
  return (
    <>
      {error && <div className="mx-4 mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</div>}

      {!isMessagesRegionVisible ? null : isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={18} className="animate-spin text-zinc-500" />
        </div>
      ) : isNewConversation ? (
        <div className="flex-1" />
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <div className="w-full max-w-5xl mx-auto space-y-4">
            {messages.map((message) => (
              <div key={message.id} className={cn("rumi-message-row group/message flex gap-3", message.role === "user" ? "flex-row-reverse" : "")}>
                <div className={cn("flex flex-col min-w-0 pt-1", message.role === "user" ? "items-end max-w-[80%]" : "items-start flex-1")}>
                  {message.role === "agent" && (
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-zinc-300 tracking-wide">Rumi</span>
                      {message.metadata?.executionTime && (
                        <span className="text-[10px] text-zinc-500 font-mono flex items-center gap-1">
                          <Clock size={10} /> {message.metadata.executionTime}
                        </span>
                      )}
                    </div>
                  )}

                  <div className={cn("flex max-w-full flex-col", message.role === "user" ? "items-start" : "w-full items-start")}>
                    <div
                      tabIndex={0}
                      className={cn(
                        "relative rounded-2xl max-w-full sm:px-4 px-3 py-3 text-[14px] outline-none",
                        message.role === "user"
                          ? "bg-zinc-800/80 text-zinc-100 rounded-tr-sm shadow-sm border border-zinc-700/50"
                          : "w-full text-zinc-200 bg-transparent",
                      )}
                    >
                      {showActivityInMessages && message.role === "agent" && <ToolActivityTray message={message} />}

                      {message.role === "agent" && message.metadata?.thinkingTranscript && (
                        <details className="mb-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-400">
                          <summary className="cursor-pointer select-none text-[11px] font-medium text-zinc-300">
                            Thinking
                          </summary>
                          <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-zinc-400">
                            {message.metadata.thinkingTranscript}
                          </pre>
                        </details>
                      )}

                      <div className="markdown-body select-text leading-relaxed break-words space-y-4">
                        {message.content.length > 0 && (messageVisibleText(message) || message.content.some((block) => String(block.type ?? "text") !== "text"))
                          ? message.content.map((block, index) => (
                              <MessageBlock key={`${message.id}-${index}`} block={block} unknownStrategy={unknownBlockStrategy} />
                            ))
                          : message.role === "agent" && !messageVisibleText(message)
                            ? (
                                <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[12px] leading-relaxed text-amber-100">
                                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-300" />
                                  <span>レスポンス本文が空でした。stream が途中で閉じたか、thinking のみで終了した可能性があります。</span>
                                </div>
                              )
                            : <ReactMarkdown>{message.rawText}</ReactMarkdown>}
                      </div>

                      {showWidgets && message.widget && <WidgetCard widget={message.widget} />}
                    </div>

                    <MessageActionBar message={message} onEdit={onSuggestionClick} />
                  </div>
                </div>
              </div>
            ))}

            {isGenerating && (
              <div className="flex gap-3">
                <div className="text-zinc-400 text-[13px] flex flex-col gap-1 mt-1.5">
                  <div className="flex items-center gap-2">
                    <Loader2 size={14} className="text-zinc-400 animate-spin" />
                    <span className="animate-pulse">{pendingStatus || "Processing..."}</span>
                  </div>
                  {pendingToolNames.length > 0 && (
                    <PendingToolTray toolNames={pendingToolNames} />
                  )}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} className="h-1" />
          </div>
        </div>
      )}
    </>
  );
}
