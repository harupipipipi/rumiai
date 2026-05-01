import { ArrowUp, ChevronDown, Folder, Loader2, Mic, Paperclip, Plus, Sparkles, Wrench } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import type { ComposerRendererProps } from "./types";
import type { ComposerExtensionItem } from "./types";

const THINKING_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

function compactProfileName(name: string): string {
  return name
    .replace(/^GPT-/i, "")
    .replace(/^Claude\s+/i, "")
    .replace(/\s*\(.*?\)\s*/g, " ")
    .trim();
}

type ToolGroup = {
  id: string;
  label: string;
  description: string;
  items: ComposerExtensionItem[];
};

function toolGroupFor(item: ComposerExtensionItem): Omit<ToolGroup, "items"> {
  const haystack = `${item.id} ${item.label} ${item.description ?? ""} ${(item.tags ?? []).join(" ")}`.toLowerCase();
  if (/(search|research|web|reddit|knowledge|local)/.test(haystack)) {
    return { id: "research", label: "調べる", description: "web/search/knowledge 系" };
  }
  if (/(file|coding|code|artifact|patch|write|create|read)/.test(haystack)) {
    return { id: "build", label: "作る・編集", description: "ファイル作成、修正、読み取り" };
  }
  if (/(browser|computer|screen|screenshot)/.test(haystack)) {
    return { id: "operate", label: "操作する", description: "browser/computer 操作" };
  }
  if (/(terminal|shell|command|git)/.test(haystack)) {
    return { id: "terminal", label: "コマンド", description: "terminal/git 実行" };
  }
  return { id: "other", label: "その他", description: "追加 tool" };
}

function groupToolItems(items: ComposerExtensionItem[]): ToolGroup[] {
  const groups = new Map<string, ToolGroup>();
  for (const item of items) {
    const meta = toolGroupFor(item);
    const current = groups.get(meta.id) ?? { ...meta, items: [] };
    current.items.push(item);
    groups.set(meta.id, current);
  }
  return [...groups.values()].filter((group) => group.items.length > 0);
}

function ToolItemList({
  items,
  onSelect,
}: {
  items: ComposerExtensionItem[];
  onSelect: (item: ComposerExtensionItem) => void;
}) {
  if (items.length === 0) {
    return <div className="px-3 py-2 text-xs text-zinc-500">tool がありません</div>;
  }
  return (
    <div className="grid gap-1">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          disabled={item.disabled}
          onClick={() => onSelect(item)}
          className="rounded-lg px-3 py-2 text-left transition-colors hover:bg-zinc-900 disabled:opacity-50"
        >
          <span className="block truncate text-sm text-zinc-100">{item.label}</span>
          {item.description && <span className="block truncate text-[11px] text-zinc-500">{item.description}</span>}
        </button>
      ))}
    </div>
  );
}

export function ComposerRenderer({
  input,
  placeholder,
  isNewConversation = false,
  isGenerating,
  selectedProfile,
  favoriteProfiles,
  thinkingLevel,
  contextUsage,
  inlineExtensions,
  belowExtensions,
  commands = [],
  yoloMode = false,
  onExtensionSelect,
  onFilesAttach,
  onCommandSelect,
  onModelProfileSelect,
  onThinkingLevelChange,
  onInputChange,
  onSubmit,
}: ComposerRendererProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [openFolder, setOpenFolder] = useState<"tools" | "models" | "commands">("tools");
  const [openToolGroup, setOpenToolGroup] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const profileName = selectedProfile?.display_name ?? selectedProfile?.profile_id ?? "model";
  const levels = selectedProfile?.supports_thinking ? (selectedProfile.thinking_levels?.length ? selectedProfile.thinking_levels : ["low", "medium", "high"]) : [];
  const contextDegrees = Math.round(contextUsage.ratio * 360);
  const contextTitle = contextUsage.maxContext < 0
    ? `${contextUsage.usedTokens} tokens / unlimited`
    : `${contextUsage.usedTokens} / ${contextUsage.maxContext || "unknown"} tokens`;
  const toolItems = useMemo(() => [...inlineExtensions, ...belowExtensions], [inlineExtensions, belowExtensions]);
  const toolGroups = useMemo(() => groupToolItems(toolItems), [toolItems]);
  const activeToolGroup = toolGroups.find((group) => group.id === openToolGroup) ?? toolGroups[0] ?? null;
  const showToolGroups = toolItems.length > 4;
  const slashQuery = input.startsWith("/") ? input.slice(1).trim().toLowerCase() : "";
  const matchedCommands = input.startsWith("/")
    ? commands.filter((command) => {
        const haystack = `${command.id} ${command.label} ${command.description ?? ""}`.toLowerCase();
        return !slashQuery || haystack.includes(slashQuery);
      })
    : [];

  const chooseCommand = (commandId: string) => {
    onCommandSelect?.(commandId);
    onInputChange("");
  };

  const attachFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const snippets = await Promise.all(
      Array.from(files).map(async (file) => {
        const text = await file.text();
        const truncated = text.length > 120_000;
        const clippedText = truncated ? `${text.slice(0, 120_000)}\n...` : text;
        return `\n\n添付ファイル: ${file.name}\n\`\`\`\n${clippedText}\n\`\`\``;
      }),
    );
    onFilesAttach?.(
      await Promise.all(
        Array.from(files).map(async (file) => {
          const text = await file.text();
          const truncated = text.length > 120_000;
          return {
            name: file.name,
            content: truncated ? text.slice(0, 120_000) : text,
            size: file.size,
            type: file.type || "text/plain",
            truncated,
          };
        }),
      ),
    );
    onInputChange(`${input}${snippets.join("")}`);
  };

  return (
    <div className={`${isNewConversation ? "w-full px-5" : "px-5 pb-5 pt-2 bg-[#09090b] flex-shrink-0 max-[640px]:px-2 max-[640px]:pb-2"}`}>
      <div className={`rumi-composer-shell ${isNewConversation ? "rumi-composer-shell-new mx-auto" : "mx-auto"}`}>
        <form onSubmit={onSubmit} className={`rumi-composer-frame ${isNewConversation ? "rumi-composer-new min-h-[162px] rounded-[26px] border-zinc-700/70 bg-[#202021]" : "rounded-[20px] border-zinc-700/30 bg-[#2b2b2d] max-[640px]:rounded-2xl"} relative flex flex-col border overflow-visible shadow-2xl shadow-black/20 focus-within:border-zinc-500/60`}>
          {matchedCommands.length > 0 && (
            <div className="absolute bottom-full left-4 z-30 mb-2 w-[min(420px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
              <div className="border-b border-zinc-800 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Commands</div>
              <div className="max-h-56 overflow-y-auto py-1">
                {matchedCommands.map((command) => (
                  <button
                    key={command.id}
                    type="button"
                    onClick={() => chooseCommand(command.id)}
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-zinc-900"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-zinc-100">/{command.label}</span>
                      {command.description && <span className="block truncate text-[11px] text-zinc-500">{command.description}</span>}
                    </span>
                    {command.enabled && <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
          {menuOpen && (
            <>
              <button type="button" aria-label="close composer menu" className="fixed inset-0 z-20 cursor-default" onClick={() => setMenuOpen(false)} />
              <div className="absolute bottom-[52px] left-4 z-30 grid w-[min(520px,calc(100vw-32px))] grid-cols-[132px_minmax(0,1fr)] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl max-[640px]:left-2 max-[640px]:grid-cols-1">
                <div className="border-r border-zinc-800 bg-zinc-950/90 p-1.5 max-[640px]:flex max-[640px]:border-b max-[640px]:border-r-0">
                  {([
                    ["tools", "Tools", Wrench],
                    ["models", "AI", Sparkles],
                    ["commands", "Commands", Folder],
                  ] as const).map(([id, label, Icon]) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setOpenFolder(id)}
                      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${openFolder === id ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}
                    >
                      <Icon size={14} />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
                <div className="max-h-72 overflow-y-auto p-2">
                  {openFolder === "tools" && !showToolGroups && (
                    <ToolItemList items={toolItems} onSelect={(item) => {
                      onExtensionSelect?.(item);
                      setMenuOpen(false);
                    }} />
                  )}
                  {openFolder === "tools" && showToolGroups && (
                    <div className="grid grid-cols-[150px_minmax(0,1fr)] gap-2 max-[640px]:grid-cols-1">
                      <div className="grid content-start gap-1">
                        {toolGroups.map((group) => (
                          <button
                            key={group.id}
                            type="button"
                            onClick={() => setOpenToolGroup(group.id)}
                            className={`rounded-lg px-3 py-2 text-left transition-colors ${activeToolGroup?.id === group.id ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}
                          >
                            <span className="block truncate text-sm">{group.label}</span>
                            <span className="block truncate text-[10px] text-zinc-500">{group.items.length} tools</span>
                          </button>
                        ))}
                      </div>
                      <div className="min-w-0">
                        {activeToolGroup && (
                          <>
                            <div className="mb-1.5 px-2 text-[10px] text-zinc-500">{activeToolGroup.description}</div>
                            <ToolItemList items={activeToolGroup.items} onSelect={(item) => {
                              onExtensionSelect?.(item);
                              setMenuOpen(false);
                            }} />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                  {openFolder === "models" && (
                    <div className="grid gap-1">
                      {favoriteProfiles.map((profile) => (
                        <button
                          key={profile.profile_id}
                          type="button"
                          onClick={() => {
                            onModelProfileSelect(profile.profile_id);
                            setMenuOpen(false);
                          }}
                          className="rounded-lg px-3 py-2 text-left hover:bg-zinc-900"
                        >
                          <span className="block truncate text-sm text-zinc-100">{compactProfileName(profile.display_name)}</span>
                          <span className="block truncate text-[11px] text-zinc-500">{profile.max_context_tokens ?? profile.max_context ?? "?"} context</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {openFolder === "commands" && (
                    <div className="grid gap-1">
                      {commands.map((command) => (
                        <button
                          key={command.id}
                          type="button"
                          onClick={() => {
                            chooseCommand(command.id);
                            setMenuOpen(false);
                          }}
                          className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-zinc-900"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm text-zinc-100">/{command.label}</span>
                            {command.description && <span className="block truncate text-[11px] text-zinc-500">{command.description}</span>}
                          </span>
                          {command.enabled && <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder={placeholder}
            disabled={isGenerating}
            className={`${isNewConversation ? "rumi-composer-input-new min-h-[94px] px-7 pt-6 text-[18px] font-medium leading-[1.55] placeholder:text-zinc-500" : "min-h-[34px] px-6 pt-3 text-[16px] max-[640px]:min-h-[32px] max-[640px]:px-3 max-[640px]:pt-2.5 max-[640px]:pb-0 max-[640px]:text-[13px]"} w-full bg-transparent border-none outline-none text-zinc-100 pb-0 resize-none max-h-[130px] disabled:opacity-50`}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit(event);
              }
            }}
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              void attachFiles(event.target.files).finally(() => {
                event.target.value = "";
              });
            }}
          />
          <div className={`${isNewConversation ? "rumi-composer-actions px-5 pb-4" : "px-4 pb-2 max-[640px]:px-2 max-[640px]:pb-1.5"} flex items-center justify-between gap-2 pt-0 max-[640px]:gap-1.5`}>
            <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
              <button type="button" disabled={isGenerating} title="追加" onClick={() => setMenuOpen((value) => !value)} className="h-7 w-7 flex flex-shrink-0 items-center justify-center text-zinc-300 hover:text-zinc-50 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50">
                <Plus size={20} />
              </button>
              <button type="button" disabled={isGenerating} title="ファイル添付" onClick={() => fileInputRef.current?.click()} className={`${isNewConversation ? "border border-zinc-700/70 bg-zinc-900/30 text-zinc-300 hover:border-zinc-600 hover:bg-zinc-800/70" : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70"} h-7 w-7 flex flex-shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-50`}>
                <Paperclip size={18} />
              </button>
              <button type="button" disabled={isGenerating} title="音声入力" className="h-7 w-7 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50 max-[640px]:hidden">
                <Mic size={18} />
              </button>
              {yoloMode && <span className="rounded-full border border-orange-500/30 px-2 py-0.5 text-[11px] text-orange-300">YOLO</span>}
            </div>
            <div className="rumi-composer-submit-area flex flex-shrink-0 items-center justify-end gap-2.5">
              <div className="rumi-model-control flex items-center gap-2 bg-zinc-800/50 rounded-full px-3 py-1.5 border border-zinc-700/50 max-[640px]:hidden">
                <div title={contextTitle} className="h-4 w-4 flex-shrink-0 rounded-full p-[2px]" style={{ background: `conic-gradient(#a1a1aa ${contextDegrees}deg, #52525b ${contextDegrees}deg)` }}>
                  <div className="h-full w-full rounded-full bg-zinc-800" />
                </div>
                {favoriteProfiles.length > 1 ? (
                  <select
                    value={selectedProfile?.profile_id ?? selectedProfile?.qualified_model_id ?? ""}
                    onChange={(event) => onModelProfileSelect(event.target.value)}
                    disabled={isGenerating}
                    className="max-w-[130px] pr-2 bg-transparent text-[12px] font-medium text-zinc-300 outline-none cursor-pointer hover:text-zinc-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="モデルプロファイル"
                  >
                    {favoriteProfiles.map((profile) => (
                      <option key={profile.profile_id} value={profile.profile_id} className="bg-zinc-900 text-zinc-100">
                        {compactProfileName(profile.display_name)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="max-w-[130px] truncate text-[12px] font-medium text-zinc-300" title={profileName}>
                    {compactProfileName(profileName)}
                  </span>
                )}
                {levels.length > 0 && (
                  <select
                    value={thinkingLevel ?? levels[0]}
                    onChange={(event) => onThinkingLevelChange(event.target.value)}
                    disabled={isGenerating}
                    className="bg-transparent text-[12px] font-medium text-zinc-400 outline-none cursor-pointer hover:text-zinc-200 transition-colors disabled:opacity-50 border-l border-zinc-700/50 pl-2 ml-1"
                    title="Thinking level"
                  >
                    {levels.map((level) => (
                      <option key={level} value={level} className="bg-zinc-900 text-zinc-100">
                        {THINKING_LABELS[level] ?? level}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <button type="submit" disabled={!input.trim() || isGenerating} title="送信" className={`rumi-send-button ${isNewConversation ? "h-10 w-10" : "w-9 h-9 max-[640px]:h-8 max-[640px]:w-8"} flex flex-shrink-0 items-center justify-center bg-zinc-200 text-black rounded-full disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white shadow-sm`}>
                {isGenerating ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={18} strokeWidth={2.4} />}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
