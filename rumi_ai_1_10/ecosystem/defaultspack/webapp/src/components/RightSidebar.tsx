import { useEffect, useMemo, useState, type DragEvent, type ReactElement } from "react";
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

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
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
  research: <Search size={16} />,
  operate: <Monitor size={16} />,
  manage: <Cpu size={16} />,
  other: <Wrench size={16} />,
};

const TOOL_GROUP_LABELS: Record<string, string> = {
  coding: "Coding",
  research: "調べる",
  operate: "操作する",
  manage: "管理",
  other: "その他",
};

const ITEM_ICONS: Record<string, ReactElement> = {
  artifacts: <Archive size={18} />,
  browser_computer: <Monitor size={18} />,
  calculator: <BrainCircuit size={18} />,
  code: <Terminal size={18} />,
  coding_file_read: <FileText size={18} />,
  coding_file_write: <FileText size={18} />,
  coding_file_create: <FileText size={18} />,
  coding_file_delete: <FileText size={18} />,
  coding_file_list: <FileText size={18} />,
  coding_file_search: <Search size={18} />,
  coding_file_patch: <FileText size={18} />,
  coding_file_restore: <FileText size={18} />,
  coding_git_status: <GitBranch size={18} />,
  coding_git_diff: <GitBranch size={18} />,
  coding_git_commit: <GitBranch size={18} />,
  coding_git_push: <GitBranch size={18} />,
  coding_terminal_exec: <Terminal size={18} />,
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

function actionIcon(action: SidebarAction) {
  const key = action.icon || action.id.split(".")[0] || "play";
  return ACTION_ICONS[key] ?? <Play size={13} />;
}

function iconForItem(item: SidebarItem) {
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

function toolGroupId(item: SidebarItem): string {
  if (item.category !== "tool") return "";
  const haystack = `${item.id} ${item.label} ${item.description ?? ""} ${(item.tags ?? []).join(" ")}`.toLowerCase();
  if (/^coding_/.test(item.id) || /(coding|git|terminal|file)/.test(haystack)) return "coding";
  if (/(search|research|web|reddit|knowledge)/.test(haystack)) return "research";
  if (/(browser|computer|screen|screenshot)/.test(haystack)) return "operate";
  if (/(artifact|memory|prompt|template)/.test(haystack)) return "manage";
  return "other";
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
  const actions = panel?.actions ?? [];

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

      {fields.length > 0 && (
        <div className="space-y-2.5">
          {fields.map((field) => {
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
          })}
        </div>
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
  const current = CATEGORY_META[active];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen((value) => !value)}
        className={cn("w-9 h-9 rounded-lg flex items-center justify-center transition-all", "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50", isOpen && "bg-zinc-800 text-zinc-100")}
        title={`Filter: ${current.label}`}
      >
        {current.icon}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-full mr-2 top-0 z-50 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden min-w-[150px]">
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
  onSettingChange,
  onOpenSettings,
  onPanelAction,
}: {
  items: SidebarItem[];
  activeItemId?: string | null;
  settingsValues: Record<string, Record<string, unknown>>;
  settingsSections: SettingsSection[];
  onSettingChange: (sectionId: string, fieldId: string, value: unknown) => void;
  onOpenSettings: () => void;
  onPanelAction?: (item: SidebarItem, action: SidebarAction) => void;
}) {
  const [activePanel, setActivePanel] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<"all" | SidebarCategory>("all");
  const [toolGroupFilter, setToolGroupFilter] = useState<string | null>(null);
  const [toolEnabledState, setToolEnabledState] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const requestedId = activeItemId?.split(":").slice(0, -1).join(":") || activeItemId;
    if (requestedId && items.some((item) => item.id === requestedId)) {
      setActivePanel(requestedId);
    }
  }, [activeItemId, items]);

  useEffect(() => {
    if (!activePanel) return;
    if (!items.some((item) => item.id === activePanel)) {
      setActivePanel(null);
    }
  }, [activePanel, items]);

  const counts = useMemo(() => {
    const next: Record<string, number> = { all: items.length };
    for (const item of items) {
      next[item.category] = (next[item.category] ?? 0) + 1;
    }
    return next;
  }, [items]);

  const toolItems = useMemo(() => items.filter((item) => item.category === "tool"), [items]);
  const toolGroups = useMemo(() => {
    const groups = new Map<string, SidebarItem[]>();
    for (const item of toolItems) {
      const gid = toolGroupId(item);
      const list = groups.get(gid) ?? [];
      list.push(item);
      groups.set(gid, list);
    }
    return [...groups.entries()].map(([id, groupItems]) => ({ id, items: groupItems, count: groupItems.length }));
  }, [toolItems]);

  const visibleItems = useMemo(() => {
    let filtered = categoryFilter === "all" ? items : items.filter((item) => item.category === categoryFilter);
    if (categoryFilter === "all" || categoryFilter === "tool") {
      if (toolGroupFilter) {
        filtered = filtered.filter((item) => item.category !== "tool" || toolGroupId(item) === toolGroupFilter);
      }
    }
    return filtered;
  }, [items, categoryFilter, toolGroupFilter]);

  const activeItem = items.find((item) => item.id === activePanel) ?? null;

  const toggleToolEnabled = (itemId: string) => {
    setToolEnabledState((prev) => ({ ...prev, [itemId]: !(prev[itemId] ?? true) }));
  };

  const handleDragStart = (event: DragEvent, item: SidebarItem) => {
    event.dataTransfer.setData(
      "application/rumi-widget",
      JSON.stringify({ id: item.id, type: "tool", label: item.label, enabled: toolEnabledState[item.id] ?? true }),
    );
    event.dataTransfer.effectAllowed = "copy";
  };

  return (
    <aside className="flex-shrink-0 border-l border-zinc-800/60 bg-[#09090b] hidden md:flex h-full transition-[width,opacity] duration-200 ease-out">
      {activeItem && (
        <div className="w-[250px] xl:w-[270px] flex flex-col border-r border-zinc-800/40 bg-[#0a0a0c] animate-in slide-in-from-right-2 duration-200">
          <div className="h-10 flex items-center justify-between px-2.5 border-b border-zinc-800/60 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0 overflow-hidden">
              <div className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", categoryColor(activeItem.category, "bg"))} />
              <h3 className="text-[13px] font-medium text-zinc-100 truncate">{activeItem.label}</h3>
              {activeItem.badge && (
                <span className="text-[8px] bg-emerald-500/20 text-emerald-400 px-1 py-0.5 rounded-full font-bold flex-shrink-0">
                  {activeItem.badge}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => toggleToolEnabled(activeItem.id)}
              className={cn(
                "p-1 rounded transition-colors",
                toolEnabledState[activeItem.id] ?? true ? "text-emerald-400 hover:bg-emerald-500/10" : "text-zinc-600 hover:bg-zinc-800",
              )}
              title={toolEnabledState[activeItem.id] ?? true ? "無効にする" : "有効にする"}
            >
              <Power size={14} />
            </button>
          </div>

          {activeItem.description && (
            <div className="px-2.5 py-1.5 border-b border-zinc-800/40">
              <p className="text-[10px] text-zinc-500">{activeItem.description}</p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-2.5">
            <SidebarPanel item={activeItem} settingsValues={settingsValues} onSettingChange={onSettingChange} onPanelAction={onPanelAction} />
          </div>
        </div>
      )}

      <div className="w-11 flex flex-col items-center py-1 gap-px flex-shrink-0">
        <CategorySwitcher active={categoryFilter} counts={counts} onChange={(id) => { setCategoryFilter(id); setToolGroupFilter(null); }} />
        <div className="w-5 h-px bg-zinc-800 my-1" />

        {(categoryFilter === "all" || categoryFilter === "tool") && toolGroups.length > 1 && (
          <>
            <div className="flex flex-col items-center gap-px w-full">
              {toolGroups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => setToolGroupFilter((current) => (current === group.id ? null : group.id))}
                  className={cn(
                    "w-9 h-9 rounded-lg flex items-center justify-center relative transition-all flex-shrink-0",
                    toolGroupFilter === group.id
                      ? "bg-emerald-900/40 text-emerald-300 border border-emerald-500/30"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
                  )}
                  title={`${TOOL_GROUP_LABELS[group.id] ?? group.id} (${group.count})`}
                >
                  {TOOL_GROUP_ICONS[group.id] ?? <Wrench size={16} />}
                  <span className="absolute -top-0.5 -right-0.5 text-[7px] bg-zinc-700 text-zinc-300 px-0.5 rounded-full leading-tight">
                    {group.count}
                  </span>
                  <span className="absolute right-full mr-2 px-2 py-1 bg-zinc-800 text-zinc-200 text-[10px] rounded-md opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap border border-zinc-700 shadow-lg z-50">
                    {TOOL_GROUP_LABELS[group.id] ?? group.id}
                  </span>
                </button>
              ))}
            </div>
            <div className="w-5 h-px bg-zinc-800 my-1" />
          </>
        )}

        <div className="flex-1 flex flex-col items-center gap-px overflow-y-auto w-full scrollbar-none">
          {visibleItems.map((item) => (
            <button
              key={item.id}
              draggable={item.category === "tool"}
              onDragStart={item.category === "tool" ? (e) => handleDragStart(e, item) : undefined}
              onClick={() => setActivePanel((current) => (current === item.id ? null : item.id))}
              className={cn(
                "w-9 h-9 rounded-lg flex items-center justify-center relative transition-all duration-150 ease-out group/btn flex-shrink-0 hover:scale-[1.03] active:scale-95",
                activePanel === item.id
                  ? "bg-zinc-800 text-zinc-100"
                  : item.category === "tool" && !(toolEnabledState[item.id] ?? true)
                    ? "text-zinc-700 hover:text-zinc-500 hover:bg-zinc-800/30"
                    : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50",
              )}
              title={item.label}
            >
              {iconForItem(item)}

              {activePanel === item.id && (
                <div className={cn("absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full", categoryColor(item.category, "indicator"))} />
              )}

              {item.category === "tool" && !(toolEnabledState[item.id] ?? true) && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-6 h-px bg-zinc-600 rotate-45" />
                </div>
              )}

              {item.badge && (
                <span className="absolute -top-0.5 -right-0.5 text-[6px] bg-emerald-500 text-black px-0.5 rounded-full font-bold leading-tight">
                  {item.badge}
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
        </div>

        <div className="w-5 h-px bg-zinc-800 my-1" />

        <button
          onClick={onOpenSettings}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-all group/btn flex-shrink-0"
          title="Settings"
        >
          <Settings size={18} />
          <span className="absolute right-full mr-2 px-2 py-1 bg-zinc-800 text-zinc-200 text-[10px] rounded-md opacity-0 group-hover/btn:opacity-100 pointer-events-none transition-opacity whitespace-nowrap border border-zinc-700 shadow-lg z-50">
            Settings
          </span>
        </button>
      </div>
    </aside>
  );
}
