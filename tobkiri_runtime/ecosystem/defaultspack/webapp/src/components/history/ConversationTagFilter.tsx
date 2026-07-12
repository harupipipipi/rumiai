import { Tag, X } from "lucide-react";

export function ConversationTagFilter({
  tags,
  activeTag,
  onChange,
}: {
  tags: string[];
  activeTag: string | null;
  onChange: (tag: string | null) => void;
}) {
  if (tags.length === 0) return null;

  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      <Tag size={12} className="flex-shrink-0 text-zinc-600" />
      {tags.slice(0, 10).map((tag) => {
        const active = activeTag === tag;
        return (
          <button
            key={tag}
            type="button"
            onClick={() => onChange(active ? null : tag)}
            className={`h-6 flex-shrink-0 rounded-md border px-1.5 text-[10px] transition-colors ${
              active
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                : "border-zinc-800 bg-zinc-950/50 text-zinc-500 hover:text-zinc-300"
            }`}
            title={`Filter tag: ${tag}`}
          >
            {tag}
          </button>
        );
      })}
      {activeTag && (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
          title="Clear tag filter"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
