import {
  ArrowUp,
  Bot,
  ChevronDown,
  Code2,
  File,
  FileText,
  Folder,
  GitBranch,
  Loader2,
  MessageSquare,
  Mic,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Terminal,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  AttachedFile,
  ComposerCommandItem,
  ComposerExtensionItem,
  ComposerRendererProps,
  DroppedWidget,
  AppMode,
  ToolGroup,
} from "./types";
import type { ModelProfile } from "../lib/api";
import { fileToAttachment } from "../lib/attachments";
import { supportsComposerToggleDrop, toolGroupFor } from "../lib/toolUi";

const THINKING_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

const MODE_META: Record<AppMode, { label: string; icon: typeof MessageSquare; description: string }> = {
  chat: { label: "Chat", icon: MessageSquare, description: "通常チャット" },
  coding: { label: "Coding", icon: Code2, description: "コード編集・Git操作" },
  agent: { label: "Agent", icon: Bot, description: "自律エージェント" },
};

function compactProfileName(name: string): string {
  return name
    .replace(/^GPT-/i, "")
    .replace(/^Claude\s+/i, "")
    .replace(/\s*\(.*?\)\s*/g, " ")
    .trim();
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

function DroppedWidgetChip({ widget, onToggle }: { widget: DroppedWidget; onToggle?: (id: string) => void }) {
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

export type ComposerDropAction =
  | { type: "select_model"; profileId: string }
  | { type: "drop_widget"; widget: DroppedWidget }
  | { type: "ignore" };

export function resolveComposerWidgetDrop(widget: DroppedWidget, toolItems: ComposerExtensionItem[]): ComposerDropAction {
  if (widget.type === "model") return { type: "select_model", profileId: widget.id };
  if (widget.type === "tool") {
    const item = toolItems.find((candidate) => candidate.id === widget.id);
    if (!item || !supportsComposerToggleDrop(item)) return { type: "ignore" };
    return { type: "drop_widget", widget };
  }
  return { type: "ignore" };
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
  const filtered = useMemo(() => {
    if (!search) return profiles;
    const q = search.toLowerCase();
    return profiles.filter(
      (p) =>
        p.display_name.toLowerCase().includes(q) ||
        (p.provider_id ?? "").toLowerCase().includes(q) ||
        (p.model_id ?? "").toLowerCase().includes(q),
    );
  }, [profiles, search]);

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
      <div className="absolute bottom-full left-0 mb-2 z-30 w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
        <div className="border-b border-zinc-800 p-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="モデルを検索..."
              className="w-full rounded-lg bg-zinc-900 border border-zinc-800 pl-8 pr-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-zinc-600 placeholder:text-zinc-600"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-64 overflow-y-auto py-1">
          {groupedByProvider.map(([provider, profiles]) => (
            <div key={provider}>
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">{provider}</div>
              {profiles.map((profile) => (
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
                    <span className="block truncate text-[13px] text-zinc-200">{compactProfileName(profile.display_name)}</span>
                    <span className="block truncate text-[10px] text-zinc-500">
                      {profile.provider_id}/{profile.model_id}
                    </span>
                  </span>
                  <span className="flex-shrink-0 text-[10px] text-zinc-500">
                    {profile.max_context_tokens ?? profile.max_context ?? "?"}
                  </span>
                </button>
              ))}
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
      <div className="absolute bottom-full left-0 mb-2 z-30 w-[220px] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
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

function AtFileMention({
  query,
  files,
  onSelect,
  onClose,
}: {
  query: string;
  files: string[];
  onSelect: (file: string) => void;
  onClose: () => void;
}) {
  const filtered = useMemo(() => filterAtMentionFiles(files, query), [files, query]);

  if (filtered.length === 0) return null;

  return (
    <>
      <button type="button" aria-label="close file mention" className="fixed inset-0 z-20 cursor-default" onClick={onClose} />
      <div className="absolute bottom-full left-4 mb-2 z-30 w-[min(400px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
        <div className="border-b border-zinc-800 px-3 py-2 flex items-center gap-2">
          <Folder size={13} className="text-zinc-500" />
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">ファイルを選択</p>
        </div>
        <div className="max-h-56 overflow-y-auto py-1">
          {filtered.map((file) => (
            <button
              key={file}
              type="button"
              onClick={() => onSelect(file)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-800/80 transition-colors"
            >
              <FileText size={13} className="text-zinc-500 flex-shrink-0" />
              <span className="truncate text-[13px] text-zinc-200">{file}</span>
            </button>
          ))}
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
  commands = [],
  yoloMode = false,
  mode = "chat",
  codingContext = null,
  attachedFiles = [],
  droppedWidgets = [],
  selectedToolIds = [],
  onExtensionSelect,
  onCommandSelect,
  onModelProfileSelect,
  onThinkingLevelChange,
  onInputChange,
  onSubmit,
  onModeChange,
  onFileAttach,
  onFileRemove,
  onDropWidget,
  onWidgetToggle,
  onCodingBranchSwitch,
  onCodingDirectoryChange,
  onCodingContextRefresh,
}: ComposerRendererProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [openFolder, setOpenFolder] = useState<"tools" | "models" | "commands">("tools");
  const [openToolGroup, setOpenToolGroup] = useState<string | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modeSelectorOpen, setModeSelectorOpen] = useState(false);
  const [atMentionOpen, setAtMentionOpen] = useState(false);
  const [atMentionQuery, setAtMentionQuery] = useState("");
  const [newBranchName, setNewBranchName] = useState("");
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const profileName = selectedProfile?.display_name ?? selectedProfile?.profile_id ?? "model";
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
  const currentModeMeta = MODE_META[mode];
  const ModeIcon = currentModeMeta.icon;
  const directoryEntries = (codingContext?.entries ?? []).filter((entry) => entry.is_dir);
  const branchOptions = codingContext?.branches?.length ? codingContext.branches : codingContext?.branch ? [codingContext.branch] : [];
  const currentDirectory = codingContext?.directory || ".";

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

  const chooseCommand = (commandId: string) => {
    onCommandSelect?.(commandId);
    onInputChange("");
  };

  const handleInputChange = useCallback(
    (value: string) => {
      onInputChange(value);

      const textarea = textareaRef.current;
      if (!textarea) return;

      const cursorPos = textarea.selectionStart;
      const textBeforeCursor = value.slice(0, cursorPos);
      const atMatch = textBeforeCursor.match(/@(\S*)$/);

      if (atMatch && mode === "coding" && codingContext?.files?.length) {
        setAtMentionOpen(true);
        setAtMentionQuery(atMatch[1]);
      } else {
        setAtMentionOpen(false);
        setAtMentionQuery("");
      }

      if (!value.startsWith("/")) {
        setSelectedCommandIndex(0);
      }
    },
    [onInputChange, mode, codingContext],
  );

  const handleAtFileSelect = useCallback(
    (file: string) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const cursorPos = textarea.selectionStart;
      const textBeforeCursor = input.slice(0, cursorPos);
      const atIndex = textBeforeCursor.lastIndexOf("@");
      const before = input.slice(0, atIndex);
      const after = input.slice(cursorPos);
      const next = `${before}@${file} ${after}`;
      onInputChange(next);
      setAtMentionOpen(false);
      setAtMentionQuery("");

      setTimeout(() => {
        const newPos = atIndex + file.length + 2;
        textarea.setSelectionRange(newPos, newPos);
        textarea.focus();
      }, 0);
    },
    [input, onInputChange],
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

      const data = event.dataTransfer.getData("application/rumi-widget");
      if (data) {
        try {
          const widget: DroppedWidget = JSON.parse(data);
          const action = resolveComposerWidgetDrop(widget, toolItems);
          if (action.type === "drop_widget") {
            onDropWidget?.(action.widget);
          } else if (action.type === "select_model") {
            onModelProfileSelect(action.profileId);
            setModelDropdownOpen(false);
            setMenuOpen(false);
          }
        } catch {
          // invalid drop data
        }
      }
    },
    [attachFiles, onDropWidget, onModelProfileSelect, toolItems],
  );

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
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

      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        onSubmit(event);
      }
    },
    [matchedCommands, selectedCommandIndex, onSubmit],
  );

  return (
    <div
      className={`${isNewConversation ? "w-full px-5" : "px-5 pb-5 pt-2 bg-[#09090b] flex-shrink-0 max-[640px]:px-2 max-[640px]:pb-2"}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className={`rumi-composer-shell ${isNewConversation ? "rumi-composer-shell-new mx-auto" : "mx-auto"}`}>
        <form
          onSubmit={onSubmit}
          className={`rumi-composer-frame ${
            isNewConversation
              ? "rumi-composer-new min-h-[176px] rounded-3xl border-zinc-700/70 bg-[#242423]"
              : "rounded-xl border-zinc-700/30 bg-[#2b2b2d] max-[640px]:rounded-xl"
          } relative flex flex-col border overflow-visible shadow-2xl shadow-black/20 focus-within:border-zinc-500/60`}
        >
          {matchedCommands.length > 0 && (
            <div className="absolute bottom-full left-4 z-30 mb-2 w-[min(420px,calc(100vw-32px))] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl">
              <div className="border-b border-zinc-800 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                Commands
              </div>
              <div className="max-h-56 overflow-y-auto py-1">
                {matchedCommands.map((command, index) => (
                  <button
                    key={command.id}
                    type="button"
                    onMouseEnter={() => setSelectedCommandIndex(index)}
                    onClick={() => chooseCommand(command.id)}
                    className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left ${
                      index === selectedCommandIndex ? "bg-zinc-800 text-zinc-100" : "hover:bg-zinc-900"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-zinc-100">/{command.label}</span>
                      {command.description && (
                        <span className="block truncate text-[11px] text-zinc-500">{command.description}</span>
                      )}
                    </span>
                    {command.enabled && (
                      <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {atMentionOpen && codingContext?.files && (
            <AtFileMention
              query={atMentionQuery}
              files={codingContext.files}
              onSelect={handleAtFileSelect}
              onClose={() => setAtMentionOpen(false)}
            />
          )}

          {menuOpen && (
            <>
              <button
                type="button"
                aria-label="close composer menu"
                className="fixed inset-0 z-20 cursor-default"
                onClick={() => setMenuOpen(false)}
              />
              <div ref={menuRef} className="absolute bottom-[52px] left-4 z-30 grid w-[min(480px,calc(100vw-32px))] grid-cols-[120px_minmax(0,1fr)] overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 shadow-2xl max-[640px]:left-2 max-[640px]:grid-cols-1">
                <div className="border-r border-zinc-800 bg-zinc-950/90 p-1.5 max-[640px]:flex max-[640px]:border-b max-[640px]:border-r-0">
                  {(
                    [
                      ["tools", "Tools", Wrench],
                      ["models", "AI Models", Sparkles],
                      ["commands", "Commands", Folder],
                    ] as const
                  ).map(([id, label, Icon]) => (
                    <button
                      key={id}
                      type="button"
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
                      {selectableProfiles.map((profile) => (
                        <button
                          key={profile.profile_id}
                          type="button"
                          draggable
                          onDragStart={(event) => {
                            event.dataTransfer.setData(
                              "application/rumi-widget",
                              JSON.stringify({ id: profile.profile_id, type: "model", label: profile.display_name }),
                            );
                            event.dataTransfer.effectAllowed = "copy";
                          }}
                          onClick={() => {
                            onModelProfileSelect(profile.profile_id);
                            setMenuOpen(false);
                          }}
                          className="rounded-lg px-3 py-1.5 text-left hover:bg-zinc-800/80 transition-colors"
                        >
                          <span className="block truncate text-[13px] text-zinc-200">
                            {compactProfileName(profile.display_name)}
                          </span>
                          <span className="block truncate text-[10px] text-zinc-500">
                            {profile.provider_id} · {profile.max_context_tokens ?? profile.max_context ?? "?"} ctx
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  {openFolder === "commands" && (
                    <div className="grid gap-0.5">
                      {commands.map((command) => (
                        <button
                          key={command.id}
                          type="button"
                          onClick={() => {
                            chooseCommand(command.id);
                            setMenuOpen(false);
                          }}
                          className="flex items-center justify-between gap-3 rounded-lg px-3 py-1.5 text-left hover:bg-zinc-800/80 transition-colors"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-[13px] text-zinc-200">/{command.label}</span>
                            {command.description && (
                              <span className="block truncate text-[10px] text-zinc-500">{command.description}</span>
                            )}
                          </span>
                          {command.enabled && (
                            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">on</span>
                          )}
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

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => handleInputChange(event.target.value)}
            placeholder={
              mode === "coding"
                ? "コーディング指示を入力... (@ でファイル添付)"
                : placeholder
            }
            disabled={isGenerating}
            className={`${
              isNewConversation
                ? "rumi-composer-input-new min-h-[64px] px-6 pt-5 text-[18px] font-medium leading-[1.55] placeholder:text-zinc-500"
                : "min-h-[34px] px-5 pt-3 text-[15px] max-[640px]:min-h-[32px] max-[640px]:px-3 max-[640px]:pt-2.5 max-[640px]:pb-0 max-[640px]:text-[13px]"
            } w-full bg-transparent border-none outline-none text-zinc-100 pb-0 resize-none max-h-[130px] disabled:opacity-50`}
            onKeyDown={handleKeyDown}
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

          {((!isNewConversation && attachedFiles.length > 0) || droppedWidgets.length > 0) && (
            <div className="px-5 pt-1.5 pb-0.5 flex flex-wrap gap-1 max-[640px]:px-3">
              {!isNewConversation && attachedFiles.map((file) => (
                <FileChip key={file.id} file={file} onRemove={onFileRemove} />
              ))}
              {droppedWidgets.map((widget) => (
                <DroppedWidgetChip
                  key={widget.id}
                  widget={widget.type === "tool" ? { ...widget, enabled: selectedToolIdSet.has(widget.id) } : widget}
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
              <button
                ref={menuButtonRef}
                type="button"
                disabled={isGenerating}
                title="追加"
                onClick={() => setMenuOpen((value) => !value)}
                className="h-8 w-8 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60 rounded-lg transition-colors disabled:opacity-50"
              >
                <Plus size={18} />
              </button>
              <button
                type="button"
                disabled={isGenerating}
                title="ファイル添付（複数選択可）"
                onClick={() => fileInputRef.current?.click()}
                className={`${
                  isNewConversation
                    ? "border border-zinc-700/70 bg-zinc-900/30 text-zinc-300 hover:border-zinc-600 hover:bg-zinc-800/70"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60"
                } h-8 w-8 flex flex-shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-50`}
              >
                <Paperclip size={16} />
              </button>
              <button
                type="button"
                disabled={isGenerating}
                title="音声入力"
                className="h-8 w-8 flex flex-shrink-0 items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60 rounded-lg transition-colors disabled:opacity-50 max-[640px]:hidden"
              >
                <Mic size={16} />
              </button>

              <div className="group/mode relative flex">
                <button
                  type="button"
                  disabled={isGenerating}
                  title={`モード: ${currentModeMeta.label}`}
                  onClick={() => setModeSelectorOpen((v) => !v)}
                  className={`h-8 flex flex-shrink-0 items-center gap-1.5 rounded-lg px-2.5 transition-colors disabled:opacity-50 ${
                    mode === "coding"
                      ? "text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30"
                      : mode === "agent"
                        ? "text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/30"
                        : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60"
                  }`}
                >
                  <ModeIcon size={14} />
                  <span className="text-[11px] font-medium max-[640px]:hidden">{currentModeMeta.label}</span>
                </button>
                {mode !== "chat" && (
                  <button
                    type="button"
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

              {yoloMode && (
                <span className="rounded-full border border-orange-500/30 px-2 py-0.5 text-[11px] text-orange-300">
                  YOLO
                </span>
              )}
            </div>

            <div className="rumi-composer-submit-area flex flex-shrink-0 items-center justify-end gap-2">
              <div className="rumi-model-control flex items-center gap-1.5 bg-zinc-800/40 rounded-lg px-2.5 py-1 border border-zinc-700/40 max-[640px]:hidden">
                <div
                  title={contextTitle}
                  className="h-3.5 w-3.5 flex-shrink-0 rounded-full p-[2px]"
                  style={{
                    background: `conic-gradient(#a1a1aa ${contextDegrees}deg, #52525b ${contextDegrees}deg)`,
                  }}
                >
                  <div className="h-full w-full rounded-full bg-zinc-800" />
                </div>
                <div className="relative">
                  <button
                    type="button"
                    disabled={isGenerating}
                    onClick={() => setModelDropdownOpen((v) => !v)}
                    className="flex items-center gap-1 text-[12px] font-medium text-zinc-300 hover:text-zinc-100 transition-colors disabled:opacity-50"
                  >
                    <span className="max-w-[120px] truncate">{compactProfileName(profileName)}</span>
                    <ChevronDown size={12} className={`transition-transform ${modelDropdownOpen ? "rotate-180" : ""}`} />
                  </button>
                  {modelDropdownOpen && (
                    <ModelDropdown
                      profiles={selectableProfiles}
                      selectedProfile={selectedProfile}
                      isGenerating={isGenerating}
                      onSelect={onModelProfileSelect}
                      onClose={() => setModelDropdownOpen(false)}
                    />
                  )}
                </div>
                {levels.length > 0 && (
                  <select
                    value={thinkingLevel ?? levels[0]}
                    onChange={(event) => onThinkingLevelChange(event.target.value)}
                    disabled={isGenerating}
                    className="bg-transparent text-[11px] font-medium text-zinc-400 outline-none cursor-pointer hover:text-zinc-200 transition-colors disabled:opacity-50 border-l border-zinc-700/50 pl-1.5 ml-0.5"
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
              <button
                type="submit"
                disabled={!input.trim() || isGenerating}
                title="送信"
                className={`rumi-send-button ${
                  isNewConversation ? "h-9 w-9" : "w-8 h-8 max-[640px]:h-7 max-[640px]:w-7"
                } flex flex-shrink-0 items-center justify-center bg-zinc-200 text-black rounded-lg disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white shadow-sm transition-colors`}
              >
                {isGenerating ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <ArrowUp size={16} strokeWidth={2.4} />
                )}
              </button>
            </div>
          </div>

          {mode === "coding" && codingContext && (
            <div className="px-5 pb-2 pt-0 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500 max-[640px]:px-3">
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
              <form
                className="inline-flex items-center gap-1"
                onSubmit={(event) => {
                  event.preventDefault();
                  const branch = newBranchName.trim();
                  if (!branch) return;
                  onCodingBranchSwitch?.(branch, true);
                  setNewBranchName("");
                }}
              >
                <input
                  value={newBranchName}
                  onChange={(event) => setNewBranchName(event.target.value)}
                  disabled={isGenerating}
                  placeholder="new branch"
                  className="h-6 w-24 rounded-md border border-zinc-800 bg-zinc-900/40 px-2 font-mono text-[11px] text-zinc-300 outline-none placeholder:text-zinc-700 focus:border-zinc-600 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={isGenerating || !newBranchName.trim()}
                  title="ブランチを作成して切り替え"
                  className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
                >
                  <Plus size={12} />
                </button>
              </form>
              {codingContext.rootFolder && (
                <span className="inline-flex min-w-0 items-center gap-1">
                  <Folder size={11} />
                  <span className="max-w-[200px] truncate font-mono">{codingContext.rootFolder}</span>
                </span>
              )}
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
                <span>{codingContext.files.length} files</span>
              </span>
              <button
                type="button"
                onClick={onCodingContextRefresh}
                disabled={isGenerating}
                title="coding context を更新"
                className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
              >
                <RefreshCw size={12} />
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
