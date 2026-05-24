import {
  ArrowUp,
  BrainCircuit,
  ChevronDown,
  Code2,
  CornerDownRight,
  Cpu,
  File,
  FileText,
  Folder,
  GitBranch,
  KeyRound,
  Loader2,
  MessageSquare,
  MousePointerClick,
  PanelRightOpen,
  Search,
  SlidersHorizontal,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";

import type {
  AttachedFile,
  ComposerCommandItem,
  ComposerExtensionItem,
  ComposerRendererProps,
  ComposerSkillItem,
  DroppedWidget,
  AppMode,
  ToolGroup,
} from "./types";
import type { ModelCommandCandidate, ModelProfile } from "../lib/api";
import { CodingWorkspaceBadge } from "../components/coding/CodingWorkspaceBadge";
import { CodingWorkspacePicker } from "../components/coding/CodingWorkspacePicker";
import { RuntimeCapabilityBanner } from "../components/RuntimeCapabilityBanner";
import { WarmActionIcon } from "../components/WarmActionIcon";
import { fileToAttachment } from "../lib/attachments";
import { composerSkillMentionWidget, composerToolMentionWidget, filterComposerSkillMentions, filterComposerToolMentions, resolveComposerWidgetDrop } from "../lib/composerWidgets";
import { HISTORY_CHAT_DROP_MIME, parseHistoryChatDrop } from "../lib/historyComposer";
import { sortedToolGroups, toolGroupFor } from "../lib/toolUi";

export { composerSkillMentionWidget, composerToolMentionWidget, filterComposerSkillMentions, filterComposerToolMentions, resolveComposerWidgetDrop, skillMentionIdsFromText, toolMentionIdsFromText } from "../lib/composerWidgets";

const THINKING_LABELS: Record<string, string> = {
  none: "なし",
  low: "低",
  medium: "中",
  high: "高",
  xhigh: "最高",
};

const RISK_BADGE_STYLES: Record<string, string> = {
  low: "border-emerald-500/20 text-emerald-300",
  medium: "border-amber-500/25 text-amber-300",
  high: "border-rose-500/30 text-rose-300",
};

const MODE_META: Record<AppMode, { label: string; icon: typeof MessageSquare; description: string }> = {
  chat: { label: "Chat", icon: MessageSquare, description: "通常チャット" },
  coding: { label: "Coding", icon: Code2, description: "コード編集・Git操作" },
  agent: { label: "Agent", icon: Cpu, description: "自律エージェント" },
};

type ComposerChromeWidth = {
  basis: string;
  min?: string;
  max?: string;
  grow?: number;
  shrink?: number;
};

type ComposerChromeSlot = "leading" | "trailing";

type ComposerChromeWidgetSpec = {
  id: string;
  slot: ComposerChromeSlot;
  order: number;
  visible?: boolean;
  mobile?: "show" | "hide";
  width: ComposerChromeWidth;
  className?: string;
  render: () => ReactNode;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    isFinal?: boolean;
    0?: { transcript?: string };
  }>;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

const COMPOSER_CHROME_WIDTHS = {
  icon: { basis: "2rem", min: "2rem", max: "2rem" },
  mode: { basis: "auto", min: "2rem", max: "7rem", shrink: 1 },
  badge: { basis: "auto", min: "0", max: "11rem", shrink: 1 },
  model: { basis: "14rem", min: "11rem", max: "15rem", shrink: 1 },
  send: { basis: "2rem", min: "2rem", max: "2rem" },
  sendLarge: { basis: "2.25rem", min: "2.25rem", max: "2.25rem" },
} satisfies Record<string, ComposerChromeWidth>;

export function composerChromeWidgetStyle(width: ComposerChromeWidth): CSSProperties {
  return {
    flex: `${width.grow ?? 0} ${width.shrink ?? 0} ${width.basis}`,
    minWidth: width.min,
    maxWidth: width.max,
  };
}

function composerChromeWidgetsForSlot(
  widgets: ComposerChromeWidgetSpec[],
  slot: ComposerChromeSlot,
): ComposerChromeWidgetSpec[] {
  return widgets
    .filter((widget) => widget.slot === slot && widget.visible !== false)
    .sort((left, right) => left.order - right.order);
}

function ComposerChromeWidget({ widget }: { widget: ComposerChromeWidgetSpec }) {
  const mobileClass = widget.mobile === "hide" ? "max-[640px]:hidden" : "";
  return (
    <div
      data-composer-widget={widget.id}
      data-composer-slot={widget.slot}
      className={`rumi-composer-widget flex min-w-0 items-center ${mobileClass} ${widget.className ?? ""}`}
      style={composerChromeWidgetStyle(widget.width)}
    >
      {widget.render()}
    </div>
  );
}

const LOCAL_MODEL_PROVIDER_IDS = new Set(["stub", "ollama", "lmstudio", "vllm", "llamacpp", "llama_cpp"]);
const API_KEY_PROVIDER_IDS = new Set([
  "anthropic",
  "deepseek",
  "glm",
  "google",
  "groq",
  "longcat",
  "mistral",
  "openai",
  "openai_compatible",
  "openrouter",
  "perplexity",
  "together",
  "xai",
]);

function profileProviderId(profile: ModelProfile | null | undefined): string {
  return String(profile?.provider_id ?? "").trim();
}

function profileProviderLabel(profile: ModelProfile | null | undefined): string {
  return String(
    profile?.provider_display_name
    ?? profile?.metadata?.provider_display_name
    ?? profile?.provider_id
    ?? "provider",
  );
}

function profileDisplayName(profile: ModelProfile | null | undefined): string {
  return String(
    profile?.disambiguated_name
    ?? profile?.metadata?.disambiguated_name
    ?? profile?.display_name
    ?? profile?.profile_id
    ?? "model",
  );
}

function profileIsConfigured(profile: ModelProfile | null | undefined): boolean {
  const availability = profile?.availability ?? {};
  return Boolean(
    availability.configured
    || availability.active
    || availability.status === "configured"
    || availability.status === "active",
  );
}

export function profileNeedsApiKey(profile: ModelProfile | null | undefined): boolean {
  const providerId = profileProviderId(profile);
  if (!providerId || providerId === "rumi" || LOCAL_MODEL_PROVIDER_IDS.has(providerId)) return false;
  const availability = profile?.availability ?? {};
  if (profile?.local || availability.local || availability.offline || profileIsConfigured(profile)) return false;
  return API_KEY_PROVIDER_IDS.has(providerId);
}

function thinkingCommandMatch(input: string): { query: string } | null {
  const match = input.trimStart().match(/^\/(?:think|thinking|t)(?:\s+(\S*))?$/i);
  if (!match) return null;
  return { query: String(match[1] ?? "").toLowerCase() };
}

function compactProfileName(name: string): string {
  return name
    .replace(/^GPT-/i, "")
    .replace(/^Claude\s+/i, "")
    .replace(/\s*\(.*?\)\s*/g, " ")
    .trim();
}

function steerStatusLabel(status: string | undefined): string {
  switch (String(status || "").toLowerCase()) {
    case "queued":
      return "待機中";
    case "injected":
      return "反映済み";
    case "sending":
      return "送信中";
    case "sent":
      return "送信済み";
    default:
      return "入力";
  }
}

function capabilityBadges(profile: ModelProfile | null | undefined): string[] {
  if (!profile) return [];
  const badges: string[] = [];
  if (profile.supports_vision || profile.supports_image_input) badges.push("Vision");
  if (profile.supports_tool_calling) badges.push("Tools");
  if (profile.supports_thinking) badges.push("Thinking");
  if (profile.supports_fast || profile.speed_tier === "fast") badges.push("Fast");
  if ((profile.max_context_tokens ?? profile.max_context ?? 0) >= 100000) badges.push("Long Context");
  return badges;
}

function modelRouteReason(profile: ModelProfile | null | undefined): string {
  if (!profile) return "";
  const knowledge = typeof profile.knowledge_level === "number" ? `KL ${profile.knowledge_level}` : "";
  return [...capabilityBadges(profile), knowledge].filter(Boolean).join(" / ");
}

function normalizeProviderSearchToken(value: string): string {
  return value
    .trim()
    .replace(/^@+/, "")
    .toLowerCase()
    .replace(/[\s_-]+/g, "");
}

function modelProfileProviderAliases(profile: ModelProfile): string[] {
  return [
    profile.provider_id,
    profile.provider_display_name,
    profile.metadata?.provider_id,
    profile.metadata?.provider_display_name,
  ].map((value) => normalizeProviderSearchToken(String(value ?? ""))).filter(Boolean);
}

function modelProfileSearchText(profile: ModelProfile): string {
  return [
    profile.profile_id,
    profile.qualified_model_id,
    profile.model_id,
    profile.provider_id,
    profile.provider_display_name,
    profileDisplayName(profile),
    profile.display_name,
    profile.disambiguated_name,
    ...(profile.capability_tags ?? []),
    ...(profile.recommended_roles ?? []),
  ].filter(Boolean).join(" ").toLowerCase();
}

export function filterModelProfilesBySearch(profiles: ModelProfile[], search: string): ModelProfile[] {
  const rawTokens = search.trim().split(/\s+/).filter(Boolean);
  if (rawTokens.length === 0) return profiles;

  const providerTokens = rawTokens
    .filter((token) => token.startsWith("@"))
    .map(normalizeProviderSearchToken)
    .filter(Boolean);
  const textTokens = rawTokens
    .filter((token) => !token.startsWith("@"))
    .map((token) => token.toLowerCase())
    .filter(Boolean);

  return profiles.filter((profile) => {
    const providerAliases = modelProfileProviderAliases(profile);
    const matchesProviders = providerTokens.every((token) => (
      providerAliases.some((alias) => alias.includes(token))
    ));
    if (!matchesProviders) return false;

    const searchText = modelProfileSearchText(profile);
    return textTokens.every((token) => searchText.includes(token));
  });
}

function groupToolItems(items: ComposerExtensionItem[]): ToolGroup[] {
  const groups = new Map<string, ToolGroup>();
  for (const item of items) {
    const meta = toolGroupFor(item);
    const current = groups.get(meta.id) ?? { ...meta, items: [] };
    current.items.push(item);
    groups.set(meta.id, current);
  }
  return sortedToolGroups([...groups.values()].filter((group) => group.items.length > 0));
}

function FileChip({ file, onRemove }: { file: AttachedFile; onRemove?: (id: string) => void }) {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const icon = /^(md|txt|json|yaml|yml|toml|ini|cfg)$/.test(ext) ? <FileText size={12} /> : <File size={12} />;
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-zinc-700/60 bg-zinc-800/70 px-2 py-0.5 text-[11px] text-zinc-300 max-w-[160px]">
      {icon}
      <span className="truncate">{file.name}</span>
      {onRemove && (
        <button type="button" onClick={() => onRemove(file.id)} className="ml-0.5 text-zinc-500 hover:text-zinc-200 flex-shrink-0">
          <X size={10} />
        </button>
      )}
    </span>
  );
}

function FilePreviewCard({ file, onRemove }: { file: AttachedFile; onRemove?: (id: string) => void }) {
  const ext = file.name.split(".").pop()?.toUpperCase() || "FILE";
  const lineCount = file.content ? file.content.split(/\r\n|\r|\n/).length : null;
  const isImage = /^image\//.test(file.type ?? "");
  return (
    <div className="group/file relative h-[120px] w-[148px] flex-shrink-0 rounded-xl border border-zinc-600/70 bg-[#272728] p-3 shadow-sm">
      <div className="flex h-full flex-col justify-between">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-medium text-zinc-100">{file.name}</p>
          <p className="mt-1 text-[12px] text-zinc-500">
            {lineCount ? `${lineCount}行` : `${Math.max(1, Math.ceil(file.size / 1024))} KB`}
          </p>
        </div>
        <div className="inline-flex h-7 w-fit items-center rounded-md border border-zinc-500/60 px-2 text-[13px] font-semibold text-zinc-300">
          {isImage ? "IMG" : ext.slice(0, 4)}
        </div>
      </div>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(file.id)}
          className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-zinc-950/80 text-zinc-400 opacity-0 transition-opacity hover:text-zinc-100 group-hover/file:opacity-100"
          title="削除"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}

function DroppedWidgetChip({
  widget,
  onAction,
  onToggle,
}: {
  widget: DroppedWidget;
  onAction?: (widget: DroppedWidget) => void;
  onToggle?: (id: string) => void;
}) {
  if (widget.type === "conversation") {
    return (
      <button
        type="button"
        title={widget.description ?? widget.label}
        onClick={() => onToggle?.(widget.id)}
        className={`inline-flex max-w-[220px] items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
          widget.enabled === false
            ? "border-zinc-700/60 bg-zinc-800/50 text-zinc-500"
            : "border-amber-500/30 bg-amber-500/10 text-amber-200 hover:bg-amber-500/15"
        }`}
      >
        <MessageSquare size={10} />
        <span className="truncate">{widget.label}</span>
      </button>
    );
  }

  if (widget.widgetKind !== "tool_toggle" && widget.type !== "tool") {
    const Icon = widget.widgetKind === "button"
      ? MousePointerClick
      : widget.widgetKind === "selector"
        ? SlidersHorizontal
        : PanelRightOpen;
    return (
      <button
        type="button"
        title={widget.description ?? widget.label}
        onClick={() => onAction?.(widget)}
        className="inline-flex max-w-[160px] items-center gap-1 rounded-md border border-zinc-700/60 bg-zinc-800/70 px-2 py-0.5 text-[11px] text-zinc-300 transition-colors hover:bg-zinc-800/80 hover:text-zinc-100"
      >
        <Icon size={10} />
        <span className="truncate">{widget.label}</span>
      </button>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] cursor-pointer transition-colors ${
        widget.enabled
          ? "border-emerald-600/50 bg-emerald-900/30 text-emerald-300"
          : "border-zinc-700/60 bg-zinc-800/70 text-zinc-400"
      }`}
      onClick={() => onToggle?.(widget.id)}
    >
      <Wrench size={10} />
      <span className="truncate">{widget.label}</span>
    </span>
  );
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
    <div className="grid gap-0.5">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          disabled={item.disabled}
          onClick={() => onSelect(item)}
          className="rounded-lg px-3 py-1.5 text-left transition-colors hover:bg-zinc-800/80 disabled:opacity-50 group"
        >
          <span className="block truncate text-[13px] text-zinc-200 group-hover:text-zinc-50">{item.label}</span>
          {item.description && <span className="block truncate text-[10px] text-zinc-500">{item.description}</span>}
        </button>
      ))}
    </div>
  );
}

function ProviderApiKeyPrompt({
  profile,
  onCancel,
  onSave,
}: {
  profile: ModelProfile;
  onCancel: () => void;
  onSave: (providerId: string, value: string) => Promise<void> | void;
}) {
  const [draft, setDraft] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const providerId = profileProviderId(profile);
  const providerLabel = profileProviderLabel(profile);

  const save = async () => {
    const value = draft.trim();
    if (!value || isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      await onSave(providerId, value);
      setDraft("");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "API key の保存に失敗しました。");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <button type="button" aria-label="close api key prompt" className="fixed inset-0 z-30 cursor-default" onClick={onCancel} />
      <div className="absolute bottom-full right-3 z-40 mb-2 w-[min(430px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/80 bg-zinc-950 shadow-2xl">
        <div className="border-b border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
            <KeyRound size={15} className="text-zinc-400" />
            {providerLabel} API key
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">
            {profile.display_name} を使うには API key が必要です。ここで保存すると、そのままモデルを選べます。
          </p>
        </div>
        <div className="space-y-2 p-3">
          <input
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(null);
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              void save();
            }}
            placeholder={providerId === "google" ? "Gemini API key" : `${providerLabel} API key`}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
            autoFocus
          />
          {error && <p className="text-[11px] text-red-300">{error}</p>}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="h-8 rounded-lg px-3 text-xs text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!draft.trim() || isSaving}
              onClick={() => void save()}
              className={`h-8 rounded-lg px-3 text-xs font-semibold transition-colors ${
                draft.trim() && !isSaving
                  ? "bg-zinc-100 text-zinc-950 hover:bg-white"
                  : "bg-zinc-900 text-zinc-600 cursor-not-allowed"
              }`}
            >
              {isSaving ? "Saving..." : "Save and use"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function ModelDropdown({
  profiles,
  selectedProfile,
  isGenerating,
  onSelect,
  onClose,
}: {
  profiles: ModelProfile[];
  selectedProfile: ModelProfile | null;
  isGenerating: boolean;
  onSelect: (profileId: string) => void;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => filterModelProfilesBySearch(profiles, search), [profiles, search]);

  const groupedByProvider = useMemo(() => {
    const map = new Map<string, ModelProfile[]>();
    for (const profile of filtered) {
      const provider = profile.provider_id ?? "other";
      const list = map.get(provider) ?? [];
      list.push(profile);
      map.set(provider, list);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <>
      <button type="button" aria-label="close model dropdown" className="fixed inset-0 z-20 cursor-default" onClick={onClose} />
      <div className="absolute bottom-full left-0 mb-2 z-[70] w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
        <div className="border-b border-zinc-800 p-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="モデルを検索... @google"
              className="w-full rounded-lg bg-zinc-900 border border-zinc-800 pl-8 pr-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-zinc-600 placeholder:text-zinc-600"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {groupedByProvider.map(([provider, profiles]) => (
            <div key={provider}>
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">{provider}</div>
              {profiles.map((profile) => {
                const needsKey = profileNeedsApiKey(profile);
                const badges = capabilityBadges(profile).slice(0, 4);
                return (
                  <button
                    key={profile.profile_id}
                    type="button"
                    draggable
                    disabled={isGenerating}
                    onDragStart={(event) => {
                      event.dataTransfer.setData(
                        "application/rumi-widget",
                        JSON.stringify({ id: profile.profile_id, type: "model", label: profile.display_name }),
                      );
                      event.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={() => {
                      onSelect(profile.profile_id);
                      onClose();
                    }}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-1.5 text-left transition-colors hover:bg-zinc-800/80 disabled:opacity-50 ${
                      selectedProfile?.profile_id === profile.profile_id ? "bg-zinc-800/60" : ""
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] text-zinc-200">{compactProfileName(profileDisplayName(profile))}</span>
                      <span className="block truncate text-[10px] text-zinc-500">
                        {profile.provider_display_name ?? profile.provider_id} · {profile.provider_id}/{profile.model_id}
                      </span>
                      {badges.length > 0 && (
                        <span className="mt-1 flex flex-wrap gap-1">
                          {badges.map((badge) => (
                            <span key={badge} className="rounded border border-zinc-700 px-1.5 py-0.5 text-[9px] leading-none text-zinc-400">
                              {badge}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                    {needsKey ? (
                      <span className="flex-shrink-0 rounded-full border border-amber-500/30 px-2 py-0.5 text-[10px] text-amber-300">
                        API key
                      </span>
                    ) : (
                      <span className="flex-shrink-0 text-right text-[10px] text-zinc-500">
                        <span className="block">{profile.max_context_tokens ?? profile.max_context ?? "?"}</span>
                        {typeof profile.knowledge_level === "number" && <span className="block">KL {profile.knowledge_level}</span>}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
          {groupedByProvider.length === 0 && (
            <div className="px-3 py-4 text-center text-xs text-zinc-500">モデルが見つかりません</div>
          )}
        </div>
      </div>
    </>
  );
}

function ModeSelector({
  mode,
  onModeChange,
  onClose,
}: {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  onClose: () => void;
}) {
  return (
    <>
      <button type="button" aria-label="close mode selector" className="fixed inset-0 z-20 cursor-default" onClick={onClose} />
      <div className="absolute bottom-full left-0 mb-2 z-50 w-[220px] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
        <div className="border-b border-zinc-800 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">モード選択</p>
        </div>
        <div className="py-1">
          {(Object.entries(MODE_META) as [AppMode, (typeof MODE_META)[AppMode]][]).map(([id, meta]) => {
            const Icon = meta.icon;
            return (
              <button
                key={id}
                type="button"
                onClick={() => {
                  onModeChange(id);
                  onClose();
                }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                  mode === id ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                }`}
              >
                <Icon size={15} />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{meta.label}</span>
                  <span className="block text-[10px] text-zinc-500">{meta.description}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

type ComposerAtMentionCandidate =
  | { kind: "tool"; id: string; label: string; description?: string; item: ComposerExtensionItem }
  | { kind: "skill"; id: string; label: string; description?: string; skill: ComposerSkillItem }
  | { kind: "file"; id: string; label: string; description?: string; file: string };

function AtMentionMenu({
  candidates,
  activeIndex,
  onActiveIndexChange,
  onSelect,
  onClose,
  style,
}: {
  candidates: ComposerAtMentionCandidate[];
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onSelect: (candidate: ComposerAtMentionCandidate) => void;
  onClose: () => void;
  style?: CSSProperties;
}) {
  if (candidates.length === 0) return null;

  return (
    <>
      <button type="button" aria-label="close mention menu" className="fixed inset-0 z-20 cursor-default" onClick={onClose} />
      <div
        role="listbox"
        aria-label="Composer mentions"
        data-testid="composer-at-mention-candidates"
        style={style}
        className="fixed z-50 w-[min(440px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl"
      >
        <div className="border-b border-zinc-800 px-3 py-2 flex items-center justify-between gap-2">
          <span className="inline-flex min-w-0 items-center gap-2">
            <Wrench size={13} className="text-zinc-500" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Mentions</span>
          </span>
          <span className="text-[10px] text-zinc-600">{candidates.length}</span>
        </div>
        <div className="max-h-56 overflow-y-auto py-1">
          {candidates.map((candidate, index) => {
            const Icon = candidate.kind === "tool" ? Wrench : candidate.kind === "skill" ? BrainCircuit : FileText;
            return (
            <button
              key={candidate.id}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => onActiveIndexChange(index)}
              onClick={() => onSelect(candidate)}
              className={`w-full flex items-center justify-between gap-3 px-3 py-2 text-left transition-colors ${
                index === activeIndex ? "bg-zinc-800 text-zinc-100" : "hover:bg-zinc-900"
              }`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Icon size={13} className="text-zinc-500 flex-shrink-0" />
                <span className="min-w-0">
                  <span className="block truncate text-[13px] text-zinc-200">@{candidate.label}</span>
                  {candidate.description && <span className="block truncate text-[10px] text-zinc-500">{candidate.description}</span>}
                </span>
              </span>
              <span className={`flex-shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] leading-none ${
                candidate.kind === "tool"
                  ? "border-emerald-500/25 text-emerald-300"
                  : candidate.kind === "skill"
                    ? "border-violet-500/25 text-violet-300"
                    : "border-sky-500/25 text-sky-300"
              }`}>
                {candidate.kind}
              </span>
            </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

export function filterAtMentionFiles(files: string[], query: string): string[] {
  if (!query) return files.slice(0, 20);
  const q = query.toLowerCase();
  return files.filter((file) => file.toLowerCase().includes(q)).slice(0, 20);
}

export function insertAtMentionText(input: string, cursorPos: number, file: string): { value: string; cursor: number } {
  const textBeforeCursor = input.slice(0, cursorPos);
  const atIndex = textBeforeCursor.lastIndexOf("@");
  const insertAt = atIndex >= 0 ? atIndex : cursorPos;
  const before = input.slice(0, insertAt);
  const after = input.slice(cursorPos);
  const value = `${before}@${file} ${after}`;
  return { value, cursor: insertAt + file.length + 2 };
}

export type ModelCandidateMenuKeyAction =
  | { handled: false }
  | { handled: true; type: "move"; nextIndex: number }
  | { handled: true; type: "select"; index: number }
  | { handled: true; type: "close" };

export function nextModelCandidateIndex(currentIndex: number, candidateCount: number, direction: 1 | -1): number {
  if (candidateCount <= 0) return 0;
  return (currentIndex + direction + candidateCount) % candidateCount;
}

export function modelCandidateMenuKeyAction(
  key: string,
  shiftKey: boolean,
  currentIndex: number,
  candidateCount: number,
): ModelCandidateMenuKeyAction {
  if (candidateCount <= 0) return { handled: false };
  if (key === "Tab" || key === "ArrowDown" || key === "ArrowUp") {
    const direction = key === "ArrowUp" || (key === "Tab" && shiftKey) ? -1 : 1;
    return {
      handled: true,
      type: "move",
      nextIndex: nextModelCandidateIndex(currentIndex, candidateCount, direction),
    };
  }
  if (key === "Enter") {
    return { handled: true, type: "select", index: Math.min(Math.max(currentIndex, 0), candidateCount - 1) };
  }
  if (key === "Escape") {
    return { handled: true, type: "close" };
  }
  return { handled: false };
}

export function shouldFocusComposerForSlashKey(
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "defaultPrevented" | "isComposing">,
  target: EventTarget | null,
): boolean {
  if (event.defaultPrevented || event.isComposing) return false;
  if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (typeof Element === "undefined") return true;
  if (!(target instanceof Element)) return true;
  const tagName = target.tagName.toLowerCase();
  return tagName !== "input" && tagName !== "textarea" && tagName !== "select" && !target.closest("[contenteditable='true']");
}

function modelCandidateTitle(candidate: ModelCommandCandidate): string {
  return String(candidate.display_name ?? candidate.profile_id ?? "model");
}

function modelCandidateSubtitle(candidate: ModelCommandCandidate): string {
  const explicit = String(candidate.subtitle ?? "").trim();
  if (explicit) return explicit;
  const provider = String(candidate.provider_display_name ?? candidate.provider_id ?? "").trim();
  const model = String(candidate.model_id ?? candidate.qualified_model_id ?? candidate.profile_id ?? "").trim();
  return [provider, model].filter(Boolean).join(" / ");
}

function modelCandidateApiKeyBadge(candidate: ModelCommandCandidate): string | null {
  if (candidate.requires_api_key === true || candidate.api_key_required === true) return "API key";
  if (candidate.api_key_configured === true || candidate.configured === true) return "key set";
  const availability = candidate.availability ?? {};
  if (availability.configured === true || availability.status === "configured" || availability.status === "active") return "key set";
  return null;
}

function ModelCommandCandidatePopup({
  candidates,
  activeIndex,
  onActiveIndexChange,
  onSelect,
  onClose,
  style,
}: {
  candidates: ModelCommandCandidate[];
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onSelect: (candidate: ModelCommandCandidate) => void;
  onClose?: () => void;
  style?: CSSProperties;
}) {
  if (candidates.length === 0) return null;

  return (
    <div
      role="listbox"
      aria-label="Model candidates"
      style={style}
      className="fixed z-50 w-[min(460px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl"
    >
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Models</span>
        {onClose && (
          <button
            type="button"
            aria-label="close model candidates"
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200"
          >
            <X size={13} />
          </button>
        )}
      </div>
      <div className="max-h-64 overflow-y-auto py-1">
        {candidates.map((candidate, index) => {
          const badge = modelCandidateApiKeyBadge(candidate);
          return (
            <button
              key={candidate.profile_id}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => onActiveIndexChange(index)}
              onClick={() => onSelect(candidate)}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors ${
                index === activeIndex ? "bg-zinc-800 text-zinc-100" : "hover:bg-zinc-900"
              }`}
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-zinc-100">{modelCandidateTitle(candidate)}</span>
                <span className="block truncate text-[11px] text-zinc-500">{modelCandidateSubtitle(candidate)}</span>
              </span>
              {badge && (
                <span
                  className={`flex-shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${
                    badge === "API key"
                      ? "border-amber-500/30 text-amber-300"
                      : "border-emerald-500/25 text-emerald-300"
                  }`}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
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
  modelProfiles = [],
  thinkingLevel,
  contextUsage,
  inlineExtensions,
  belowExtensions,
  skillExtensions = [],
  commands = [],
  modelCommandCandidates = [],
  modelPickerRequestId = 0,
  yoloMode = false,
  voiceInputEnabled = true,
  voiceInputUseAi = false,
  mode = "chat",
  codingContext = null,
  codingWorkspaces = [],
  selectedCodingWorkspaceId = null,
  attachedFiles = [],
  droppedWidgets = [],
  selectedToolIds = [],
  keyboardButtonNavigation = false,
  steerStatus = null,
  steerBusy = false,
  steerQueuedCount = 0,
  steerPreviewItems = [],
  suppressPopovers = false,
  onOpenModelManager,
  onOpenToolSettings,
  onSwitchToVisionModel,
  onExtensionSelect,
  onCommandSelect,
  onModelCommandCandidateSelect,
  onModelCommandCandidatesClose,
  onModelProfileSelect,
  onProviderApiKeySave,
  onThinkingLevelChange,
  onInputChange,
  onSubmit,
  onStopGenerating,
  onSteerSubmit,
  onModeChange,
  onFileAttach,
  onAtFileAttach,
  onFileRemove,
  onDropWidget,
  onWidgetAction,
  onWidgetToggle,
  onCodingBranchSwitch,
  onCodingDirectoryChange,
  onCodingWorkspaceSelect,
  onCodingWorkspaceTrust,
  onCodingWorkspaceCreate,
  onCodingWorkspacesRefresh,
  onCodingContextRefresh,
}: ComposerRendererProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [openFolder, setOpenFolder] = useState<"tools" | "models" | "commands">("tools");
  const [openToolGroup, setOpenToolGroup] = useState<string | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [apiKeyPromptProfile, setApiKeyPromptProfile] = useState<ModelProfile | null>(null);
  const [locallyConfiguredProviders, setLocallyConfiguredProviders] = useState<Set<string>>(() => new Set());
  const [modeSelectorOpen, setModeSelectorOpen] = useState(false);
  const [atMentionOpen, setAtMentionOpen] = useState(false);
  const [atMentionQuery, setAtMentionQuery] = useState("");
  const [selectedAtMentionIndex, setSelectedAtMentionIndex] = useState(0);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [selectedModelCandidateIndex, setSelectedModelCandidateIndex] = useState(0);
  const [composerPopoverStyle, setComposerPopoverStyle] = useState<CSSProperties | undefined>(undefined);
  const [isVoiceListening, setIsVoiceListening] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);
  const submitPointerHandledRef = useRef(false);
  const lastModelPickerRequestIdRef = useRef(modelPickerRequestId);
  const chromeButtonTabIndex = keyboardButtonNavigation ? undefined : -1;
  const profileName = profileDisplayName(selectedProfile);
  const selectedProviderLabel = profileProviderLabel(selectedProfile);
  const levels = selectedProfile?.supports_thinking
    ? selectedProfile.thinking_levels?.length
      ? selectedProfile.thinking_levels
      : ["low", "medium", "high"]
    : [];
  const contextDegrees = Math.round(contextUsage.ratio * 360);
  const contextTitle =
    contextUsage.maxContext < 0
      ? `${contextUsage.usedTokens} tokens / unlimited`
      : `${contextUsage.usedTokens} / ${contextUsage.maxContext || "unknown"} tokens`;
  const toolItems = useMemo(() => [...inlineExtensions, ...belowExtensions], [inlineExtensions, belowExtensions]);
  const selectableProfiles = modelProfiles.length > 0 ? modelProfiles : favoriteProfiles;
  const selectedToolIdSet = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);
  const computerUseSelected = selectedToolIds.some((toolId) => (
    toolId === "computer_use"
    || toolId === "browser_computer"
    || toolId === "browser_use"
    || toolId === "browser_companion"
  ));
  const hasAttachedImages = attachedFiles.some((file) => String(file.type ?? "").startsWith("image/"));
  const imageBridgePlanned = hasAttachedImages && !selectedProfile?.supports_vision && !selectedProfile?.supports_image_input;
  const toolGroups = useMemo(() => groupToolItems(toolItems), [toolItems]);
  const activeToolGroup = toolGroups.find((group) => group.id === openToolGroup) ?? toolGroups[0] ?? null;
  const showToolGroups = toolItems.length > 4;
  const isEscapedSlash = input.startsWith("//");
  const isSteerMode = isGenerating && !isNewConversation;
  const slashText = !isSteerMode && input.startsWith("/") && !isEscapedSlash ? input.slice(1) : "";
  const slashCommandName = slashText.trimStart().split(/\s+/, 1)[0] ?? "";
  const slashQuery = slashCommandName.toLowerCase();
  const thinkingCommand = commands.find((command) => command.id === "think");
  const thinkingMatch = !isSteerMode && input.startsWith("/") && !isEscapedSlash ? thinkingCommandMatch(input) : null;
  const matchedCommands = !isSteerMode && input.startsWith("/") && !isEscapedSlash
    ? thinkingMatch && thinkingCommand && levels.length > 0
      ? levels
          .filter((level) => !thinkingMatch.query || level.toLowerCase().includes(thinkingMatch.query))
          .map((level) => ({
            ...thinkingCommand,
            id: `think:${level}`,
            name: `think ${level}`,
            label: `Thinking ${THINKING_LABELS[level] ?? level}`,
            description: `思考レベルを ${THINKING_LABELS[level] ?? level} に変更`,
          }))
      : commands.filter((command) => {
          const haystack = `${command.id} ${command.name} ${(command.aliases ?? []).join(" ")} ${command.label} ${command.description ?? ""}`.toLowerCase();
          return !slashQuery || haystack.includes(slashQuery);
        })
    : [];
  const showThinkingLevelChips = Boolean(thinkingMatch && thinkingCommand && levels.length > 0);
  const hasModelCommandCandidates = !isSteerMode && modelCommandCandidates.length > 0;
  const showCommandSuggestions = !hasModelCommandCandidates && matchedCommands.length > 0;
  const visibleSteerPreviewItems = steerPreviewItems.filter((item) => (
    item.visible !== false && String(item.prompt ?? "").trim()
  ));
  const currentModeMeta = MODE_META[mode];
  const ModeIcon = currentModeMeta.icon;
  const directoryEntries = (codingContext?.entries ?? []).filter((entry) => entry.is_dir);
  const branchOptions = codingContext?.branches?.length ? codingContext.branches : codingContext?.branch ? [codingContext.branch] : [];
  const currentDirectory = codingContext?.directory || ".";
  const selectedCodingWorkspace = codingWorkspaces.find((workspace) => workspace.workspace_id === (selectedCodingWorkspaceId || codingContext?.workspaceId)) ?? codingWorkspaces[0] ?? null;
  const atMentionCandidates = useMemo<ComposerAtMentionCandidate[]>(() => {
    const toolCandidates = filterComposerToolMentions(toolItems, atMentionQuery, 14).map((item) => ({
      kind: "tool" as const,
      id: `tool:${item.id}`,
      label: item.id,
      description: item.description ?? item.label,
      item,
    }));
    const skillCandidates = filterComposerSkillMentions(skillExtensions, atMentionQuery, 8).map((skill) => ({
      kind: "skill" as const,
      id: `skill:${skill.id}`,
      label: skill.id,
      description: skill.description ?? skill.label,
      skill,
    }));
    const fileCandidates = mode === "coding"
      ? filterAtMentionFiles(codingContext?.files ?? [], atMentionQuery).slice(0, 8).map((file) => ({
          kind: "file" as const,
          id: `file:${file}`,
          label: file,
          description: "workspace file",
          file,
        }))
      : [];
    return [...toolCandidates, ...skillCandidates, ...fileCandidates];
  }, [atMentionQuery, codingContext?.files, mode, skillExtensions, toolItems]);

  const needsApiKey = useCallback(
    (profile: ModelProfile | null | undefined) => (
      profileNeedsApiKey(profile) && !locallyConfiguredProviders.has(profileProviderId(profile))
    ),
    [locallyConfiguredProviders],
  );

  const updateComposerPopoverAnchor = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || typeof window === "undefined") return;
    const rect = textarea.getBoundingClientRect();
    const width = Math.min(460, Math.max(260, window.innerWidth - 16));
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const top = Math.max(8, rect.top - 8);
    setComposerPopoverStyle({
      left,
      top,
      width,
      transform: "translateY(-100%)",
    });
  }, []);

  const requestModelProfileSelect = useCallback(
    (profileId: string) => {
      const profile = selectableProfiles.find((item) => (
        item.profile_id === profileId
        || item.qualified_model_id === profileId
        || `${item.provider_id}/${item.model_id}` === profileId
      ));
      if (profile && needsApiKey(profile)) {
        setApiKeyPromptProfile(profile);
        setModelDropdownOpen(false);
        setMenuOpen(false);
        return;
      }
      onModelProfileSelect(profileId);
    },
    [needsApiKey, onModelProfileSelect, selectableProfiles],
  );

  const saveProviderApiKey = useCallback(
    async (providerId: string, value: string) => {
      if (!apiKeyPromptProfile) return;
      if (!onProviderApiKeySave) {
        throw new Error("この provider の API key 保存に対応していません。");
      }
      await onProviderApiKeySave(providerId, value);
      setLocallyConfiguredProviders((current) => new Set(current).add(providerId));
      const selectedId = apiKeyPromptProfile.profile_id || apiKeyPromptProfile.qualified_model_id || `${apiKeyPromptProfile.provider_id}/${apiKeyPromptProfile.model_id}`;
      setApiKeyPromptProfile(null);
      onModelProfileSelect(selectedId);
    },
    [apiKeyPromptProfile, onModelProfileSelect, onProviderApiKeySave],
  );

  useEffect(() => {
    if (!menuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target) || menuButtonRef.current?.contains(target)) return;
      setMenuOpen(false);
    };

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleDocumentKeyDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    setSelectedCommandIndex((current) => {
      if (matchedCommands.length === 0) return 0;
      return Math.min(current, matchedCommands.length - 1);
    });
  }, [matchedCommands.length]);

  useEffect(() => {
    setSelectedAtMentionIndex((current) => {
      if (atMentionCandidates.length === 0) return 0;
      return Math.min(current, atMentionCandidates.length - 1);
    });
  }, [atMentionCandidates.length]);

  useEffect(() => {
    setSelectedModelCandidateIndex((current) => {
      if (modelCommandCandidates.length === 0) return 0;
      return Math.min(current, modelCommandCandidates.length - 1);
    });
    if (modelCommandCandidates.length > 0) {
      setModelDropdownOpen(false);
      setMenuOpen(false);
    }
  }, [modelCommandCandidates.length]);

  useEffect(() => {
    if (modelPickerRequestId === lastModelPickerRequestIdRef.current) return;
    lastModelPickerRequestIdRef.current = modelPickerRequestId;
    if (modelPickerRequestId <= 0) return;
    setMenuOpen(false);
    setModelDropdownOpen(true);
    window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 0);
  }, [modelPickerRequestId]);

  useEffect(() => {
    if (!suppressPopovers) return;
    setMenuOpen(false);
    setAtMentionOpen(false);
    setModelDropdownOpen(false);
    setModeSelectorOpen(false);
    onModelCommandCandidatesClose?.();
  }, [onModelCommandCandidatesClose, suppressPopovers]);

  useEffect(() => {
    if (!atMentionOpen && !hasModelCommandCandidates) return;
    updateComposerPopoverAnchor();
    window.addEventListener("resize", updateComposerPopoverAnchor);
    window.addEventListener("scroll", updateComposerPopoverAnchor, true);
    return () => {
      window.removeEventListener("resize", updateComposerPopoverAnchor);
      window.removeEventListener("scroll", updateComposerPopoverAnchor, true);
    };
  }, [atMentionOpen, hasModelCommandCandidates, updateComposerPopoverAnchor]);

  useEffect(() => {
    textareaRef.current?.focus({ preventScroll: true });
    const focusTimer = window.setTimeout(() => {
      textareaRef.current?.focus({ preventScroll: true });
    }, 80);
    return () => window.clearTimeout(focusTimer);
  }, []);

  useEffect(() => {
    const handleDocumentSlashFocus = (event: KeyboardEvent) => {
      if (isGenerating || !shouldFocusComposerForSlashKey(event, event.target)) return;
      event.preventDefault();
      const textarea = textareaRef.current;
      if (!textarea) return;
      if (!input.trim()) {
        onInputChange("/");
        window.setTimeout(() => {
          textarea.focus({ preventScroll: true });
          textarea.setSelectionRange(1, 1);
        }, 0);
        return;
      }
      textarea.focus({ preventScroll: true });
    };

    document.addEventListener("keydown", handleDocumentSlashFocus);
    return () => document.removeEventListener("keydown", handleDocumentSlashFocus);
  }, [input, isGenerating, onInputChange]);

  const chooseCommand = (commandId: string, rawInput = input) => {
    const thinkingLevelMatch = commandId.match(/^think:(.+)$/);
    if (thinkingLevelMatch) {
      onCommandSelect?.("think", `/think ${thinkingLevelMatch[1]}`);
      onInputChange("");
      return;
    }

    const command = commands.find((item) => item.id === commandId);
    const action = command?.execution.type === "frontend" ? command.execution.action : "";
    const rawHasArgs = rawInput.trim().includes(" ");
    if (command?.id === "think") {
      onInputChange("/think ");
      window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 0);
      return;
    }
    if (action === "open_model_picker" && !rawHasArgs) {
      setModelDropdownOpen(true);
      setMenuOpen(false);
    } else if (action === "open_tool_picker" && !rawHasArgs) {
      setOpenFolder("tools");
      setMenuOpen(true);
    } else if (action === "open_command_help") {
      setOpenFolder("commands");
      setMenuOpen(true);
    }
    onCommandSelect?.(commandId, rawInput);
    if (!(command?.id === "model" && rawHasArgs)) {
      onInputChange("");
    }
  };

  const chooseModelCommandCandidate = useCallback(
    (candidate: ModelCommandCandidate | undefined) => {
      if (!candidate) return;
      onModelCommandCandidateSelect?.(candidate);
    },
    [onModelCommandCandidateSelect],
  );

  const updateAtMentionStateFromInput = useCallback(
    (value: string) => {
      const textarea = textareaRef.current;
      if (!textarea || suppressPopovers) return;
      const cursorPos = textarea.selectionStart ?? value.length;
      const textBeforeCursor = value.slice(0, cursorPos);
      const atMatch = textBeforeCursor.match(/(?:^|\s)@([^\s@]*)$/);
      const hasMentionTargets = toolItems.length > 0 || skillExtensions.length > 0 || (mode === "coding" && Boolean(codingContext?.files?.length));

      if (atMatch && !isSteerMode && hasMentionTargets) {
        setAtMentionOpen(true);
        setAtMentionQuery(atMatch[1]);
        updateComposerPopoverAnchor();
      } else {
        setAtMentionOpen(false);
        setAtMentionQuery("");
      }
    },
    [codingContext?.files?.length, isSteerMode, mode, skillExtensions.length, suppressPopovers, toolItems.length, updateComposerPopoverAnchor],
  );

  useEffect(() => {
    updateAtMentionStateFromInput(input);
  }, [input, updateAtMentionStateFromInput]);

  const handleInputChange = useCallback(
    (value: string) => {
      onInputChange(value);
      updateAtMentionStateFromInput(value);

      if (!value.startsWith("/") || value.startsWith("//")) {
        setSelectedCommandIndex(0);
      }
    },
    [onInputChange, updateAtMentionStateFromInput],
  );

  const handleAtMentionSelect = useCallback(
    (candidate: ComposerAtMentionCandidate) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const cursorPos = textarea.selectionStart;
      const mentionText = candidate.kind === "tool" ? candidate.item.id : candidate.kind === "skill" ? candidate.skill.id : candidate.file;
      const next = insertAtMentionText(input, cursorPos, mentionText);
      onInputChange(next.value);
      if (candidate.kind === "tool") {
        onDropWidget?.(composerToolMentionWidget(candidate.item));
      } else if (candidate.kind === "skill") {
        onDropWidget?.(composerSkillMentionWidget(candidate.skill));
      } else if (mode === "coding") {
        onAtFileAttach?.(candidate.file);
      }
      setAtMentionOpen(false);
      setAtMentionQuery("");

      setTimeout(() => {
        textarea.setSelectionRange(next.cursor, next.cursor);
        textarea.focus();
      }, 0);
    },
    [input, mode, onAtFileAttach, onDropWidget, onInputChange],
  );

  const attachFiles = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    const newFiles: AttachedFile[] = await Promise.all(Array.from(files).map(fileToAttachment));
    onFileAttach?.(newFiles);
  }, [onFileAttach]);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (event.dataTransfer.files.length > 0) {
        void attachFiles(event.dataTransfer.files);
        return;
      }

      const historyData = event.dataTransfer.getData(HISTORY_CHAT_DROP_MIME);
      if (historyData) {
        const widget = parseHistoryChatDrop(historyData);
        if (widget) onDropWidget?.(widget);
        return;
      }

      const data = event.dataTransfer.getData("application/rumi-widget");
      if (data) {
        try {
          const widget: DroppedWidget = JSON.parse(data);
          const action = resolveComposerWidgetDrop(widget, toolItems);
          if (action.type === "drop_widget") {
            onDropWidget?.(action.widget);
          } else if (action.type === "select_model") {
            requestModelProfileSelect(action.profileId);
            setModelDropdownOpen(false);
            setMenuOpen(false);
          }
        } catch {
          // invalid drop data
        }
      }
    },
    [attachFiles, onDropWidget, requestModelProfileSelect, toolItems],
  );

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const handleSubmitWithApiKeyGuard = useCallback(
    (event: React.SyntheticEvent) => {
      if (isGenerating) {
        event.preventDefault();
        const prompt = input.trim();
        if (prompt && !steerBusy) {
          onSteerSubmit?.(prompt);
        } else if (!prompt) {
          onStopGenerating?.();
        }
        return;
      }
      if (needsApiKey(selectedProfile)) {
        event.preventDefault();
        if (selectedProfile) setApiKeyPromptProfile(selectedProfile);
        return;
      }
      onSubmit(event);
    },
    [input, isGenerating, needsApiKey, onStopGenerating, onSteerSubmit, onSubmit, selectedProfile, steerBusy],
  );

  const handleSendButtonPointerDown = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      if (event.button !== 0) return;
      if (!isGenerating && !input.trim() && attachedFiles.length === 0) return;
      if (isGenerating && !input.trim()) return;
      submitPointerHandledRef.current = true;
      handleSubmitWithApiKeyGuard(event);
    },
    [attachedFiles.length, handleSubmitWithApiKeyGuard, input, isGenerating],
  );

  const handleSendButtonClick = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      if (submitPointerHandledRef.current) {
        submitPointerHandledRef.current = false;
        event.preventDefault();
        return;
      }
      if (isGenerating) {
        event.preventDefault();
        if (input.trim()) {
          handleSubmitWithApiKeyGuard(event);
        } else {
          onStopGenerating?.();
        }
        return;
      }
      handleSubmitWithApiKeyGuard(event);
    },
    [handleSubmitWithApiKeyGuard, input, isGenerating, onStopGenerating],
  );

  const toggleVoiceInput = useCallback(() => {
    if (!voiceInputEnabled || isGenerating) return;
    if (isVoiceListening) {
      recognitionRef.current?.stop();
      setIsVoiceListening(false);
      return;
    }
    const recognitionCtor = (window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    }).SpeechRecognition ?? (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;
    if (!recognitionCtor) return;
    const recognition = new recognitionCtor();
    recognition.lang = "ja-JP";
    recognition.continuous = false;
    recognition.interimResults = true;
    let finalTranscript = "";
    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result?.[0]?.transcript ?? "";
        if (result?.isFinal) finalTranscript += text;
        else interim += text;
      }
      const transcript = `${finalTranscript}${interim}`.trim();
      if (!transcript) return;
      const prefix = voiceInputUseAi ? "文字起こしして: " : "";
      const base = input.trimEnd();
      onInputChange(`${base}${base ? "\n" : ""}${prefix}${transcript}`);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setIsVoiceListening(false);
      window.setTimeout(() => textareaRef.current?.focus({ preventScroll: true }), 0);
    };
    recognitionRef.current = recognition;
    setIsVoiceListening(true);
    recognition.start();
  }, [input, isGenerating, isVoiceListening, onInputChange, voiceInputEnabled, voiceInputUseAi]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
        event.stopPropagation();
        return;
      }

      if (atMentionOpen) {
        if (event.key === "Escape") {
          event.preventDefault();
          setAtMentionOpen(false);
          return;
        }
        if (atMentionCandidates.length > 0 && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
          event.preventDefault();
          const direction = event.key === "ArrowUp" ? -1 : 1;
          setSelectedAtMentionIndex((current) => nextModelCandidateIndex(current, atMentionCandidates.length, direction));
          return;
        }
        if (atMentionCandidates.length > 0 && (event.key === "Tab" || event.key === "Enter")) {
          event.preventDefault();
          handleAtMentionSelect(atMentionCandidates[Math.min(selectedAtMentionIndex, atMentionCandidates.length - 1)]);
          return;
        }
      }

      const modelCandidateAction = isSteerMode
        ? { handled: false as const }
        : modelCandidateMenuKeyAction(
            event.key,
            event.shiftKey,
            selectedModelCandidateIndex,
            modelCommandCandidates.length,
          );
      if (modelCandidateAction.handled) {
        event.preventDefault();
        if (modelCandidateAction.type === "move") {
          setSelectedModelCandidateIndex(modelCandidateAction.nextIndex);
        } else if (modelCandidateAction.type === "select") {
          chooseModelCommandCandidate(modelCommandCandidates[modelCandidateAction.index]);
        } else if (modelCandidateAction.type === "close") {
          onModelCommandCandidatesClose?.();
        }
        return;
      }

      if (event.key === "Enter" && !event.shiftKey && isSteerMode) {
        event.preventDefault();
        handleSubmitWithApiKeyGuard(event);
        return;
      }

      if (matchedCommands.length > 0) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setSelectedCommandIndex((current) => (current + 1) % matchedCommands.length);
          return;
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          setSelectedCommandIndex((current) => (current - 1 + matchedCommands.length) % matchedCommands.length);
          return;
        }
        if (event.key === "Tab" || event.key === "Enter") {
          event.preventDefault();
          chooseCommand(matchedCommands[selectedCommandIndex]?.id ?? matchedCommands[0].id);
          return;
        }
      }

      if (event.key === "Tab" && !keyboardButtonNavigation) {
        event.preventDefault();
        return;
      }

      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSubmitWithApiKeyGuard(event);
      }
    },
    [
      atMentionCandidates,
      atMentionOpen,
      chooseModelCommandCandidate,
      handleAtMentionSelect,
      handleSubmitWithApiKeyGuard,
      isSteerMode,
      matchedCommands,
      modelCommandCandidates,
      onModelCommandCandidatesClose,
      keyboardButtonNavigation,
      selectedAtMentionIndex,
      selectedCommandIndex,
      selectedModelCandidateIndex,
    ],
  );

  const chromeWidgets: ComposerChromeWidgetSpec[] = [
    {
      id: "menu",
      slot: "leading",
      order: 10,
      width: COMPOSER_CHROME_WIDTHS.icon,
      render: () => (
        <button
          ref={menuButtonRef}
          type="button"
          tabIndex={chromeButtonTabIndex}
          disabled={isGenerating}
          title="追加"
          onClick={() => setMenuOpen((value) => !value)}
          className="h-8 w-8 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60 rounded-lg transition-colors disabled:opacity-50"
        >
          <WarmActionIcon kind="menu" size="md" />
        </button>
      ),
    },
    {
      id: "file-attach",
      slot: "leading",
      order: 20,
      width: COMPOSER_CHROME_WIDTHS.icon,
      render: () => (
        <button
          type="button"
          tabIndex={chromeButtonTabIndex}
          disabled={isGenerating}
          title="ファイル添付（複数選択可）"
          onClick={() => fileInputRef.current?.click()}
          className={`${
            isNewConversation
              ? "border border-zinc-700/70 bg-zinc-900/30 text-zinc-300 hover:border-zinc-600 hover:bg-zinc-800/70"
              : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60"
          } h-8 w-8 flex flex-shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-50`}
        >
          <WarmActionIcon kind="attach" size="md" />
        </button>
      ),
    },
    {
      id: "voice-input",
      slot: "leading",
      order: 30,
      mobile: "hide",
      width: COMPOSER_CHROME_WIDTHS.icon,
      render: () => (
        <button
          type="button"
          tabIndex={chromeButtonTabIndex}
          disabled={isGenerating || !voiceInputEnabled}
          title={isVoiceListening ? "音声入力を停止" : voiceInputUseAi ? "音声入力（AI文字起こし）" : "音声入力"}
          onClick={toggleVoiceInput}
          className={`h-8 w-8 flex flex-shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-50 ${
            isVoiceListening ? "bg-rose-500/15 text-rose-300 hover:bg-rose-500/25" : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60"
          }`}
        >
          <WarmActionIcon kind="mic" size="md" />
        </button>
      ),
    },
    {
      id: "mode",
      slot: "leading",
      order: 40,
      width: COMPOSER_CHROME_WIDTHS.mode,
      render: () => (
        <div className="group/mode relative flex min-w-0 max-w-full">
          <button
            type="button"
            tabIndex={chromeButtonTabIndex}
            disabled={isGenerating}
            title={`モード: ${currentModeMeta.label}`}
            onClick={() => setModeSelectorOpen((v) => !v)}
            className={`h-8 flex min-w-0 flex-shrink-0 items-center gap-1.5 rounded-lg px-2.5 transition-colors disabled:opacity-50 ${
              mode === "coding"
                ? "text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30"
                : mode === "agent"
                  ? "text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/30"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60"
            }`}
          >
            <ModeIcon size={14} className="flex-shrink-0" />
            <span className="truncate text-[11px] font-medium max-[640px]:hidden">{currentModeMeta.label}</span>
          </button>
          {mode !== "chat" && (
            <button
              type="button"
              tabIndex={chromeButtonTabIndex}
              aria-label="モードを閉じる"
              title="Chat に戻す"
              onClick={(event) => {
                event.stopPropagation();
                setModeSelectorOpen(false);
                onModeChange?.("chat");
              }}
              className="absolute -right-1 -top-1 hidden h-4 w-4 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-400 shadow-sm hover:bg-zinc-800 hover:text-zinc-100 group-hover/mode:flex"
            >
              <X size={10} />
            </button>
          )}
          {modeSelectorOpen && (
            <ModeSelector
              mode={mode}
              onModeChange={(m) => onModeChange?.(m)}
              onClose={() => setModeSelectorOpen(false)}
            />
          )}
        </div>
      ),
    },
    {
      id: "yolo-status",
      slot: "leading",
      order: 50,
      visible: yoloMode,
      width: COMPOSER_CHROME_WIDTHS.badge,
      className: "overflow-hidden",
      render: () => (
        <span className="rounded-full border border-orange-500/30 px-2 py-0.5 text-[11px] text-orange-300">
          YOLO
        </span>
      ),
    },
    {
      id: "computer-use-status",
      slot: "leading",
      order: 60,
      visible: computerUseSelected,
      width: COMPOSER_CHROME_WIDTHS.badge,
      className: "overflow-hidden",
      render: () => (
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
          <MousePointerClick size={12} className="flex-shrink-0" />
          <span className="truncate">Computer ON</span>
        </span>
      ),
    },
    {
      id: "vision-bridge-status",
      slot: "leading",
      order: 70,
      visible: imageBridgePlanned,
      width: COMPOSER_CHROME_WIDTHS.badge,
      className: "overflow-hidden",
      render: () => (
        <span className="inline-flex items-center rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-300">
          <span className="truncate">Vision Bridge</span>
        </span>
      ),
    },
    {
      id: "model-control",
      slot: "trailing",
      order: 10,
      mobile: "hide",
      width: COMPOSER_CHROME_WIDTHS.model,
      className: "rumi-model-control",
      render: () => (
        <div className="rumi-model-control flex w-full min-w-0 items-center gap-1.5 bg-zinc-800/40 rounded-lg px-2.5 py-1 border border-zinc-700/40">
          <div
            title={contextTitle}
            className="h-3.5 w-3.5 flex-shrink-0 rounded-full p-[2px]"
            style={{
              background: `conic-gradient(#a1a1aa ${contextDegrees}deg, #52525b ${contextDegrees}deg)`,
            }}
          >
            <div className="h-full w-full rounded-full bg-zinc-800" />
          </div>
          <div className="relative min-w-0 max-w-full flex-1">
            <button
              type="button"
              tabIndex={chromeButtonTabIndex}
              disabled={isGenerating}
              onClick={() => setModelDropdownOpen((v) => !v)}
              className="flex w-full min-w-0 items-center gap-1 text-[12px] font-medium text-zinc-300 hover:text-zinc-100 transition-colors disabled:opacity-50"
            >
              <span className="min-w-0 flex-1 truncate">{compactProfileName(profileName)}</span>
              <ChevronDown size={12} className={`flex-shrink-0 transition-transform ${modelDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            <span className="block truncate text-[10px] leading-none text-zinc-500">
              {modelRouteReason(selectedProfile) || selectedProviderLabel}
            </span>
            {modelDropdownOpen && (
              <ModelDropdown
                profiles={selectableProfiles}
                selectedProfile={selectedProfile}
                isGenerating={isGenerating}
                onSelect={requestModelProfileSelect}
                onClose={() => setModelDropdownOpen(false)}
              />
            )}
          </div>
          {levels.length > 0 && (
            <label className="inline-flex flex-shrink-0 items-center border-l border-zinc-700/50 pl-1.5 ml-0.5 text-[11px] font-medium text-zinc-500">
              <select
                value={thinkingLevel ?? levels[0]}
                onChange={(event) => onThinkingLevelChange(event.target.value)}
                disabled={isGenerating}
                tabIndex={chromeButtonTabIndex}
                className="bg-transparent text-[11px] font-medium text-zinc-400 outline-none cursor-pointer hover:text-zinc-200 transition-colors disabled:opacity-50"
                aria-label="Thinking level"
                title="Thinking level"
              >
                {levels.map((level) => (
                  <option key={level} value={level} className="bg-zinc-900 text-zinc-100">
                    {THINKING_LABELS[level] ?? level}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      ),
    },
    {
      id: "send",
      slot: "trailing",
      order: 20,
      width: isNewConversation ? COMPOSER_CHROME_WIDTHS.sendLarge : COMPOSER_CHROME_WIDTHS.send,
      render: () => (
        <button
          type="button"
          tabIndex={chromeButtonTabIndex}
          disabled={!isGenerating && (!input.trim() && attachedFiles.length === 0)}
          onPointerDown={handleSendButtonPointerDown}
          onClick={handleSendButtonClick}
          title={isGenerating ? (input.trim() ? "ステアを送る" : "停止") : "送信"}
          className={`rumi-send-button ${
            isNewConversation ? "h-9 w-9" : "w-8 h-8 max-[640px]:h-7 max-[640px]:w-7"
          } flex flex-shrink-0 items-center justify-center bg-zinc-200 text-black rounded-lg disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white shadow-sm transition-colors`}
        >
          {isGenerating && !input.trim() ? (
            <WarmActionIcon kind="stop" size={isNewConversation ? "lg" : "md"} className="shadow-none ring-0" />
          ) : isGenerating ? (
            <CornerDownRight size={15} strokeWidth={2.4} />
          ) : (
            <WarmActionIcon kind="send" size={isNewConversation ? "lg" : "md"} className="shadow-none ring-0" />
          )}
        </button>
      ),
    },
  ];

  return (
    <div
      className={`${isNewConversation ? "w-full px-5" : "px-5 pb-5 pt-2 bg-[#09090b] flex-shrink-0 max-[640px]:px-2 max-[640px]:pb-2"}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className={`rumi-composer-shell ${isNewConversation ? "rumi-composer-shell-new mx-auto" : "mx-auto"}`}>
        <RuntimeCapabilityBanner
          visible={imageBridgePlanned}
          onSwitchToVisionModel={onSwitchToVisionModel}
          onOpenModelManager={onOpenModelManager}
          onOpenToolSettings={onOpenToolSettings}
        />
        <form
          onSubmit={handleSubmitWithApiKeyGuard}
          className={`rumi-composer-frame ${
            isNewConversation
              ? "rumi-composer-new min-h-[154px] rounded-3xl border-zinc-700/70 bg-[#242423]"
              : "rounded-xl border-zinc-700/30 bg-[#2b2b2d] max-[640px]:rounded-xl"
          } relative flex flex-col border overflow-visible shadow-2xl shadow-black/20 focus-within:border-zinc-500/60`}
        >
          {apiKeyPromptProfile && (
            <ProviderApiKeyPrompt
              profile={apiKeyPromptProfile}
              onCancel={() => setApiKeyPromptProfile(null)}
              onSave={saveProviderApiKey}
            />
          )}
          {hasModelCommandCandidates && (
            <ModelCommandCandidatePopup
              candidates={modelCommandCandidates}
              activeIndex={selectedModelCandidateIndex}
              onActiveIndexChange={setSelectedModelCandidateIndex}
              onSelect={chooseModelCommandCandidate}
              onClose={onModelCommandCandidatesClose}
              style={composerPopoverStyle}
            />
          )}
          {showCommandSuggestions && (
            showThinkingLevelChips ? (
              <div className="absolute bottom-full left-4 z-40 mb-2 flex w-[min(520px,calc(100vw-32px))] flex-wrap items-center gap-2 rounded-xl border border-zinc-700/70 bg-zinc-950/95 px-3 py-2 shadow-2xl">
                <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Thinking</span>
                {matchedCommands.map((command, index) => {
                  const level = command.id.replace(/^think:/, "");
                          return (
                            <button
                              key={command.id}
                              type="button"
                              tabIndex={chromeButtonTabIndex}
                              onMouseEnter={() => setSelectedCommandIndex(index)}
                              onClick={() => chooseCommand(command.id)}
                      className={`h-8 rounded-lg border px-3 text-xs font-medium transition-colors ${
                        index === selectedCommandIndex
                          ? "border-zinc-400 bg-zinc-100 text-zinc-950"
                          : "border-zinc-700 bg-zinc-900 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
                      }`}
                    >
                      {THINKING_LABELS[level] ?? level}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="absolute bottom-full left-4 z-40 mb-2 w-[min(420px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
                <div className="border-b border-zinc-800 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Commands
                </div>
                <div className="max-h-56 overflow-y-auto py-1">
                          {matchedCommands.map((command, index) => (
                            <button
                              key={command.id}
                              type="button"
                              tabIndex={chromeButtonTabIndex}
                              onMouseEnter={() => setSelectedCommandIndex(index)}
                              onClick={() => chooseCommand(command.id)}
                      className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left ${
                        index === selectedCommandIndex ? "bg-zinc-800 text-zinc-100" : "hover:bg-zinc-900"
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-zinc-100">/{command.name ?? command.id}</span>
                        {command.description && (
                          <span className="block truncate text-[11px] text-zinc-500">{command.description}</span>
                        )}
                      </span>
                      <span className="flex flex-shrink-0 items-center gap-1">
                        {command.risk && (
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] ${RISK_BADGE_STYLES[command.risk] ?? "border-zinc-700 text-zinc-400"}`}>
                            {command.risk}
                          </span>
                        )}
                        {(command.enabled || command.active) && (
                          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )
          )}

          {atMentionOpen && (
            <AtMentionMenu
              candidates={atMentionCandidates}
              activeIndex={selectedAtMentionIndex}
              onActiveIndexChange={setSelectedAtMentionIndex}
              onSelect={handleAtMentionSelect}
              onClose={() => setAtMentionOpen(false)}
              style={composerPopoverStyle}
            />
          )}

          {menuOpen && (
            <>
                      <button
                        type="button"
                        aria-label="close composer menu"
                        tabIndex={chromeButtonTabIndex}
                        className="fixed inset-0 z-20 cursor-default"
                        onClick={() => setMenuOpen(false)}
                      />
              <div ref={menuRef} className="absolute bottom-full left-4 z-40 mb-2 grid w-[min(480px,calc(100vw-32px))] grid-cols-[120px_minmax(0,1fr)] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl max-[640px]:left-2 max-[640px]:grid-cols-1">
                <div className="border-r border-zinc-800 bg-zinc-950/90 p-1.5 max-[640px]:flex max-[640px]:border-b max-[640px]:border-r-0">
                  {(
                    [
                      ["tools", "Tools", Wrench],
                      ["models", "Models", SlidersHorizontal],
                      ["commands", "Commands", Folder],
                    ] as const
                  ).map(([id, label, Icon]) => (
                            <button
                              key={id}
                              type="button"
                              tabIndex={chromeButtonTabIndex}
                              onClick={() => setOpenFolder(id)}
                      className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                        openFolder === id
                          ? "bg-zinc-800 text-zinc-100"
                          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                      }`}
                    >
                      <Icon size={13} />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
                <div className="max-h-72 overflow-y-auto p-2">
                  {openFolder === "tools" && !showToolGroups && (
                    <ToolItemList
                      items={toolItems}
                      onSelect={(item) => {
                        onExtensionSelect?.(item);
                        setMenuOpen(false);
                      }}
                    />
                  )}
                  {openFolder === "tools" && showToolGroups && (
                    <div className="grid grid-cols-[130px_minmax(0,1fr)] gap-2 max-[640px]:grid-cols-1">
                      <div className="grid content-start gap-0.5">
                        {toolGroups.map((group) => (
                                  <button
                                    key={group.id}
                                    type="button"
                                    tabIndex={chromeButtonTabIndex}
                                    onClick={() => setOpenToolGroup(group.id)}
                            className={`rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                              activeToolGroup?.id === group.id
                                ? "bg-zinc-800 text-zinc-100"
                                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                            }`}
                          >
                            <span className="block truncate text-[13px]">{group.label}</span>
                            <span className="block truncate text-[10px] text-zinc-500">
                              {group.path?.length && group.path.length > 1 ? group.path.join(" / ") : `${group.items.length} tools`}
                            </span>
                          </button>
                        ))}
                      </div>
                      <div className="min-w-0">
                        {activeToolGroup && (
                          <>
                            <div className="mb-1 px-2 text-[10px] text-zinc-500">
                              {activeToolGroup.path?.length && activeToolGroup.path.length > 1
                                ? activeToolGroup.path.join(" / ")
                                : activeToolGroup.description}
                            </div>
                            <ToolItemList
                              items={activeToolGroup.items}
                              onSelect={(item) => {
                                onExtensionSelect?.(item);
                                setMenuOpen(false);
                              }}
                            />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                  {openFolder === "models" && (
                    <div className="grid gap-0.5">
                      {selectableProfiles.map((profile) => {
                        const needsKey = needsApiKey(profile);
                        const badges = capabilityBadges(profile).slice(0, 3);
                        return (
                                  <button
                                    key={profile.profile_id}
                                    type="button"
                                    tabIndex={chromeButtonTabIndex}
                                    draggable
                            onDragStart={(event) => {
                              event.dataTransfer.setData(
                                "application/rumi-widget",
                                JSON.stringify({ id: profile.profile_id, type: "model", label: profile.display_name }),
                              );
                              event.dataTransfer.effectAllowed = "copy";
                            }}
                            onClick={() => {
                              requestModelProfileSelect(profile.profile_id);
                              setMenuOpen(false);
                            }}
                            className="flex items-center justify-between gap-2 rounded-lg px-3 py-1.5 text-left hover:bg-zinc-800/80 transition-colors"
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-[13px] text-zinc-200">
                                {compactProfileName(profileDisplayName(profile))}
                              </span>
                              <span className="block truncate text-[10px] text-zinc-500">
                                {profile.provider_display_name ?? profile.provider_id} · {profile.provider_id} · {profile.max_context_tokens ?? profile.max_context ?? "?"} ctx
                              </span>
                              {badges.length > 0 && (
                                <span className="mt-1 flex flex-wrap gap-1">
                                  {badges.map((badge) => (
                                    <span key={badge} className="rounded border border-zinc-700 px-1 py-0.5 text-[9px] leading-none text-zinc-400">
                                      {badge}
                                    </span>
                                  ))}
                                </span>
                              )}
                            </span>
                            {needsKey && (
                              <span className="flex-shrink-0 rounded-full border border-amber-500/30 px-2 py-0.5 text-[10px] text-amber-300">
                                API key
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {openFolder === "commands" && (
                    <div className="grid gap-0.5">
                      {commands.map((command) => (
                                <button
                                  key={command.id}
                                  type="button"
                                  tabIndex={chromeButtonTabIndex}
                                  onClick={() => {
                                    chooseCommand(command.id);
                                    setMenuOpen(false);
                                  }}
                          className="flex items-center justify-between gap-3 rounded-lg px-3 py-1.5 text-left hover:bg-zinc-800/80 transition-colors"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-[13px] text-zinc-200">/{command.name ?? command.id}</span>
                            {command.description && (
                              <span className="block truncate text-[10px] text-zinc-500">{command.description}</span>
                            )}
                          </span>
                          <span className="flex flex-shrink-0 items-center gap-1">
                            {command.visibility === "advanced" && (
                              <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-500">advanced</span>
                            )}
                            {(command.enabled || command.active) && (
                              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>
                            )}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {isNewConversation && attachedFiles.length > 0 && (
            <div className="flex gap-4 overflow-x-auto px-6 pb-2 pt-5">
              {attachedFiles.map((file) => (
                <FilePreviewCard key={file.id} file={file} onRemove={onFileRemove} />
              ))}
            </div>
          )}

          {!isNewConversation && visibleSteerPreviewItems.length > 0 && (
            <div className="mx-2 mt-1 overflow-hidden rounded-xl bg-zinc-900/45 px-2 py-1.5 max-[640px]:mx-1.5 max-[640px]:px-1.5">
              <div className="flex items-center justify-between gap-2 pb-1 text-[10px] leading-none text-zinc-500">
                <div className="flex min-w-0 items-center gap-1.5">
                  <CornerDownRight size={12} className="flex-shrink-0" />
                  {visibleSteerPreviewItems.length > 1 && (
                    <span className="rounded-full bg-zinc-800/80 px-1.5 py-0.5 text-[9px] leading-none">
                      {visibleSteerPreviewItems.length}
                    </span>
                  )}
                </div>
                <div className="flex min-w-0 flex-shrink items-center justify-end gap-1.5">
                  {steerBusy && <Loader2 size={11} className="flex-shrink-0 animate-spin" />}
                  {steerStatus && <span className="truncate">{steerStatus}</span>}
                </div>
              </div>
              <div className="grid gap-1">
                {visibleSteerPreviewItems.map((item) => (
                  <div key={item.id} className="grid gap-1 rounded-lg bg-zinc-950/30 px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[9px] leading-none text-zinc-500">
                        {steerStatusLabel(item.status)}
                      </span>
                    </div>
                    <div className="max-h-16 overflow-y-auto whitespace-pre-wrap break-words text-[12px] leading-4 text-zinc-300">
                      {String(item.prompt ?? "").trim()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <textarea
            ref={textareaRef}
            autoFocus
            value={input}
            onChange={(event) => handleInputChange(event.target.value)}
            placeholder={
              isSteerMode
                ? "実行中のAIへステアを入力..."
                : mode === "coding"
                ? "コーディング指示を入力... (@ でtool/ファイル)"
                : placeholder
            }
            className={`${
              isNewConversation
                ? "rumi-composer-input-new min-h-[54px] px-6 pt-4 text-[18px] font-medium leading-[1.5] placeholder:text-zinc-500"
                : "min-h-[34px] px-5 pt-3 text-[15px] max-[640px]:min-h-[32px] max-[640px]:px-3 max-[640px]:pt-2.5 max-[640px]:pb-0 max-[640px]:text-[13px]"
            } rumi-composer-textarea w-full select-text bg-transparent border-none outline-none text-zinc-100 pb-0 resize-none max-h-[130px]`}
            onKeyDownCapture={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
                event.stopPropagation();
              }
            }}
            onKeyDown={handleKeyDown}
          />

          {isSteerMode && (
            <div className="flex min-h-5 items-center gap-2 px-5 pt-1 text-[10px] leading-none text-zinc-500 max-[640px]:px-3">
              <CornerDownRight size={12} className="flex-shrink-0" />
              <span className="truncate">
                {input.trim() ? "Enterでステアを送信" : "AI実行中。入力するとステアになります"}
              </span>
              {steerBusy && <Loader2 size={11} className="flex-shrink-0 animate-spin" />}
              {steerQueuedCount > 0 && (
                <span className="flex-shrink-0 rounded-full border border-zinc-700 px-1.5 py-0.5 text-[9px] leading-none">
                  {steerQueuedCount}件待機
                </span>
              )}
              {steerStatus && (
                <span className="min-w-0 truncate text-zinc-600">{steerStatus}</span>
              )}
            </div>
          )}

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

          {((!isNewConversation && attachedFiles.length > 0) || droppedWidgets.length > 0) && (
            <div className="px-5 pt-1.5 pb-0.5 flex flex-wrap gap-1 max-[640px]:px-3">
              {!isNewConversation && attachedFiles.map((file) => (
                <FileChip key={file.id} file={file} onRemove={onFileRemove} />
              ))}
              {droppedWidgets.map((widget) => (
                <DroppedWidgetChip
                  key={widget.id}
                  widget={widget.type === "tool" ? { ...widget, enabled: selectedToolIdSet.has(widget.sourceItemId || widget.id) } : widget}
                  onAction={onWidgetAction}
                  onToggle={onWidgetToggle}
                />
              ))}
            </div>
          )}

          <div
            className={`${
              isNewConversation ? "rumi-composer-actions px-5 pb-4" : "px-4 pb-2 max-[640px]:px-2 max-[640px]:pb-1.5"
            } flex items-center justify-between gap-2 pt-0 max-[640px]:gap-1.5`}
          >
            <div className="flex min-w-0 items-center gap-1 overflow-hidden">
              {composerChromeWidgetsForSlot(chromeWidgets, "leading").map((widget) => (
                <ComposerChromeWidget key={widget.id} widget={widget} />
              ))}
            </div>

            <div className="rumi-composer-submit-area flex flex-shrink-0 items-center justify-end gap-2">
              {composerChromeWidgetsForSlot(chromeWidgets, "trailing").map((widget) => (
                <ComposerChromeWidget key={widget.id} widget={widget} />
              ))}
            </div>
          </div>

          {mode === "coding" && codingContext && (
            <div className="px-5 pb-2 pt-0 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500 max-[640px]:px-3">
              <CodingWorkspaceBadge workspace={selectedCodingWorkspace} compact />
              <CodingWorkspacePicker
                workspaces={codingWorkspaces}
                selectedWorkspaceId={selectedCodingWorkspace?.workspace_id ?? selectedCodingWorkspaceId ?? codingContext.workspaceId ?? null}
                disabled={isGenerating}
                onSelect={onCodingWorkspaceSelect}
                onTrust={onCodingWorkspaceTrust}
                onCreate={onCodingWorkspaceCreate}
                onRefresh={onCodingWorkspacesRefresh}
              />
              <span className="inline-flex min-w-0 items-center gap-1">
                <GitBranch size={11} />
                {branchOptions.length > 1 ? (
                  <select
                    value={codingContext.branch ?? ""}
                    onChange={(event) => event.target.value && onCodingBranchSwitch?.(event.target.value, false)}
                    disabled={isGenerating}
                    className="max-w-[140px] bg-transparent font-mono text-zinc-400 outline-none hover:text-zinc-200 disabled:opacity-50"
                    title="ブランチを切り替え"
                  >
                    {branchOptions.map((branch) => (
                      <option key={branch} value={branch} className="bg-zinc-900 text-zinc-100">
                        {branch}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="font-mono">{codingContext.branch ?? "no git"}</span>
                )}
              </span>
              <span className="inline-flex items-center gap-1">
                <FileText size={11} />
                <select
                  value={currentDirectory}
                  onChange={(event) => onCodingDirectoryChange?.(event.target.value)}
                  disabled={isGenerating}
                  className="max-w-[140px] bg-transparent font-mono text-zinc-400 outline-none hover:text-zinc-200 disabled:opacity-50"
                  title="target folder"
                >
                  <option value="." className="bg-zinc-900 text-zinc-100">.</option>
                  {directoryEntries.map((entry) => (
                    <option key={entry.path} value={entry.path} className="bg-zinc-900 text-zinc-100">
                      {entry.path}
                    </option>
                  ))}
                </select>
              </span>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
