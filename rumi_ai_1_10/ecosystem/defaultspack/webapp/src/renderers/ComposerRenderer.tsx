import { ChevronDown, Loader2, Mic, Paperclip, Plus, Send, ShieldCheck } from "lucide-react";

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
  onModelProfileSelect,
  onThinkingLevelChange,
  onInputChange,
  onSubmit,
}: ComposerRendererProps) {
  const profileName = selectedProfile?.display_name ?? selectedProfile?.profile_id ?? "model";
  const levels = selectedProfile?.supports_thinking ? (selectedProfile.thinking_levels?.length ? selectedProfile.thinking_levels : ["low", "medium", "high"]) : [];
  const contextDegrees = Math.round(contextUsage.ratio * 360);
  const contextTitle = contextUsage.maxContext < 0
    ? `${contextUsage.usedTokens} tokens / unlimited`
    : `${contextUsage.usedTokens} / ${contextUsage.maxContext || "unknown"} tokens`;

  return (
    <div className="px-5 pb-5 pt-2 bg-[#09090b] flex-shrink-0">
      <div className="max-w-5xl mx-auto">
        <form onSubmit={onSubmit} className="relative flex flex-col bg-[#2b2b2d] border border-zinc-700/30 rounded-[28px] overflow-hidden shadow-2xl shadow-black/20 focus-within:border-zinc-500/60 transition-colors">
          <textarea
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder={placeholder}
            disabled={isGenerating}
            className="w-full bg-transparent border-none outline-none text-zinc-100 px-7 pt-7 pb-3 text-[16px] resize-none min-h-[96px] max-h-[220px] placeholder:text-zinc-500 disabled:opacity-50"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit(event);
              }
            }}
          />
          <div className="flex flex-col gap-3 px-5 pb-4 pt-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <button type="button" disabled={isGenerating} title="追加" className="h-9 w-9 flex items-center justify-center text-zinc-300 hover:text-zinc-50 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50">
                <Plus size={20} />
              </button>
              <button type="button" disabled={isGenerating} title="添付" className="h-9 w-9 flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50">
                <Paperclip size={18} />
              </button>
              {inlineExtensions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  disabled={isGenerating || item.disabled}
                  title={item.description ?? item.label}
                  className="hidden h-8 max-w-[140px] truncate rounded-full border border-zinc-700/70 px-3 text-[12px] text-zinc-300 hover:bg-zinc-700/60 hover:text-zinc-50 disabled:opacity-50 sm:inline-flex sm:items-center"
                >
                  {item.label}
                </button>
              ))}
              <button type="button" disabled={isGenerating} title="音声入力" className="h-9 w-9 flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/70 rounded-full transition-colors disabled:opacity-50">
                <Mic size={18} />
              </button>
            </div>
            <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
              <div title={contextTitle} className="h-6 w-6 rounded-full p-[3px]" style={{ background: `conic-gradient(#a1a1aa ${contextDegrees}deg, #52525b ${contextDegrees}deg)` }}>
                <div className="h-full w-full rounded-full bg-[#2b2b2d]" />
              </div>
              {favoriteProfiles.length > 1 ? (
                <select
                  value={selectedProfile?.profile_id ?? selectedProfile?.qualified_model_id ?? ""}
                  onChange={(event) => onModelProfileSelect(event.target.value)}
                  disabled={isGenerating}
                  className="max-w-[180px] bg-transparent text-[15px] font-semibold text-zinc-100 outline-none disabled:opacity-50"
                  title="モデルプロファイル"
                >
                  {favoriteProfiles.map((profile) => (
                    <option key={profile.profile_id} value={profile.profile_id} className="bg-zinc-900 text-zinc-100">
                      {compactProfileName(profile.display_name)}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="max-w-[160px] truncate text-[15px] font-semibold text-zinc-100" title={profileName}>
                  {compactProfileName(profileName)}
                </span>
              )}
              {levels.length > 0 && (
                <select
                  value={thinkingLevel ?? levels[0]}
                  onChange={(event) => onThinkingLevelChange(event.target.value)}
                  disabled={isGenerating}
                  className="bg-transparent text-[15px] text-zinc-300 outline-none disabled:opacity-50"
                  title="Thinking level"
                >
                  {levels.map((level) => (
                    <option key={level} value={level} className="bg-zinc-900 text-zinc-100">
                      {THINKING_LABELS[level] ?? level}
                    </option>
                  ))}
                </select>
              )}
              <ChevronDown size={16} className="text-zinc-400" />
              <button type="submit" disabled={!input.trim() || isGenerating} title="送信" className="flex items-center justify-center w-11 h-11 bg-zinc-200 text-black rounded-full disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white transition-colors">
                {isGenerating ? <Loader2 size={18} className="animate-spin" /> : <Send size={20} />}
              </button>
            </div>
          </div>
        </form>
        {belowExtensions.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 px-2 text-[13px] text-zinc-400">
            <span className="inline-flex items-center gap-1.5 text-zinc-500">
              <ShieldCheck size={14} />
              ローカルで作業
            </span>
            {belowExtensions.map((item) => (
              <button key={item.id} type="button" className="inline-flex max-w-[180px] items-center gap-1 truncate rounded-md px-2 py-1 hover:bg-zinc-800 hover:text-zinc-100" title={item.description ?? item.label}>
                <span className="truncate">{item.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
