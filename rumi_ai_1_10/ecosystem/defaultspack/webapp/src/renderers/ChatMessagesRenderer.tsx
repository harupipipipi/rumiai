import { Clock, Image as ImageIcon, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { cn } from "../lib/cn";
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
          <div className="max-w-3xl mx-auto space-y-4">
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
                      : "text-zinc-200 bg-transparent"
                  )}>
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
                    <div className="flex flex-wrap gap-1.5 pl-5">
                      {pendingToolNames.slice(0, 4).map((name) => (
                        <span key={name} className="rounded-full border border-zinc-800 bg-zinc-900/50 px-2 py-0.5 text-[10px] text-zinc-500">
                          {name}
                        </span>
                      ))}
                      {pendingToolNames.length > 4 && (
                        <span className="rounded-full border border-zinc-800 bg-zinc-900/50 px-2 py-0.5 text-[10px] text-zinc-500">
                          +{pendingToolNames.length - 4}
                        </span>
                      )}
                    </div>
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
