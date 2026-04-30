import { Activity, Clock, FileText, Globe, Image as ImageIcon, Loader2, Sparkles, Terminal, Zap } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { cn } from "../lib/cn";
import type { ChatContentBlock } from "../lib/api";
import type { ChatMessagesRendererProps } from "./types";

function WelcomeScreen({ onSuggestionClick }: { onSuggestionClick: (text: string) => void }) {
  const suggestions = [
    { icon: <Terminal size={15} className="text-amber-400" />, label: "コード", text: "defaultspack の拡張ポイントを整理して" },
    { icon: <Globe size={15} className="text-emerald-400" />, label: "リサーチ", text: "この会話の context に何が注入されているか教えて" },
    { icon: <FileText size={15} className="text-violet-400" />, label: "ドキュメント", text: "frontend extension manifest のテンプレートを書いて" },
    { icon: <Sparkles size={15} className="text-blue-400" />, label: "設計", text: "非中央集権な UI registry の設計をまとめて" },
  ];

  return (
    <div className="flex-1 flex items-center justify-center px-5">
      <div className="max-w-md w-full text-center">
        <div className="mb-6">
          <div className="w-9 h-9 rounded-lg bg-white text-black flex items-center justify-center mx-auto mb-3">
            <Zap size={18} className="fill-black" />
          </div>
          <h1 className="text-xl font-semibold text-zinc-100 mb-1">何を作りましょうか？</h1>
          <p className="text-xs text-zinc-500">registry から拡張される chat shell</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.label}
              onClick={() => onSuggestionClick(suggestion.text)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 hover:border-zinc-700 transition-all text-xs text-zinc-400 hover:text-zinc-200"
            >
              {suggestion.icon}
              <span>{suggestion.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

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
        <WelcomeScreen onSuggestionClick={onSuggestionClick} />
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((message) => (
              <div key={message.id} className={cn("flex gap-2.5", message.role === "user" ? "flex-row-reverse" : "")}>
                {message.role === "agent" && (
                  <div className="flex-shrink-0 mt-1">
                    <div className="w-5 h-5 rounded bg-white text-black flex items-center justify-center">
                      <Zap size={10} className="fill-black" />
                    </div>
                  </div>
                )}

                <div className={cn("flex flex-col min-w-0", message.role === "user" ? "items-end max-w-[75%]" : "items-start flex-1")}>
                  {message.role === "agent" && (
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[10px] font-medium text-zinc-500">Rumi</span>
                      {message.metadata?.executionTime && (
                        <span className="text-[9px] text-zinc-600 font-mono flex items-center gap-0.5">
                          <Clock size={8} /> {message.metadata.executionTime}
                        </span>
                      )}
                    </div>
                  )}

                  <div className={cn("rounded-lg max-w-full", message.role === "user" ? "bg-zinc-800 text-zinc-100 px-3 py-2 rounded-tr-sm text-[13px]" : "text-zinc-300")}>
                    {message.role === "agent" && showActivityInMessages && message.metadata?.toolUsed && (
                      <div className="flex items-center gap-1 text-[10px] text-zinc-500 mb-1 font-mono">
                        <Activity size={9} />
                        <span>{message.metadata.toolUsed}</span>
                      </div>
                    )}

                    <div className="markdown-body text-[13px] leading-relaxed break-words space-y-3">
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
              <div className="flex gap-2.5">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-5 h-5 rounded bg-white text-black flex items-center justify-center">
                    <Zap size={10} className="fill-black" />
                  </div>
                </div>
                <div className="text-zinc-400 text-[13px] flex items-center gap-2">
                  <Loader2 size={12} className="animate-spin" />
                  Processing...
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
