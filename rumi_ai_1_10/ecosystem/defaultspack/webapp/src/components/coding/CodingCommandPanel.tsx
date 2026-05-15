import { GitBranch, GitCompare, Play, SearchCode } from "lucide-react";

import type { ComposerCommandItem } from "../../lib/api";

const FALLBACKS = [
  { key: "diff", label: "Diff", icon: GitCompare },
  { key: "review", label: "Review", icon: SearchCode },
  { key: "test", label: "Test", icon: Play },
  { key: "branch", label: "Branch", icon: GitBranch },
] as const;

export function CodingCommandPanel({
  commands = [],
  disabled = false,
  onRunCommand,
}: {
  commands?: ComposerCommandItem[];
  disabled?: boolean;
  onRunCommand?: (commandId: string, rawInput?: string) => void;
}) {
  const codingCommands = commands
    .filter((command) => command.category === "coding")
    .slice(0, 4);
  const items = codingCommands.length
    ? codingCommands.map((command) => ({ key: command.id, label: command.label || command.name, command }))
    : FALLBACKS.map((item) => ({ ...item, command: null }));

  return (
    <div className="inline-flex items-center gap-1">
      {items.map((item) => {
        const Icon = "icon" in item ? item.icon : Play;
        const commandId = item.command?.id ?? item.key;
        const rawInput = item.command ? `/${item.command.name || item.command.id}` : undefined;
        return (
          <button
            key={commandId}
            type="button"
            disabled={disabled || !onRunCommand}
            onClick={() => onRunCommand?.(commandId, rawInput)}
            className="inline-flex h-6 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-1.5 text-[11px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
            title={item.label}
          >
            <Icon size={11} />
            <span className="max-[640px]:hidden">{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
