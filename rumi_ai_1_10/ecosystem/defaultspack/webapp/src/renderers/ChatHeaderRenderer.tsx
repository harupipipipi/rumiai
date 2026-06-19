import { Copy, Hash } from "lucide-react";

import type { ChatHeaderRendererProps } from "./types";

export function ChatHeaderRenderer({
  conversationId,
  onCopyChatId,
  title,
}: ChatHeaderRendererProps) {
  return (
    <header className="h-11 flex items-center px-4 border-b border-zinc-800/60 justify-between bg-[#09090b]/80 backdrop-blur-md rumi-layer-panel flex-shrink-0 rumi-anim-fade-down">
      <div className="flex items-center gap-2 min-w-0">
        <Hash size={14} className="text-zinc-600 flex-shrink-0" />
        <h2 className="text-zinc-200 font-medium text-sm truncate">{title}</h2>
      </div>
      {conversationId && onCopyChatId && (
        <button
          type="button"
          onClick={onCopyChatId}
          className="ml-3 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
          title="Copy chatid"
          aria-label="Copy chatid"
        >
          <Copy size={13} />
        </button>
      )}
    </header>
  );
}
