import { Search, X } from "lucide-react";

export function ConversationSearchBar({
  value,
  resultCount,
  onChange,
}: {
  value: string;
  resultCount?: number;
  onChange: (value: string) => void;
}) {
  const hasValue = value.trim().length > 0;
  return (
    <label className="relative block">
      <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search conversations"
        className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-950/70 pl-8 pr-9 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
      />
      {hasValue && (
        <button
          type="button"
          onClick={() => onChange("")}
          className="absolute right-1.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
          title="Clear search"
        >
          <X size={12} />
        </button>
      )}
      {hasValue && resultCount !== undefined && (
        <span className="absolute right-8 top-1/2 -translate-y-1/2 text-[10px] text-zinc-600">
          {resultCount}
        </span>
      )}
    </label>
  );
}
