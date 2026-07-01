import { Hash } from "lucide-react";

import { AgentStackPicker } from "../components/AgentStackPicker";
import type { ChatHeaderRendererProps } from "./types";

export function ChatHeaderRenderer({
  title,
  agentStack,
  canOpenSettings,
  canShowPreview,
  onOpenSettings,
  onTogglePreview,
  showPreview,
}: ChatHeaderRendererProps) {
  return (
    <header className="h-11 flex items-center px-4 border-b border-zinc-800/60 justify-between bg-[#09090b]/80 backdrop-blur-md rumi-layer-panel flex-shrink-0 rumi-anim-fade-down">
      <div className="flex items-center gap-2 min-w-0">
        <Hash size={14} className="text-zinc-600 flex-shrink-0" />
        <h2 className="text-zinc-200 font-medium text-sm truncate">{title}</h2>
      </div>
      {agentStack ? (
        <AgentStackPicker
          controls={agentStack}
          canOpenSettings={canOpenSettings}
          canShowPreview={canShowPreview}
          showPreview={showPreview}
          onOpenSettings={onOpenSettings}
          onTogglePreview={onTogglePreview}
        />
      ) : null}
    </header>
  );
}
