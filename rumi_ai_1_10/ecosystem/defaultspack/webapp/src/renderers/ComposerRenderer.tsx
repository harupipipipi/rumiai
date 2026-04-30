import { ChevronDown, Folder, Loader2, Mic, Paperclip, Plus, Send, Sparkles, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import type { ComposerRendererProps } from "./types";

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

export function ComposerRenderer({
  input,
  placeholder,
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
  onCommandSelect,
  onModelProfileSelect,
  onThinkingLevelChange,
  onInputChange,
  onSubmit,
}: ComposerRendererProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [openFolder, setOpenFolder] = useState<"tools" | "models" | "commands">("tools");
  const profileName = selectedProfile?.display_name ?? selectedProfile?.profile_id ?? "model";
  const levels = selectedProfile?.supports_thinking ? (selectedProfile.thinking_levels?.length ? selectedProfile.thinking_levels : ["low", "medium", "high"]) : [];
  const contextDegrees = Math.round(contextUsage.ratio * 360);
  const contextTitle = contextUsage.maxContext < 0
    ? `${contextUsage.usedTokens} tokens / unlimited`
    : `${contextUsage.usedTokens} / ${contextUsage.maxContext || "unknown"} tokens`;
  const toolItems = useMemo(() => [...inlineExtensions, ...belowExtensions], [inlineExtensions, belowExtensions]);
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

  return (
    <div className="px-5 pb-5 pt-2 bg-[#09090b] flex-shrink-0 max-[640px]:px-2 max-[640px]:pb-2">
      <div className="max-w-5xl mx-auto">
        <form onSubmit={onSubmit} className="relative flex flex-col bg-[#2b2b2d] border border-zinc-700/30 rounded-[20px] overflow-visible shadow-2xl shadow-black/20 focus-within:border-zinc-500/60 transition-colors max-[640px]:rounded-2xl">
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
                  {openFolder === "tools" && (
                    <div className="grid gap-1">
                      {toolItems.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          disabled={item.disabled}
                          onClick={() => {
                            onExtensionSelect?.(item);
                            setMenuOpen(false);
                          }}
                          className="rounded-lg px-3 py-2 text-left hover:bg-zinc-900 disabled:opacity-50"
                        >
                          <span className="block truncate text-sm text-zinc-100">{item.label}</span>
                          {item.description && <span className="block truncate text-[11px] text-zinc-500">{item.description}</span>}
                        </button>
                      ))}
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
            className="w-full bg-transparent border-none outline-none text-zinc-100 px-6 pt-3 pb-0 text-[16px] resize-none min-h-[34px] max-h-[110px] placeholder:text-zinc-500 disabled:opacity-50 max-[640px]:min-h-[32px] max-[640px]:px-3 max-[640px]:pt-2.5 max-[640px]:pb-0 max-[640px]:text-[13px]"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit(event);
              }
            }}
          />
          <div className="flex items-center justify-between gap-2 px-4 pb-2 pt-0 max-[640px]:gap-1.5 max-[640px]:px-2 max-[640px]:pb-1.5">
            <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
              <button type="button" disabled={isGenerating} title="追加" onClick={() => setMenuOpen((value) => !value)} className="h-7 w-7 flex flex-shrink-0 items-center justify-center text-zinc-300 hover:text-zinc-50 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50">
                <Plus size={20} />
              </button>
              <button type="button" disabled={isGenerating} title="添付" className="h-7 w-7 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50 max-[640px]:hidden">
                <Paperclip size={18} />
              </button>
              <button type="button" disabled={isGenerating} title="音声入力" className="h-7 w-7 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50 max-[640px]:hidden">
                <Mic size={18} />
              </button>
              {yoloMode && <span className="rounded-full border border-orange-500/30 px-2 py-0.5 text-[11px] text-orange-300">YOLO</span>}
            </div>
            <div className="flex flex-shrink-0 items-center justify-end gap-1.5">
              <div title={contextTitle} className="h-6 w-6 flex-shrink-0 rounded-full p-[3px] max-[640px]:hidden" style={{ background: `conic-gradient(#a1a1aa ${contextDegrees}deg, #52525b ${contextDegrees}deg)` }}>
                <div className="h-full w-full rounded-full bg-[#2b2b2d]" />
              </div>
              {favoriteProfiles.length > 1 ? (
                <select
                  value={selectedProfile?.profile_id ?? selectedProfile?.qualified_model_id ?? ""}
                  onChange={(event) => onModelProfileSelect(event.target.value)}
                  disabled={isGenerating}
                  className="max-w-[170px] bg-transparent text-[14px] font-semibold text-zinc-100 outline-none disabled:opacity-50 max-[640px]:hidden"
                  title="モデルプロファイル"
                >
                  {favoriteProfiles.map((profile) => (
                    <option key={profile.profile_id} value={profile.profile_id} className="bg-zinc-900 text-zinc-100">
                      {compactProfileName(profile.display_name)}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="max-w-[150px] truncate text-[14px] font-semibold text-zinc-100 max-[640px]:hidden" title={profileName}>
                  {compactProfileName(profileName)}
                </span>
              )}
              {levels.length > 0 && (
                <select
                  value={thinkingLevel ?? levels[0]}
                  onChange={(event) => onThinkingLevelChange(event.target.value)}
                  disabled={isGenerating}
                  className="bg-transparent text-[14px] text-zinc-300 outline-none disabled:opacity-50 max-[640px]:hidden"
                  title="Thinking level"
                >
                  {levels.map((level) => (
                    <option key={level} value={level} className="bg-zinc-900 text-zinc-100">
                      {THINKING_LABELS[level] ?? level}
                    </option>
                  ))}
                </select>
              )}
              <ChevronDown size={16} className="text-zinc-400 max-[640px]:hidden" />
              <button type="submit" disabled={!input.trim() || isGenerating} title="送信" className="flex flex-shrink-0 items-center justify-center w-9 h-9 bg-zinc-200 text-black rounded-full disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white transition-colors max-[640px]:h-8 max-[640px]:w-8">
                {isGenerating ? <Loader2 size={18} className="animate-spin" /> : <Send size={20} />}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
