import { Hash, MoreHorizontal, PanelRightClose, PanelRightOpen, Settings } from "lucide-react";

import { cn } from "../lib/cn";
import type { ChatHeaderRendererProps } from "./types";

export function ChatHeaderRenderer({
  title,
  showPreview,
  canShowPreview,
  canOpenSettings,
  onTogglePreview,
  onOpenSettings,
}: ChatHeaderRendererProps) {
  return (
    <header className="h-11 flex items-center px-4 border-b border-zinc-800/60 justify-between bg-[#09090b]/80 backdrop-blur-md z-10 flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <Hash size={14} className="text-zinc-600 flex-shrink-0" />
        <h2 className="text-zinc-200 font-medium text-sm truncate">{title}</h2>
      </div>
      <div className="flex items-center gap-1">
        {canShowPreview && (
          <button
            onClick={onTogglePreview}
            className={cn(
              "p-1.5 rounded-md transition-colors",
              showPreview ? "text-zinc-200 bg-zinc-800" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800",
            )}
            title={showPreview ? "Hide preview" : "Show preview"}
          >
            {showPreview ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
          </button>
        )}
        {canOpenSettings && (
          <button onClick={onOpenSettings} className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors">
            <Settings size={14} />
          </button>
        )}
        <button className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded-md transition-colors">
          <MoreHorizontal size={14} />
        </button>
      </div>
    </header>
  );
}
