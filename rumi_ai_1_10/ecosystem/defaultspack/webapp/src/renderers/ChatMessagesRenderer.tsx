import { AlertTriangle, CheckCircle2, ChevronDown, Clock, Image as ImageIcon, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { cn } from "../lib/cn";
import { buildToolActivityGroups, toolFolderFor, type ToolActivityItem } from "../lib/toolActivity";
import { extractToolVisual, type ToolVisualImage } from "../lib/toolVisuals";
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

function ToolVisualPreview({ visual }: { visual: ToolVisualImage }) {
  const hasPoints = visual.points.length > 0;
  const title = visual.kind === "zoom" ? "Zoom crop" : "Screenshot";
  const imageClass = hasPoints
    ? "block max-h-[240px] max-w-full rounded-md border border-zinc-800 object-contain"
    : "block max-h-[150px] max-w-full rounded-md border border-zinc-800 object-contain opacity-90";

  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-zinc-800/80 bg-zinc-950/80">
      <div className="flex min-w-0 items-center justify-between gap-3 border-b border-zinc-800/70 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2 text-[11px] font-medium text-zinc-300">
          <ImageIcon size={12} className="shrink-0 text-blue-300" />
          <span>{hasPoints ? "Click feedback" : title}</span>
        </div>
        <span className="min-w-0 truncate font-mono text-[10px] text-zinc-600">{visual.sourceLabel}</span>
      </div>
      <div className="p-2 text-center">
        <div className="relative inline-block max-w-full overflow-hidden rounded-md bg-black/40 align-top">
          <img src={visual.src} alt={title} className={imageClass} />
          {visual.points.map((point) => (
            <span
              key={point.id}
              title={point.label}
              className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,0.42)]"
              style={{ left: `${point.xPercent}%`, top: `${point.yPercent}%` }}
            />
          ))}
        </div>
      </div>
      {(visual.cropBounds || visual.imageSize) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-zinc-800/70 px-3 py-2 font-mono text-[10px] text-zinc-500">
          {visual.imageSize && <span>{visual.imageSize.width}x{visual.imageSize.height}</span>}
          {visual.cropBounds && <span>crop {JSON.stringify(visual.cropBounds)}</span>}
        </div>
      )}
    </div>
  );
}

function WidgetCard({ widget }: { widget: Record<string, unknown> }) {
  const visual = extractToolVisual(widget);
  return (
    <details className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3" open={Boolean(visual)}>
      <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-blue-300">
        Widget details
      </summary>
      {visual && (
        <div className="mt-2">
          <ToolVisualPreview visual={visual} />
        </div>
      )}
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

function parseJsonDetail(detail: string): unknown | null {
  if (!isJsonLikeDetail(detail)) return null;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function ToolResultDetail({ detail, result }: { detail: string; result?: unknown }) {
  const parsedDetail = typeof detail === "string" ? parseJsonDetail(detail) : null;
  const visual = extractToolVisual(result) ?? extractToolVisual(parsedDetail);

  if (isJsonLikeDetail(detail)) {
    return (
      <div className="min-w-0 flex-1 space-y-2">
        {visual && <ToolVisualPreview visual={visual} />}
        <details className="text-[12px] leading-relaxed" open={!visual}>
          <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">
            詳細データ
          </summary>
          <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono text-[11px] text-zinc-500">
            {detail}
          </pre>
        </details>
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1 break-words text-[12px] leading-relaxed">
      {visual && (
        <div className="mb-2">
          <ToolVisualPreview visual={visual} />
        </div>
      )}
      {detail}
    </div>
  );
}

function ToolResultPanel({ item }: { item: ToolActivityItem }) {
  const visual = extractToolVisual(item.result);
  if (!item.detail && !visual) return null;

  return (
    <div className="mt-2 min-w-0 rounded-md border border-zinc-800/70 bg-black/20 px-3 py-2 text-zinc-300">
      <span className="mb-1 block text-[10px] font-medium text-zinc-600">結果</span>
      <ToolResultDetail detail={item.detail} result={item.result} />
    </div>
  );
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
            <ToolResultPanel item={item} />
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
              <div key={message.id} className={cn("rumi-message-row flex gap-3", message.role === "user" ? "flex-row-reverse" : "")}>
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

                  <div className={cn(
                    "rounded-2xl max-w-full sm:px-4 px-3 py-3 text-[14px]", 
                    message.role === "user" 
                      ? "bg-zinc-800/80 text-zinc-100 rounded-tr-sm shadow-sm border border-zinc-700/50" 
                      : "w-full text-zinc-200 bg-transparent"
                  )}>
                    {showActivityInMessages && message.role === "agent" && <ToolActivityTray message={message} />}

                    <div className="markdown-body leading-relaxed break-words space-y-4">
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
