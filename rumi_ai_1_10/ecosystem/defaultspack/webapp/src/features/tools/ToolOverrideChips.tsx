import { X } from "lucide-react";

import type { ToolTarget } from "./types";

export function ToolOverrideChips({
  targets,
  labelForTarget,
  onRemove,
}: {
  targets: ToolTarget[];
  labelForTarget: (target: ToolTarget) => string;
  onRemove: (target: ToolTarget) => void;
}) {
  if (!targets.length) return null;
  return (
    <div className="mx-4 flex max-w-full gap-1.5 overflow-x-auto pb-1 pt-1 max-[640px]:mx-2">
      {targets.map((target) => (
        <span
          key={`${target.kind}:${target.id}`}
          className="inline-flex h-7 flex-shrink-0 items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-900 px-2 text-[11px] text-zinc-300"
        >
          <span className="max-w-[160px] truncate">{labelForTarget(target)}</span>
          <span className="text-zinc-500">今回</span>
          <button
            type="button"
            aria-label={`${labelForTarget(target)} の今回指定を解除`}
            onClick={() => onRemove(target)}
            className="rounded-full p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <X size={12} />
          </button>
        </span>
      ))}
    </div>
  );
}
