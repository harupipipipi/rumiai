import { GitBranch, Loader2, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

export type BranchPickerStatus = "loading" | "ready" | "error";

type BranchPickerProps = {
  branches: string[];
  currentBranch?: string | null;
  disabled?: boolean;
  status?: BranchPickerStatus;
  errorMessage?: string | null;
  onClose: () => void;
  onRefresh?: () => Promise<void> | void;
  onSelect?: (branch: string) => Promise<void> | void;
};

export const normalizeBranchOptions = (
  branches: string[],
  currentBranch?: string | null,
): string[] => {
  const current = String(currentBranch ?? "").trim();
  const seen = new Set<string>();
  return [current, ...branches]
    .map((branch) => String(branch ?? "").trim())
    .filter((branch) => branch && branch !== "HEAD" && !branch.endsWith("/HEAD"))
    .filter((branch) => {
      if (seen.has(branch)) return false;
      seen.add(branch);
      return true;
    });
};

export const filterBranchOptions = (branches: string[], query: string): string[] => {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return branches;
  return branches.filter((branch) => branch.toLocaleLowerCase().includes(normalizedQuery));
};

export function BranchPicker({
  branches,
  currentBranch = null,
  disabled = false,
  status = "ready",
  errorMessage = null,
  onClose,
  onRefresh,
  onSelect,
}: BranchPickerProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [pendingBranch, setPendingBranch] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const options = useMemo(
    () => normalizeBranchOptions(branches, currentBranch),
    [branches, currentBranch],
  );
  const visibleOptions = useMemo(
    () => filterBranchOptions(options, query),
    [options, query],
  );
  const current = String(currentBranch ?? "").trim();
  const alternatives = options.filter((branch) => branch !== current);
  const visibleError = selectionError || errorMessage;

  useEffect(() => {
    searchRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    setSelectedIndex((index) => Math.min(index, Math.max(visibleOptions.length - 1, 0)));
  }, [visibleOptions.length]);

  const selectBranch = async (branch: string | undefined) => {
    if (!branch || branch === current || disabled || pendingBranch) return;
    setSelectionError(null);
    setPendingBranch(branch);
    try {
      await onSelect?.(branch);
      onClose();
    } catch (error) {
      setSelectionError(
        error instanceof Error && error.message.trim()
          ? error.message
          : "ブランチを切り替えられませんでした。権限とワークスペースの状態を確認してください。",
      );
    } finally {
      setPendingBranch(null);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((index) => Math.min(index + 1, Math.max(visibleOptions.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      void selectBranch(visibleOptions[selectedIndex]);
    }
  };

  return (
    <>
      <button
        type="button"
        aria-label="Dismiss branch picker"
        tabIndex={-1}
        className="fixed inset-0 rumi-layer-local-popover cursor-default"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-labelledby="branch-picker-title"
        aria-describedby={visibleError ? "branch-picker-error" : "branch-picker-help"}
        data-branch-picker="open"
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          event.preventDefault();
          onClose();
        }}
        className="absolute bottom-full left-4 rumi-layer-global-overlay mb-2 w-[min(420px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
          <h2 id="branch-picker-title" className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <GitBranch size={14} aria-hidden="true" />
            ブランチを選択
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
            title="閉じる"
            aria-label="Close branch picker"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        <label className="mx-3 mt-3 flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/70 px-2.5 text-zinc-400 focus-within:border-zinc-600">
          <Search size={13} aria-hidden="true" />
          <span className="sr-only">ブランチを検索</span>
          <input
            ref={searchRef}
            role="combobox"
            aria-expanded="true"
            aria-autocomplete="list"
            aria-controls="branch-picker-options"
            aria-activedescendant={visibleOptions[selectedIndex] ? `branch-option-${selectedIndex}` : undefined}
            value={query}
            placeholder="ブランチを検索"
            onChange={(event) => {
              setQuery(event.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            className="min-w-0 flex-1 bg-transparent py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
          />
        </label>

        <p id="branch-picker-help" className="px-3 pb-2 pt-2 text-xs text-zinc-500">
          ↑↓で移動、Enterで切り替え、Escで閉じます。新規作成は /branch &lt;name&gt; を使います。
        </p>

        {status === "loading" ? (
          <div role="status" className="flex items-center gap-2 px-3 py-4 text-sm text-zinc-400">
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ブランチ候補を読み込んでいます…
          </div>
        ) : status === "error" ? (
          <div className="px-3 pb-3">
            <p id="branch-picker-error" role="alert" className="text-sm text-rose-300">
              {errorMessage || "ブランチ候補を読み込めませんでした。"}
            </p>
            {onRefresh && (
              <button
                type="button"
                onClick={() => void onRefresh()}
                className="mt-2 rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:bg-zinc-900"
              >
                再読み込み
              </button>
            )}
          </div>
        ) : alternatives.length === 0 ? (
          <p role="status" className="px-3 pb-4 text-sm text-zinc-400">
            切り替え可能なブランチがありません。/branch &lt;name&gt; で新しいブランチを作成できます。
          </p>
        ) : visibleOptions.length === 0 ? (
          <p role="status" className="px-3 pb-4 text-sm text-zinc-400">
            「{query}」に一致するブランチはありません。
          </p>
        ) : (
          <div
            id="branch-picker-options"
            role="listbox"
            aria-label="Branches"
            className="max-h-64 overflow-y-auto border-t border-zinc-900 py-1"
          >
            {visibleOptions.map((branch, index) => {
              const isCurrent = branch === current;
              const isPending = branch === pendingBranch;
              return (
                <button
                  id={`branch-option-${index}`}
                  key={branch}
                  type="button"
                  tabIndex={-1}
                  role="option"
                  aria-selected={index === selectedIndex}
                  aria-disabled={isCurrent || disabled}
                  disabled={isCurrent || disabled || Boolean(pendingBranch)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onClick={() => void selectBranch(branch)}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left font-mono text-sm disabled:cursor-default ${
                    index === selectedIndex ? "bg-zinc-800 text-zinc-100" : "text-zinc-300 hover:bg-zinc-900"
                  } ${isCurrent ? "opacity-70" : ""}`}
                >
                  <span className="min-w-0 truncate">{branch}</span>
                  {isPending ? (
                    <Loader2 size={13} className="shrink-0 animate-spin" aria-label="Switching branch" />
                  ) : isCurrent ? (
                    <span className="shrink-0 rounded-full bg-emerald-500/15 px-2 py-0.5 font-sans text-[10px] text-emerald-300">
                      current
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}

        {status !== "error" && selectionError && (
          <p id="branch-picker-error" role="alert" className="border-t border-zinc-800 px-3 py-2 text-sm text-rose-300">
            {selectionError}
          </p>
        )}
      </section>
    </>
  );
}
