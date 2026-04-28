import { Loader2, Mic, Paperclip, Send } from "lucide-react";

import type { ComposerRendererProps } from "./types";

export function ComposerRenderer({
  input,
  placeholder,
  isGenerating,
  onInputChange,
  onSubmit,
}: ComposerRendererProps) {
  return (
    <div className="p-2.5 bg-[#09090b] flex-shrink-0">
      <div className="max-w-3xl mx-auto">
        <form onSubmit={onSubmit} className="relative flex flex-col bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden focus-within:border-zinc-700 transition-colors">
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder={placeholder}
            disabled={isGenerating}
            className="w-full bg-transparent border-none outline-none text-zinc-100 px-3.5 py-2.5 text-[13px] resize-none min-h-[44px] max-h-[160px] placeholder:text-zinc-600 disabled:opacity-50"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit(event);
              }
            }}
          />
          <div className="flex items-center justify-between px-2.5 py-1 border-t border-zinc-800/50">
            <div className="flex items-center gap-0.5">
              <button type="button" disabled={isGenerating} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors disabled:opacity-50">
                <Paperclip size={14} />
              </button>
              <button type="button" disabled={isGenerating} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors disabled:opacity-50">
                <Mic size={14} />
              </button>
            </div>
            <button type="submit" disabled={!input.trim() || isGenerating} className="flex items-center justify-center w-7 h-7 bg-white text-black rounded-md disabled:opacity-20 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors">
              {isGenerating ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
