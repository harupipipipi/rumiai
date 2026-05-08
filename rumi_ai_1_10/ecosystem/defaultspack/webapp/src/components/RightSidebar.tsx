import { useEffect, useMemo, useRef, useState, type DragEvent, type MouseEvent, type ReactElement } from "react";
import {
  Blocks,
  BrainCircuit,
  ChevronDown,
  Cpu,
  FileText,
  Globe,
  GripVertical,
  Image,
  Languages,
  LayoutGrid,
  Layers,
  Music,
  Newspaper,
  NotebookPen,
  Power,
  Search,
  Settings,
  SlidersHorizontal,
  Star,
  Terminal,
  Wrench,
  GitBranch,
  ShieldCheck,
  Download,
  Share2,
  Play,
  CalendarClock,
  MessageSquareText,
  Monitor,
  Archive,
  Code2,
  MoreVertical,
  Pin,
  PinOff,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type {
  SettingsSection,
  SidebarAction,
  SidebarCategory,
  SidebarField,
  SidebarItem,
} from "../lib/api";
import { compareToolUiItems, sortedToolGroups, sortedToolUiItems, supportedComposerDropKind, supportsComposerDrop, toolGroupFor } from "../lib/toolUi";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function readStoredStringArray(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map((item) => String(item)).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function useStoredStringArray(key: string): [string[], (updater: (current: string[]) => string[]) => void] {
  const [value, setValue] = useState<string[]>(() => readStoredStringArray(key));
  const update = (updater: (current: string[]) => string[]) => {
    setValue((current) => {
      const next = [...new Set(updater(current).filter(Boolean))];
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Storage may be unavailable in restricted browser contexts.
      }
      return next;
    });
  };
  return [value, update];
}

const CATEGORY_META: Record<SidebarCategory | "all", { label: string; icon: ReactElement }> = {
  all: { label: "All", icon: <Layers size={14} /> },
  tool: { label: "Tools", icon: <Wrench size={14} /> },
  widget: { label: "Widgets", icon: <LayoutGrid size={14} /> },
  system: { label: "System", icon: <Settings size={14} /> },
  integration: { label: "Integrations", icon: <Blocks size={14} /> },
  capability: { label: "Capabilities", icon: <ShieldCheck size={14} /> },
};

const TOOL_GROUP_ICONS: Record<string, ReactElement> = {
  coding: <Code2 size={16} />,
  file: <FileText size={16} />,
  git: <GitBranch size={16} />,
  research: <Search size={16} />,
  operate: <Monitor size={16} />,
  manage: <Cpu size={16} />,
  terminal: <Terminal size={16} />,
  other: <Wrench size={16} />,
};

const TOOL_GROUP_LABELS: Record<string, string> = {
  coding: "Coding",
  research: "調べる",
  operate: "操作する",
  manage: "管理",
  workspace_files: "Files",
  workspace_git: "Git",
  workspace_terminal: "Terminal",
  other: "その他",
};

const ITEM_ICONS: Record<string, ReactElement> = {
  artifacts: <Archive size={18} />,
  browser: <Monitor size={18} />,
  calculator: <BrainCircuit size={18} />,
  code: <Terminal size={18} />,
  file: <FileText size={18} />,
  file_reader: <FileText size={18} />,
  files: <FileText size={18} />,
  git: <GitBranch size={18} />,
  image: <Image size={18} />,
  inspector: <Cpu size={18} />,
  knowledge: <Search size={18} />,
  memory: <Cpu size={18} />,
  music: <Music size={18} />,
  news: <Newspaper size={18} />,
  notebook: <NotebookPen size={18} />,
  provider: <Blocks size={18} />,
  providers: <Blocks size={18} />,
  search: <Globe size={18} />,
  translate: <Languages size={18} />,
  web: <Globe size={18} />,
  web_search: <Search size={18} />,
  reddit_search: <Search size={18} />,
};

const ACTION_ICONS: Record<string, ReactElement> = {
  artifacts: <Archive size={13} />,
  browser: <Monitor size={13} />,
  channels: <MessageSquareText size={13} />,
  export: <Download size={13} />,
  play: <Play size={13} />,
  reddit: <Search size={13} />,
  schedules: <CalendarClock size={13} />,
  share: <Share2 size={13} />,
  web: <Globe size={13} />,
};

const SIDEBAR_CATEGORY_ORDER: Record<SidebarCategory, number> = {
  tool: 0,
  widget: 1,
  capability: 2,
  integration: 3,
  system: 4,
};

function compareText(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
}

function compareSidebarItems(left: SidebarItem, right: SidebarItem): number {
  if (left.category === "tool" && right.category === "tool") {
    return compareToolUiItems(left, right);
  }
  return (
    SIDEBAR_CATEGORY_ORDER[left.category] - SIDEBAR_CATEGORY_ORDER[right.category]
    || compareText(left.label || left.id, right.label || right.id)
    || compareText(left.id, right.id)
  );
}

function actionIcon(action: SidebarAction) {
  const key = action.icon || action.id.split(".")[0] || "play";
  return ACTION_ICONS[key] ?? <Play size={13} />;
}

function iconForItem(item: SidebarItem) {
  const declaredIcon = item.ui?.item_icon || item.ui?.group_icon;
  if (declaredIcon && ITEM_ICONS[declaredIcon]) return ITEM_ICONS[declaredIcon];

  // Legacy fallback for pre-ui metadata tools.
  const direct = item.id.toLowerCase();
  if (ITEM_ICONS[direct]) return ITEM_ICONS[direct];
  const normalized = item.label.toLowerCase().replace(/\s+/g, "_");
  if (ITEM_ICONS[normalized]) return ITEM_ICONS[normalized];
  const byCategory: Record<SidebarCategory, ReactElement> = {
    tool: <Wrench size={18} />,
    widget: <LayoutGrid size={18} />,
    system: <Cpu size={18} />,
    integration: <Blocks size={18} />,
    capability: <ShieldCheck size={18} />,
  };
  return byCategory[item.category];
}

function categoryColor(cat: SidebarCategory, variant: "bg" | "indicator" | "dot" | "badge") {
  const map: Record<SidebarCategory, Record<string, string>> = {
    tool: { bg: "bg-emerald-500", indicator: "bg-emerald-500", dot: "bg-emerald-500/60", badge: "bg-emerald-500/20 text-emerald-400" },
    widget: { bg: "bg-blue-500", indicator: "bg-blue-500", dot: "bg-blue-500/60", badge: "bg-blue-500/20 text-blue-400" },
    system: { bg: "bg-amber-500", indicator: "bg-amber-500", dot: "bg-amber-500/60", badge: "bg-amber-500/20 text-amber-400" },
    integration: { bg: "bg-violet-500", indicator: "bg-violet-500", dot: "bg-violet-500/60", badge: "bg-violet-500/20 text-violet-400" },
    capability: { bg: "bg-cyan-500", indicator: "bg-cyan-500", dot: "bg-cyan-500/60", badge: "bg-cyan-500/20 text-cyan-300" },
  };
  return map[cat]?.[variant] ?? "";
}

function ToggleSwitch({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={cn("w-8 h-4.5 rounded-full relative transition-colors flex-shrink-0", value ? "bg-emerald-500" : "bg-zinc-700")}
    >
      <div className={cn("w-3 h-3 bg-white rounded-full absolute top-[3px] transition-transform", value ? "translate-x-[16px]" : "translate-x-[3px]")} />
    </button>
  );
}

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: SidebarField;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (field.type === "toggle") {
    return <ToggleSwitch value={Boolean(value)} onChange={onChange} />;
  }

  if (field.type === "select") {
    return (
      <select
        value={String(value ?? field.default ?? "")}
        onChange={(event) => onChange(event.target.value)}
        className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 outline-none"
      >
        {(field.options ?? []).map((option) => (
          <option key={String(option.value)} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "number") {
    return (
      <input
        type="number"
        value={Number(value ?? field.default ?? 0)}
        min={field.min}
        max={field.max}
        onChange={(event) => onChange(Number(event.target.value))}
        className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 w-20 outline-none text-right"
      />
    );
  }

  if (field.type === "readonly") {
    return <span className="text-xs text-zinc-300 font-mono">{String(value ?? field.default ?? "")}</span>;
  }

  if (field.type === "textarea") {
    return (
      <textarea
        value={String(value ?? field.default ?? "")}
        onChange={(event) => onChange(event.target.value)}
        className="w-full h-24 bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-300 resize-none focus:border-zinc-600 outline-none"
      />
    );
  }

  return (
    <input
      type="text"
      value={String(value ?? field.default ?? "")}
      onChange={(event) => onChange(event.target.value)}
      className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded px-2 py-1 outline-none min-w-0"
    />
  );
}

function SidebarPanel({
  item,
  settingsValues,
  onSettingChange,
  onPanelAction,
}: {
  item: SidebarItem;
  settingsValues: Record<string, Record<string, unknown>>;
  onSettingChange: (sectionId: string, fieldId: string, value: unknown) => void;
  onPanelAction?: (item: SidebarItem, action: SidebarAction) => void;
}) {
  const panel = item.panel;
  const fields = panel?.fields ?? [];
  const primaryFields = fields.filter((field) => !field.advanced);
  const advancedFields = fields.filter((field) => field.advanced);
  const actions = panel?.actions ?? [];
  const renderField = (field: SidebarField) => {
    const value =
      settingsValues[item.id]?.[field.id] ??
      settingsValues.tools?.[`${item.id}.${field.id}`] ??
      field.default;
    return (
      <div key={field.id} className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-zinc-400">{field.label}</span>
          <FieldControl
            field={field}
            value={value}
            onChange={(nextValue) => onSettingChange(item.id, field.id, nextValue)}
          />
        </div>
        {field.help && <p className="text-[9px] text-zinc-600 leading-relaxed">{field.help}</p>}
      </div>
    );
  };

  return (
    <div className="space-y-3">
      {item.origin && (
        <div className="p-2.5 rounded-lg border border-zinc-800/60 bg-zinc-900/30 space-y-1">
          <p className="text-[9px] uppercase tracking-wider text-zinc-500">Origin</p>
          <div className="text-[11px] text-zinc-300">{item.origin.kind}</div>
          {item.origin.path && (
            <div className="text-[10px] text-zinc-500 font-mono break-all">{item.origin.path}</div>
          )}
        </div>
      )}

      {primaryFields.length > 0 && (
        <div className="space-y-2.5">
          {primaryFields.map(renderField)}
        </div>
      )}

      {advancedFields.length > 0 && (
        <details className="rounded-lg border border-zinc-800/70 bg-zinc-950/35 px-2.5 py-2">
          <summary className="cursor-pointer select-none text-[10px] font-medium text-zinc-500 hover:text-zinc-300">
            高度な設定
          </summary>
          <div className="mt-2 space-y-2.5">{advancedFields.map(renderField)}</div>
        </details>
      )}

      {panel?.models && panel.models.length > 0 && (
        <div>
          <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Models</h4>
          <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
            {panel.models.map((model) => (
              <div
                key={model.id}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/rumi-widget", JSON.stringify({ id: model.id, type: "model", label: model.name ?? model.id }));
                  e.dataTransfer.effectAllowed = "copy";
                }}
                className="p-1.5 rounded border border-zinc-800/60 bg-zinc-900/30 cursor-grab active:cursor-grabbing hover:border-zinc-700/60 transition-colors"
              >
                <p className="text-[10px] text-zinc-300 font-mono">{model.id}</p>
                {model.name && <p className="text-[9px] text-zinc-500 mt-0.5">{model.name}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {actions.length > 0 && (
        <div>
          <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Actions</h4>
          <div className="grid grid-cols-1 gap-1">
            {actions.map((action) => (
              <button
                key={action.id}
                onClick={() => onPanelAction?.(item, action)}
                className="h-7 px-2 rounded border border-zinc-800/70 bg-zinc-900/40 text-zinc-300 hover:bg-zinc-800/70 hover:text-zinc-100 transition-colors flex items-center gap-1.5 text-[11px] text-left"
                title={action.label}
              >
                <span className="text-zinc-500 flex-shrink-0">{actionIcon(action)}</span>
                <span className="truncate">{action.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {panel?.notes && panel.notes.length > 0 && (
        <div>
          <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Notes</h4>
          <div className="space-y-1">
            {panel.notes.map((note) => (
              <div key={note} className="p-1.5 rounded border border-zinc-800/60 bg-zinc-900/30 text-[10px] text-zinc-400 leading-relaxed">
                {note}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CategorySwitcher({
  active,
  counts,
  onChange,
}: {
  active: "all" | SidebarCategory;
  counts: Record<string, number>;
  onChange: (id: "all" | SidebarCategory) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const current = CATEGORY_META[active];
  const hasActiveFilter = active !== "all";
  const rect = buttonRef.current?.getBoundingClientRect();
  const menuPosition = rect
    ? {
        top: `${Math.max(8, rect.top)}px`,
        right: `${Math.max(8, window.innerWidth - rect.left + 8)}px`,
      }
    : undefined;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        aria-expanded={isOpen}
        aria-pressed={hasActiveFilter}
        className={cn(
          "w-9 h-9 rounded-lg flex items-center justify-center transition-all relative",
          hasActiveFilter
            ? "bg-zinc-800 text-zinc-100 ring-1 ring-zinc-600/70"
            : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50",
          isOpen && "bg-zinc-800 text-zinc-100",
        )}
        title={`Filter: ${current.label}`}
      >
        {current.icon}
        {hasActiveFilter && (
          <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-sky-400" />
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div
            className="fixed z-50 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden min-w-[150px]"
            style={menuPosition}
          >
            <div className="px-2 py-1.5 border-b border-zinc-800/60">
              <p className="text-[9px] font-semibold text-zinc-500 uppercase tracking-wider">表示フィルター</p>
            </div>
            <div className="py-0.5">
              {(["all", "tool", "widget", "system", "integration", "capability"] as const).map((filterId) => {
                const count = counts[filterId] ?? 0;
                if (filterId !== "all" && count === 0) return null;
                return (
                  <button
                    key={filterId}
                    onClick={() => {
                      onChange(filterId);
                      setIsOpen(false);
                    }}
                    className={cn("w-full flex items-center gap-2 px-2.5 py-1.5 text-left transition-colors", active === filterId ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200")}
                  >
                    <span className="flex-shrink-0">{CATEGORY_META[filterId].icon}</span>
                    <span className="text-[11px] font-medium flex-1">{CATEGORY_META[filterId].label}</span>
                    <span className="text-[9px] text-zinc-600 bg-zinc-800 px-1 py-0.5 rounded">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function RightSidebar({
  items,
  activeItemId,
  settingsValues,
  settingsSections,
  selectedToolIds = [],
  onSettingChange,
  onOpenSettings,
  onToolToggle,
  onPanelAction,
}: {
  items: SidebarItem[];
  activeItemId?: string | null;
  settingsValues: Record<string, Record<string, unknown>>;
  settingsSections: SettingsSection[];
  selectedToolIds?: string[];
  onSettingChange: (sectionId: string, fieldId: string, value: unknown) => void;
  onOpenSettings: () => void;
  onToolToggle?: (item: SidebarItem) => void;
  onPanelAction?: (item: SidebarItem, action: SidebarAction) => void;
}) {
  const [activePanel, setActivePanel] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<"all" | SidebarCategory>("all");
  const [openToolGroupMenu, setOpenToolGroupMenu] = useState<string | null>(null);
  const [toolGroupMenuPosition, setToolGroupMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const [pinnedItemIds, setPinnedItemIds] = useStoredStringArray("rumi-sidebar-pinned-item-ids");
  const [starredItemIds, setStarredItemIds] = useStoredStringArray("rumi-sidebar-starred-item-ids");
  const [showStarredOnly, setShowStarredOnly] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ itemId: string; x: number; y: number } | null>(null);
  const toolGroupMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedToolIdSet = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);
  const pinnedItemIdSet = useMemo(() => new Set(pinnedItemIds), [pinnedItemIds]);
  const starredItemIdSet = useMemo(() => new Set(starredItemIds), [starredItemIds]);

  useEffect(() => {
    const requestedId = activeItemId?.split(":").slice(0, -1).join(":") || activeItemId;
    if (requestedId && items.some((item) => item.id === requestedId)) {
      setActivePanel(requestedId);
    }
  }, [activeItemId, items]);

  useEffect(() => {
    if (!activePanel) return;
    if (activePanel === "__tool_manager__") return;
    if (!items.some((item) => item.id === activePanel)) {
      setActivePanel(null);
    }
  }, [activePanel, items]);

  useEffect(() => {
    if (!activePanel || categoryFilter === "all") return;
    const active = items.find((item) => item.id === activePanel);
    if (active && active.category !== categoryFilter) {
      setActivePanel(null);
    }
  }, [activePanel, categoryFilter, items]);

  useEffect(() => {
    if (!openToolGroupMenu) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (toolGroupMenuRef.current?.contains(target)) return;
      setOpenToolGroupMenu(null);
      setContextMenu(null);
    };

    const handleDocumentKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenToolGroupMenu(null);
        setContextMenu(null);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleDocumentKeyDown);
    };
  }, [openToolGroupMenu]);

  useEffect(() => {
    if (!contextMenu) return;

    const close = () => setContextMenu(null);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [contextMenu]);

  const counts = useMemo(() => {
    const next: Record<string, number> = { all: items.length };
    for (const item of items) {
      next[item.category] = (next[item.category] ?? 0) + 1;
    }
    return next;
  }, [items]);

  const toolItems = useMemo(() => sortedToolUiItems(items.filter((item) => (
    item.category === "tool"
    && (!showStarredOnly || starredItemIdSet.has(item.id))
  ))), [items, showStarredOnly, starredItemIdSet]);
  const groupedToolIds = useMemo(() => new Set(toolItems.map((item) => item.id)), [toolItems]);
  const toolGroups = useMemo(() => {
    const groups = new Map<string, SidebarItem[]>();
    for (const item of toolItems) {
      const gid = toolGroupFor(item).id;
      const list = groups.get(gid) ?? [];
      list.push(item);
      groups.set(gid, list);
    }
    return sortedToolGroups([...groups.entries()].map(([id, groupItems]) => {
      const meta = toolGroupFor(groupItems[0]);
      return { id, label: meta.label, icon: meta.icon, path: meta.path, items: groupItems, count: groupItems.length };
    }));
  }, [toolItems]);

  const showToolGroups = (categoryFilter === "all" || categoryFilter === "tool") && toolGroups.length > 0;

  const visibleItems = useMemo(() => {
    const base = (categoryFilter === "all" ? items : items.filter((item) => item.category === categoryFilter))
      .filter((item) => !showStarredOnly || starredItemIdSet.has(item.id));
    return [...base]
      .sort(compareSidebarItems)
      .filter((item) => item.category !== "tool" || !showToolGroups || !groupedToolIds.has(item.id) || pinnedItemIdSet.has(item.id));
  }, [items, categoryFilter, groupedToolIds, pinnedItemIdSet, showStarredOnly, showToolGroups, starredItemIdSet]);

  const activeItem = items.find((item) => item.id === activePanel) ?? null;
  const isToolManagerActive = activePanel === "__tool_manager__";
  const activeToolGroupId = activeItem?.category === "tool" ? toolGroupFor(activeItem).id : null;

  const handleDragStart = (event: DragEvent, item: SidebarItem) => {
    const kind = supportedComposerDropKind(item);
    if (!kind) return;
    const type = kind === "tool_toggle" ? "tool" : kind;
    event.dataTransfer.setData(
      "application/rumi-widget",
      JSON.stringify({
        id: item.id,
        type,
        label: item.ui?.composer_label ?? item.label,
        description: item.ui?.composer_description ?? item.description,
        icon: item.ui?.composer_icon ?? item.ui?.item_icon ?? item.ui?.group_icon,
        widgetKind: kind,
        action: item.ui?.composer_action,
        sourceItemId: item.id,
        enabled: selectedToolIdSet.has(item.id),
      }),
    );
    event.dataTransfer.effectAllowed = "copy";
  };

  const handleShortcutDragStart = (event: DragEvent, item: SidebarItem) => {
    handleDragStart(event, item);
    event.dataTransfer.setData("application/rumi-sidebar-shortcut", item.id);
  };

  const handleShortcutDrop = (event: DragEvent) => {
    const itemId = event.dataTransfer.getData("application/rumi-sidebar-shortcut");
    if (!itemId || pinnedItemIdSet.has(itemId) || !items.some((item) => item.id === itemId)) return;
    event.preventDefault();
    setPinnedItemIds((current) => [...current, itemId]);
    setOpenToolGroupMenu(null);
  };

  const togglePin = (itemId: string) => {
    setPinnedItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]);
  };

  const toggleStar = (itemId: string) => {
    setStarredItemIds((current) => current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]);
  };

  const openItemContextMenu = (event: MouseEvent, item: SidebarItem) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      itemId: item.id,
      x: Math.min(event.clientX, window.innerWidth - 190),
      y: Math.min(event.clientY, window.innerHeight - 150),
    });
  };

  const openToolGroup = (groupId: string, button: HTMLButtonElement) => {
    const rect = button.getBoundingClientRect();
    setToolGroupMenuPosition({
      top: Math.max(8, Math.min(rect.top, window.innerHeight - 300)),
      right: Math.max(8, window.innerWidth - rect.left + 8),
    });
    setOpenToolGroupMenu(groupId);
  };

  return (
    <aside className="flex-shrink-0 border-l border-zinc-800/60 bg-[#09090b] hidden md:flex h-full transition-[width,opacity] duration-200 ease-out">
      {(activeItem || isToolManagerActive) && (
        <div className="w-[250px] xl:w-[270px] flex flex-col border-r border-zinc-800/40 bg-[#0a0a0c] animate-in slide-in-from-right-2 duration-200">
          <div className="h-10 flex items-center justify-between px-2.5 border-b border-zinc-800/60 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0 overflow-hidden">
              <div className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", activeItem ? categoryColor(activeItem.category, "bg") : "bg-emerald-500")} />
              <h3 className="text-[13px] font-medium text-zinc-100 truncate">{activeItem?.label ?? "Tool manager"}</h3>
              {activeItem?.badge && (
                <span className="text-[8px] bg-emerald-500/20 text-emerald-400 px-1 py-0.5 rounded-full font-bold flex-shrink-0">
                  {activeItem.badge}
                </span>
              )}
            </div>
            {activeItem?.category === "tool" && (
              <button
                type="button"
                onClick={() => onToolToggle?.(activeItem)}
                className={cn(
                  "p-1 rounded transition-colors",
                  selectedToolIdSet.has(activeItem.id) ? "text-emerald-400 hover:bg-emerald-500/10" : "text-zinc-600 hover:bg-zinc-800",
                )}
                title={selectedToolIdSet.has(activeItem.id) ? "無効にする" : "有効にする"}
              >
                <Power size={14} />
              </button>
            )}
          </div>

          {activeItem?.description && (
            <div className="px-2.5 py-1.5 border-b border-zinc-800/40">
              <p className="text-[10px] text-zinc-500">{activeItem.description}</p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-2.5">
            {activeItem ? (
              <SidebarPanel item={activeItem} settingsValues={settingsValues} onSettingChange={onSettingChange} onPanelAction={onPanelAction} />
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-2">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-600">Tools</p>
                    <p className="mt-1 text-lg font-semibold text-zinc-100">{toolItems.length}</p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-2">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-600">On</p>
                    <p className="mt-1 text-lg font-semibold text-emerald-300">{selectedToolIds.length}</p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-2">
                    <p className="text-[9px] uppercase tracking-wider text-zinc-600">Star</p>
                    <p className="mt-1 text-lg font-semibold text-amber-300">{starredItemIds.length}</p>
                  </div>
                </div>
                <div className="space-y-1">
                  {toolItems.map((item) => {
                    const enabled = selectedToolIdSet.has(item.id);
                    const pinned = pinnedItemIdSet.has(item.id);
                    const starred = starredItemIdSet.has(item.id);
                    return (
                      <div key={item.id} className="rounded-lg border border-zinc-800/70 bg-zinc-950/45 p-2">
                        <div className="flex items-start gap-2">
                          <button
                            type="button"
                            onClick={() => setActivePanel(item.id)}
                            onContextMenu={(event) => openItemContextMenu(event, item)}
                            className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-zinc-900 text-zinc-500 hover:text-zinc-200"
                            title={item.label}
                          >
                            {iconForItem(item)}
                          </button>
                          <button
                            type="button"
                            onClick={() => setActivePanel(item.id)}
                            onContextMenu={(event) => openItemContextMenu(event, item)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <span className="block truncate text-[12px] font-medium text-zinc-200">{item.label}</span>
                            {item.description && <span className="block truncate text-[10px] text-zinc-500">{item.description}</span>}
                          </button>
                          <div className="flex flex-shrink-0 items-center gap-0.5">
                            <button
                              type="button"
                              onClick={() => toggleStar(item.id)}
                              className={cn("rounded-md p-1 transition-colors", starred ? "text-amber-300 hover:bg-amber-500/10" : "text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300")}
                              title={starred ? "スター解除" : "スター"}
                            >
                              <Star size={13} className={cn(starred && "fill-current")} />
                            </button>
                            <button
                              type="button"
                              onClick={() => togglePin(item.id)}
                              className={cn("rounded-md p-1 transition-colors", pinned ? "text-sky-300 hover:bg-sky-500/10" : "text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300")}
                              title={pinned ? "ピン留め解除" : "ピン留め"}
                            >
                              {pinned ? <PinOff size={13} /> : <Pin size={13} />}
                            </button>
                            <button
                              type="button"
                              onClick={() => onToolToggle?.(item)}
                              className={cn("rounded-md p-1 transition-colors", enabled ? "text-emerald-300 hover:bg-emerald-500/10" : "text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300")}
                              title={enabled ? "無効にする" : "有効にする"}
                            >
                              <Power size={13} />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="w-11 flex flex-col flex-shrink-0 overflow-hidden">
        <div
          className="flex-1 flex flex-col items-center gap-px overflow-y-auto w-full py-1 scrollbar-none"
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes("application/rumi-sidebar-shortcut")) {
              event.preventDefault();
              event.dataTransfer.dropEffect = "copy";
            }
          }}
          onDrop={handleShortcutDrop}
        >
          <CategorySwitcher active={categoryFilter} counts={counts} onChange={(id) => { setCategoryFilter(id); setOpenToolGroupMenu(null); }} />
          <button
            type="button"
            onClick={() => setShowStarredOnly((value) => !value)}
            aria-pressed={showStarredOnly}
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center relative transition-all",
              showStarredOnly
                ? "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
            )}
            title="Starred tools"
          >
            <Star size={16} className={cn(starredItemIds.length > 0 && "fill-current")} />
            {starredItemIds.length > 0 && (
              <span className="absolute -top-0.5 -right-0.5 rounded-full bg-zinc-700 px-0.5 text-[7px] leading-tight text-zinc-200">
                {starredItemIds.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setActivePanel((current) => (current === "__tool_manager__" ? null : "__tool_manager__"))}
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center relative transition-all",
              activePanel === "__tool_manager__"
                ? "bg-zinc-800 text-zinc-100 ring-1 ring-zinc-600/70"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
            )}
            title="Tool manager"
          >
            <SlidersHorizontal size={16} />
            {selectedToolIds.length > 0 && (
              <span className="absolute -top-0.5 -right-0.5 rounded-full bg-emerald-500 px-0.5 text-[7px] font-bold leading-tight text-black">
                {selectedToolIds.length}
              </span>
            )}
          </button>
          <div className="w-5 h-px bg-zinc-800 my-1" />

          {showToolGroups && (
            <div ref={toolGroupMenuRef} className="flex flex-col items-center gap-px w-full">
              {toolGroups.map((group) => {
                const isGroupActive = activeToolGroupId === group.id;
                const isGroupOpen = openToolGroupMenu === group.id;
                return (
                <div key={group.id} className="relative">
                  <button
                    type="button"
                    onClick={(event) => {
                      if (group.items.length === 1) {
                        setActivePanel(group.items[0].id);
                        setOpenToolGroupMenu(null);
                        return;
                      }
                      if (openToolGroupMenu === group.id) {
                        setOpenToolGroupMenu(null);
                        return;
                      }
                      openToolGroup(group.id, event.currentTarget);
                    }}
                    className={cn(
                      "group/group w-9 h-9 rounded-lg flex items-center justify-center relative transition-all flex-shrink-0",
                      isGroupOpen || isGroupActive
                        ? "bg-emerald-900/40 text-emerald-300 border border-emerald-500/30"
                        : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
                    )}
                    title={`${group.path?.length ? group.path.join(" / ") : group.label || TOOL_GROUP_LABELS[group.id] || group.id} (${group.count})`}
                  >
                    {(group.icon && TOOL_GROUP_ICONS[group.icon]) || TOOL_GROUP_ICONS[group.id] || <Wrench size={16} />}
                    <span className="absolute -top-0.5 -right-0.5 text-[7px] bg-zinc-700 text-zinc-300 px-0.5 rounded-full leading-tight">
                      {group.count}
                    </span>
                    <span className="absolute right-full mr-2 px-2 py-1 bg-zinc-800 text-zinc-200 text-[10px] rounded-md opacity-0 group-hover/group:opacity-100 pointer-events-none transition-opacity whitespace-nowrap border border-zinc-700 shadow-lg z-40">
                      {group.path?.length && group.path.length > 1 ? group.path.join(" / ") : group.label || TOOL_GROUP_LABELS[group.id] || group.id}
                    </span>
                    {(isGroupActive || isGroupOpen) && (
                      <div className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-emerald-500" />
                    )}
                  </button>
                  {openToolGroupMenu === group.id && (
                    <div
                      className="fixed z-50 w-56 overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 py-1 text-left shadow-2xl"
                      style={toolGroupMenuPosition ? { top: `${toolGroupMenuPosition.top}px`, right: `${toolGroupMenuPosition.right}px` } : undefined}
                    >
                      <div className="border-b border-zinc-800 px-3 py-2">
                        <p className="truncate text-[11px] font-semibold text-zinc-200">{group.label || TOOL_GROUP_LABELS[group.id] || group.id}</p>
                        {group.path?.length && group.path.length > 1 && (
                          <p className="truncate text-[10px] text-zinc-500">{group.path.join(" / ")}</p>
                        )}
                        <p className="text-[10px] text-zinc-500">{group.count} tools</p>
                      </div>
                      <div className="max-h-64 overflow-y-auto py-1">
                        {group.items.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            draggable={supportsComposerDrop(item)}
                            onDragStart={supportsComposerDrop(item) ? (event) => handleShortcutDragStart(event, item) : undefined}
                            onContextMenu={(event) => openItemContextMenu(event, item)}
                            onClick={(event) => {
                              event.stopPropagation();
                              setActivePanel(item.id);
                              setOpenToolGroupMenu(null);
                            }}
                            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-zinc-300 transition-colors hover:bg-zinc-800/80 hover:text-zinc-100"
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-zinc-900 text-zinc-500">
                                {iconForItem(item)}
                              </span>
                              <span className="min-w-0">
                                <span className="block truncate text-[12px]">{item.label}</span>
                                {item.description && <span className="block truncate text-[10px] text-zinc-500">{item.description}</span>}
                              </span>
                            </span>
                            {item.category === "tool" && (
                              <span className="flex flex-shrink-0 items-center gap-1">
                                {starredItemIdSet.has(item.id) && <Star size={10} className="fill-current text-amber-300" />}
                                {pinnedItemIdSet.has(item.id) && <Pin size={10} className="text-sky-300" />}
                                <span className={cn("h-1.5 w-1.5 rounded-full", selectedToolIdSet.has(item.id) ? "bg-emerald-400" : "bg-zinc-700")} />
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
              })}
            </div>
          )}

          {showToolGroups && visibleItems.length > 0 && (
            <div className="w-5 h-px bg-zinc-800 my-1" />
          )}

          {visibleItems.map((item) => (
            <button
              key={item.id}
              draggable={supportsComposerDrop(item)}
              onDragStart={supportsComposerDrop(item) ? (e) => handleDragStart(e, item) : undefined}
              onContextMenu={(event) => openItemContextMenu(event, item)}
              onClick={() => setActivePanel((current) => (current === item.id ? null : item.id))}
              className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center relative transition-all duration-150 ease-out group/btn flex-shrink-0 hover:scale-[1.03] active:scale-95",
                activePanel === item.id
                  ? "bg-zinc-800 text-zinc-100 ring-1 ring-zinc-600/70"
                  : item.category === "tool" && !selectedToolIdSet.has(item.id)
                    ? "text-zinc-700 hover:text-zinc-500 hover:bg-zinc-800/30"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
              )}
              title={item.label}
            >
              {iconForItem(item)}

              {activePanel === item.id && (
                <div className={cn("absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full", categoryColor(item.category, "indicator"))} />
              )}

              {item.category === "tool" && !selectedToolIdSet.has(item.id) && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-6 h-px bg-zinc-600 rotate-45" />
                </div>
              )}

              {item.badge && (
                <span className="absolute -top-0.5 -right-0.5 text-[6px] bg-emerald-500 text-black px-0.5 rounded-full font-bold leading-tight">
                  {item.badge}
                </span>
              )}

              {(starredItemIdSet.has(item.id) || pinnedItemIdSet.has(item.id)) && !item.badge && (
                <span className="absolute -top-0.5 -right-0.5 flex items-center gap-px rounded-full bg-zinc-900 px-0.5 text-[7px] leading-tight ring-1 ring-zinc-700">
                  {starredItemIdSet.has(item.id) && <Star size={8} className="fill-current text-amber-300" />}
                  {pinnedItemIdSet.has(item.id) && <Pin size={8} className="text-sky-300" />}
                </span>
              )}

              {activePanel !== item.id && (
                <div
                  className={cn(
                    "absolute bottom-0.5 right-0.5 w-1 h-1 rounded-full opacity-0 group-hover/btn:opacity-100 transition-opacity",
                    categoryColor(item.category, "dot"),
                  )}
                />
              )}

              <span className="absolute right-full mr-2 px-2 py-1 bg-zinc-800 text-zinc-200 text-[10px] rounded-md opacity-0 group-hover/btn:opacity-100 pointer-events-none transition-opacity whitespace-nowrap border border-zinc-700 shadow-lg z-50">
                {item.label}
                <span className={cn("ml-1 text-[8px] px-1 py-px rounded", categoryColor(item.category, "badge"))}>
                  {item.category}
                </span>
              </span>
            </button>
          ))}

          {contextMenu && (() => {
            const item = items.find((candidate) => candidate.id === contextMenu.itemId);
            if (!item) return null;
            const pinned = pinnedItemIdSet.has(item.id);
            const starred = starredItemIdSet.has(item.id);
            const enabled = selectedToolIdSet.has(item.id);
            return (
              <div
                className="fixed z-[70] w-44 overflow-hidden rounded-xl border border-zinc-700/70 bg-zinc-950 py-1 text-left shadow-2xl"
                style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <div className="border-b border-zinc-800 px-3 py-2">
                  <p className="truncate text-[11px] font-semibold text-zinc-200">{item.label}</p>
                  <p className="truncate text-[10px] text-zinc-500">{item.category}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    togglePin(item.id);
                    setContextMenu(null);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"
                >
                  {pinned ? <PinOff size={13} /> : <Pin size={13} />}
                  <span>{pinned ? "ピン留め解除" : "ピン留め"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    toggleStar(item.id);
                    setContextMenu(null);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"
                >
                  <Star size={13} className={cn(starred && "fill-current text-amber-300")} />
                  <span>{starred ? "スター解除" : "スター"}</span>
                </button>
                {item.category === "tool" && (
                  <button
                    type="button"
                    onClick={() => {
                      onToolToggle?.(item);
                      setContextMenu(null);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"
                  >
                    <Power size={13} className={enabled ? "text-emerald-300" : undefined} />
                    <span>{enabled ? "Tool を off" : "Tool を on"}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setActivePanel(item.id);
                    setContextMenu(null);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"
                >
                  <MoreVertical size={13} />
                  <span>詳細を開く</span>
                </button>
              </div>
            );
          })()}

          <div className="mt-auto w-5 h-px bg-zinc-800 my-1" />

          <button
            onClick={onOpenSettings}
            className="relative w-9 h-9 rounded-lg flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-all group/btn flex-shrink-0"
            title="Settings"
          >
            <Settings size={18} />
            <span className="absolute right-full mr-2 px-2 py-1 bg-zinc-800 text-zinc-200 text-[10px] rounded-md opacity-0 group-hover/btn:opacity-100 pointer-events-none transition-opacity whitespace-nowrap border border-zinc-700 shadow-lg z-50">
              Settings
            </span>
          </button>
        </div>
      </div>
    </aside>
  );
}
