import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";

import { CompanyWorkspacePanel } from "./components/company/CompanyWorkspacePanel";
import { CodingCockpit } from "./components/coding/CodingCockpit";
import { ConversationSpotlight } from "./components/ConversationSpotlight";
import { WarmActionIcon } from "./components/WarmActionIcon";
import type { ChatItem, HistoryBoardNewTaskOptions } from "./components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "./components/ToolPreview";
import { buildToolPreviewDisplayItems, hasCanvasItems } from "./components/ToolPreview";
import { api, defaultspackApiFetch, type ChatActivityEvent, type ChatContentBlock, type ChatMessage, type ChatStreamEvent, type ChatToolStreamEvent, type CodingWorkspaceRecord, type ComposerCommandExecuteResult, type ComposerCommandItem, type ComposerCommandMode, type ComposerWidgetAction, type Conversation, type ConversationSearchResult, type ConversationSteerItem, type ModelCommandCandidate, type ModelProfile, type OperationsCompanyStatus, type SettingsSection, type SidebarAction, type SidebarItem, type UICatalog } from "./lib/api";
import { pendingBrowserApproval, pendingRuntimeApproval, staleRuntimeApproval, type BrowserApproval, type RuntimeApproval, type StaleRuntimeApproval } from "./lib/browserApproval";
import { reduceBrowserStateFromEvents } from "./lib/browserState";
import { deriveConversationTitle, formatRelativeTime, messageToText, orderConversationMessages } from "./lib/chat";
import { cn } from "./lib/cn";
import { canExecuteComposerEndpointAction, composerSkillMentionWidget, composerToolMentionWidget, isSafeLocalEndpoint, skillMentionIdsFromText, toolMentionIdsFromText } from "./lib/composerWidgets";
import { conversationMatchesSpotlightFilter, conversationToSearchResult, type SpotlightFilter } from "./lib/conversationSpotlight";
import { boundedDurationLabel } from "./lib/duration";
import { fetchDesktopSystemInfo, type DesktopSystemInfo } from "./lib/desktopSystemInfo";
import { normalizeLocale } from "./lib/i18n";
import { PENDING_CHAT_REQUEST_TTL_MS, shouldClearPendingAfterConversationRefresh, type PendingChatRequest } from "./lib/pendingChat";
import { isRecord, toolPreviewsFromMessages, upsertStreamActivityEvent } from "./lib/toolPreviews";
import { extractLatestToolFilterContext } from "./lib/toolStatus";
import { hasShellRegion } from "./lib/uiShell";
import { hasWorkspaceAttachment, workspaceFileToAttachment } from "./lib/workspaceAttachments";
import { resolveDefaultspackRenderers } from "./renderers/defaultspackRenderers";
import { RendererBoundary } from "./renderers/trustedRendererLoader";
import type { AppMode, AttachedFile, ChatUiMessage, CodingContext, ComposerExtensionItem, ComposerModelStatusIndicator, ComposerSkillItem, ContextUsageInfo, DroppedWidget } from "./renderers/types";

type ComposerCandidateMenuState = {
  mode: "model";
  query: string;
  candidates: ModelCommandCandidate[];
} | null;

type WorkspacePanelMode = "composer" | "calendar";

type PendingNewTaskContext = {
  groupId?: string;
  workspaceId?: string | null;
  workspaceLabel?: string | null;
  workspaceRoot?: string | null;
  rumiDataPath?: string | null;
};

type CalendarItemKind = "task" | "event" | "reminder";

type CalendarItem = {
  id: string;
  date: string;
  endDate?: string;
  agentPrompt?: string;
  kind: CalendarItemKind;
  lastRunStatus?: string;
  scheduleId?: string;
  scheduleStatus?: string;
  title: string;
  time?: string;
};

type CalendarSettings = {
  agentCurrentChat: boolean;
  agentModel: string;
  agentTaskDefault: boolean;
  defaultTime: string;
  defaultItemType: CalendarItemKind;
  dimWeekends: boolean;
  eventColor: "green" | "blue" | "slate";
  maxItemsPerDay: number;
  quickAddEnabled: boolean;
  showOutsideDays: boolean;
  showTimePicker: boolean;
  taskColor: "blue" | "cyan" | "slate";
  timeSlotMinutes: 15 | 30 | 60;
  weekStart: "sunday" | "monday";
};

type CalendarCell = {
  col: number;
  date: Date;
  isCurrentMonth: boolean;
  isToday: boolean;
  key: string;
  label: string;
  row: number;
};

type CalendarEditorState = {
  cell: CalendarCell;
  endKey: string;
  itemId?: string;
  mode: "create" | "edit";
  startKey: string;
};

type CalendarDragState = {
  currentKey: string;
  startKey: string;
  startedAt: number;
};

const dangerShieldSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="20" fill="#2d2e2f"/>
  <g fill="none" stroke="#fca355" stroke-linecap="round" stroke-linejoin="round">
    <path
      d="M 50,25
         C 62,25 72,28 75,32
         C 75,55 68,70 50,78
         C 32,70 25,55 25,32
         C 28,28 38,25 50,25 Z"
      stroke-width="5"
    />
    <line x1="50" y1="40" x2="50" y2="55" stroke-width="5.5"/>
    <line x1="50" y1="64" x2="50" y2="64.1" stroke-width="6"/>
  </g>
</svg>`;

const calendarSettingsDefaults: CalendarSettings = {
  agentCurrentChat: false,
  agentModel: "",
  agentTaskDefault: false,
  defaultTime: "09:00",
  defaultItemType: "task",
  dimWeekends: true,
  eventColor: "green",
  maxItemsPerDay: 3,
  quickAddEnabled: true,
  showOutsideDays: true,
  showTimePicker: true,
  taskColor: "blue",
  timeSlotMinutes: 15,
  weekStart: "sunday",
};

const calendarSettingsSection: SettingsSection = {
  id: "calendar",
  label: "カレンダー",
  description: "カレンダー画面のクリック追加、週表示、予定色を調整します。",
  fields: [
    {
      id: "quick_add_enabled",
      label: "クリックで追加",
      type: "toggle",
      default: calendarSettingsDefaults.quickAddEnabled,
      help: "日付セルをクリックした時に、新規追加カードを開きます。",
    },
    {
      id: "default_item_type",
      label: "既定の種類",
      type: "select",
      default: calendarSettingsDefaults.defaultItemType,
      options: [
        { value: "task", label: "タスク / 青" },
        { value: "event", label: "予定 / 緑" },
        { value: "reminder", label: "リマインダー / グレー" },
      ],
      help: "新規追加カードで最初に選ばれる種類です。",
    },
    {
      id: "default_time",
      label: "既定時刻",
      type: "text",
      default: calendarSettingsDefaults.defaultTime,
      help: "新規追加カードの初期時刻です。例: 09:00 / 午前9:00",
    },
    {
      id: "time_slot_minutes",
      label: "時刻の刻み幅",
      type: "select",
      default: calendarSettingsDefaults.timeSlotMinutes,
      options: [
        { value: 15, label: "15分" },
        { value: 30, label: "30分" },
        { value: 60, label: "60分" },
      ],
      help: "時刻ドロップダウンの刻み幅です。",
    },
    {
      id: "show_time_picker",
      label: "時刻候補を表示",
      type: "toggle",
      default: calendarSettingsDefaults.showTimePicker,
      help: "時刻入力時にスクロール式の候補を表示します。",
    },
    {
      id: "agent_task_default",
      label: "Agentタスクを既定ON",
      type: "toggle",
      default: calendarSettingsDefaults.agentTaskDefault,
      help: "Task作成時に、AI agent実行の候補を初期ONにします。",
    },
    {
      id: "agent_model",
      label: "Agentモデル",
      type: "text",
      default: calendarSettingsDefaults.agentModel,
      help: "空なら設定済みの非embeddingモデルを自動選択します。例: google/gemini-2.5-flash",
    },
    {
      id: "agent_current_chat",
      label: "現在のチャットで実行",
      type: "toggle",
      default: calendarSettingsDefaults.agentCurrentChat,
      help: "ONなら予定時刻に現在の会話へ送信します。OFFなら独立したagent実行にします。",
    },
    {
      id: "week_start",
      label: "週の開始曜日",
      type: "select",
      default: calendarSettingsDefaults.weekStart,
      options: [
        { value: "sunday", label: "日曜日" },
        { value: "monday", label: "月曜日" },
      ],
      help: "月表示の左端の曜日を選びます。",
    },
    {
      id: "show_outside_days",
      label: "前後月の日付を表示",
      type: "toggle",
      default: calendarSettingsDefaults.showOutsideDays,
      help: "前月/翌月の日付を薄く表示します。",
    },
    {
      id: "dim_weekends",
      label: "週末を薄く表示",
      type: "toggle",
      default: calendarSettingsDefaults.dimWeekends,
      help: "土日セルをほんの少し暗くします。",
    },
    {
      id: "task_color",
      label: "タスクの色",
      type: "select",
      default: calendarSettingsDefaults.taskColor,
      options: [
        { value: "blue", label: "青" },
        { value: "cyan", label: "シアン" },
        { value: "slate", label: "スレート" },
      ],
      help: "Taskバーの色。既定は青です。",
    },
    {
      id: "event_color",
      label: "予定の色",
      type: "select",
      default: calendarSettingsDefaults.eventColor,
      options: [
        { value: "green", label: "緑" },
        { value: "blue", label: "青" },
        { value: "slate", label: "スレート" },
      ],
      help: "Eventバーの色。休日や予定は緑寄りにできます。",
    },
    {
      id: "max_items_per_day",
      label: "1日の表示件数",
      type: "number",
      default: calendarSettingsDefaults.maxItemsPerDay,
      min: 1,
      max: 6,
      help: "1日に表示する予定バーの上限です。",
    },
  ],
};

function withCalendarSettingsSections(sections: SettingsSection[]): SettingsSection[] {
  if (sections.some((section) => section.id === calendarSettingsSection.id)) return sections;
  const insertAfter = sections.findIndex((section) => section.id === "preview");
  if (insertAfter < 0) return [...sections, calendarSettingsSection];
  return [
    ...sections.slice(0, insertAfter + 1),
    calendarSettingsSection,
    ...sections.slice(insertAfter + 1),
  ];
}

function withCalendarSettingsValues(values: Record<string, Record<string, unknown>>): Record<string, Record<string, unknown>> {
  return {
    ...values,
    calendar: {
      agent_current_chat: calendarSettingsDefaults.agentCurrentChat,
      agent_model: calendarSettingsDefaults.agentModel,
      agent_task_default: calendarSettingsDefaults.agentTaskDefault,
      default_time: calendarSettingsDefaults.defaultTime,
      quick_add_enabled: calendarSettingsDefaults.quickAddEnabled,
      default_item_type: calendarSettingsDefaults.defaultItemType,
      week_start: calendarSettingsDefaults.weekStart,
      show_outside_days: calendarSettingsDefaults.showOutsideDays,
      show_time_picker: calendarSettingsDefaults.showTimePicker,
      dim_weekends: calendarSettingsDefaults.dimWeekends,
      task_color: calendarSettingsDefaults.taskColor,
      time_slot_minutes: calendarSettingsDefaults.timeSlotMinutes,
      event_color: calendarSettingsDefaults.eventColor,
      max_items_per_day: calendarSettingsDefaults.maxItemsPerDay,
      ...(values.calendar ?? {}),
    },
  };
}

function calendarDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function calendarDateLabel(date: Date): string {
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

function calendarDateFromKey(key: string): Date {
  const [year, month, day] = key.split("-").map((part) => Number(part));
  return new Date(year, month - 1, day);
}

function compareCalendarKeys(a: string, b: string): number {
  return calendarDateFromKey(a).getTime() - calendarDateFromKey(b).getTime();
}

function orderedCalendarRange(startKey: string, endKey: string): [string, string] {
  return compareCalendarKeys(startKey, endKey) <= 0 ? [startKey, endKey] : [endKey, startKey];
}

function calendarKeysBetween(startKey: string, endKey: string): string[] {
  const [start, end] = orderedCalendarRange(startKey, endKey);
  const current = calendarDateFromKey(start);
  const endTime = calendarDateFromKey(end).getTime();
  const keys: string[] = [];
  while (current.getTime() <= endTime) {
    keys.push(calendarDateKey(current));
    current.setDate(current.getDate() + 1);
  }
  return keys;
}

function calendarRangeLabel(startKey: string, endKey: string): string {
  const [start, end] = orderedCalendarRange(startKey, endKey);
  const startLabel = calendarDateLabel(calendarDateFromKey(start));
  const endLabel = calendarDateLabel(calendarDateFromKey(end));
  return start === end ? startLabel : `${startLabel} - ${endLabel}`;
}

function calendarItemCoversDate(item: CalendarItem, key: string): boolean {
  const [start, end] = orderedCalendarRange(item.date, item.endDate ?? item.date);
  return compareCalendarKeys(key, start) >= 0 && compareCalendarKeys(key, end) <= 0;
}

function normalizeCalendarTimeInput(value: string | undefined, fallback = calendarSettingsDefaults.defaultTime): string {
  const source = String(value || "").trim();
  const fallbackMatch = /^(\d{1,2}):(\d{2})/.exec(fallback);
  const fallbackValue = fallbackMatch ? `${fallbackMatch[1].padStart(2, "0")}:${fallbackMatch[2]}` : "09:00";
  if (!source) return fallbackValue;

  const normalized = source
    .replace(/\s+/g, "")
    .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xfee0));
  const japaneseMatch = /^(午前|午後)(\d{1,2})(?::(\d{1,2}))?/.exec(normalized);
  if (japaneseMatch) {
    let hour = Number(japaneseMatch[2]);
    const minute = Number(japaneseMatch[3] ?? 0);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fallbackValue;
    if (japaneseMatch[1] === "午後" && hour < 12) hour += 12;
    if (japaneseMatch[1] === "午前" && hour === 12) hour = 0;
    return `${String(Math.max(0, Math.min(23, hour))).padStart(2, "0")}:${String(Math.max(0, Math.min(59, minute))).padStart(2, "0")}`;
  }
  const plainMatch = /^(\d{1,2})(?::(\d{1,2}))?/.exec(normalized);
  if (!plainMatch) return fallbackValue;
  const hour = Number(plainMatch[1]);
  const minute = Number(plainMatch[2] ?? 0);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fallbackValue;
  return `${String(Math.max(0, Math.min(23, hour))).padStart(2, "0")}:${String(Math.max(0, Math.min(59, minute))).padStart(2, "0")}`;
}

function formatCalendarTime(time: string | undefined): string {
  const normalized = normalizeCalendarTimeInput(time);
  const [hourText, minute] = normalized.split(":");
  const hour = Number(hourText);
  const period = hour < 12 ? "午前" : "午後";
  const hour12 = hour % 12 || 12;
  return `${period}${hour12}:${minute}`;
}

function buildCalendarTimeOptions(stepMinutes: CalendarSettings["timeSlotMinutes"]): string[] {
  const step = stepMinutes === 30 || stepMinutes === 60 ? stepMinutes : 15;
  const options: string[] = [];
  for (let minutes = 0; minutes < 24 * 60; minutes += step) {
    options.push(`${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`);
  }
  return options;
}

function calendarRunAtIso(dateKey: string, time: string): string {
  const normalized = normalizeCalendarTimeInput(time);
  return new Date(`${dateKey}T${normalized}:00`).toISOString();
}

function createCalendarItemId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `calendar-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function parseCalendarSettings(raw: Record<string, unknown> | undefined): CalendarSettings {
  const value = raw ?? {};
  const defaultItemType = String(value.default_item_type ?? calendarSettingsDefaults.defaultItemType);
  const eventColor = String(value.event_color ?? calendarSettingsDefaults.eventColor);
  const taskColor = String(value.task_color ?? calendarSettingsDefaults.taskColor);
  const weekStart = String(value.week_start ?? calendarSettingsDefaults.weekStart);
  const maxItems = Number(value.max_items_per_day ?? calendarSettingsDefaults.maxItemsPerDay);
  const slotMinutes = Number(value.time_slot_minutes ?? calendarSettingsDefaults.timeSlotMinutes);
  return {
    agentCurrentChat: value.agent_current_chat === true,
    agentModel: String(value.agent_model ?? "").trim(),
    agentTaskDefault: value.agent_task_default === true,
    defaultTime: normalizeCalendarTimeInput(String(value.default_time ?? calendarSettingsDefaults.defaultTime)),
    defaultItemType: defaultItemType === "event" || defaultItemType === "reminder" ? defaultItemType : "task",
    dimWeekends: value.dim_weekends !== false,
    eventColor: eventColor === "blue" || eventColor === "slate" ? eventColor : "green",
    maxItemsPerDay: Number.isFinite(maxItems) ? Math.max(1, Math.min(6, Math.round(maxItems))) : calendarSettingsDefaults.maxItemsPerDay,
    quickAddEnabled: value.quick_add_enabled !== false,
    showOutsideDays: value.show_outside_days !== false,
    showTimePicker: value.show_time_picker !== false,
    taskColor: taskColor === "cyan" || taskColor === "slate" ? taskColor : "blue",
    timeSlotMinutes: slotMinutes === 30 || slotMinutes === 60 ? slotMinutes : 15,
    weekStart: weekStart === "monday" ? "monday" : "sunday",
  };
}

function calendarItemClassName(item: CalendarItem, settings: CalendarSettings): string {
  if (item.kind === "task") {
    if (settings.taskColor === "cyan") return "bg-cyan-500/85 text-cyan-950";
    if (settings.taskColor === "slate") return "bg-zinc-300/85 text-zinc-950";
    return "bg-blue-500/90 text-white";
  }
  if (item.kind === "event") {
    if (settings.eventColor === "blue") return "bg-blue-500/85 text-white";
    if (settings.eventColor === "slate") return "bg-zinc-300/85 text-zinc-950";
    return "bg-emerald-500/85 text-emerald-950";
  }
  return "bg-zinc-500/80 text-zinc-50";
}

function resolveCalendarAgentModel(settings: CalendarSettings, activeModelId: string, profiles: ModelProfile[]): string {
  if (settings.agentModel) return settings.agentModel;
  const isUsableProfile = (profile: ModelProfile): boolean => {
    const availability = profile.availability ?? {};
    const metadata = profile.metadata ?? {};
    const configurationSource = String(availability.configuration_source ?? metadata.configuration_source ?? "").toLowerCase();
    if (configurationSource === "no_key_gateway") return false;
    return Boolean(profile.local || availability.local === true || availability.configured === true || availability.status === "configured");
  };
  const activeProfile = profiles.find((profile) => profile.profile_id === activeModelId || profile.qualified_model_id === activeModelId);
  if (activeProfile && isUsableProfile(activeProfile)) return activeModelId;
  const configuredProfiles = profiles.filter((profile) => {
    const id = `${profile.profile_id} ${profile.qualified_model_id} ${profile.model_id}`.toLowerCase();
    return isUsableProfile(profile) && !id.includes("embedding");
  });
  const configuredProfile = configuredProfiles.find((profile) => {
    const id = `${profile.profile_id} ${profile.qualified_model_id} ${profile.model_id}`.toLowerCase();
    return id.includes("gemini") && id.includes("flash");
  }) ?? configuredProfiles[0];
  return configuredProfile?.profile_id || configuredProfile?.qualified_model_id || activeModelId || "default";
}

function CalendarComposerPanel({
  conversationId,
  modelId,
  modelProfiles,
  settings,
}: {
  conversationId: string | null;
  modelId: string;
  modelProfiles: ModelProfile[];
  settings: CalendarSettings;
}) {
  const today = new Date();
  const [visibleMonth, setVisibleMonth] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));
  const year = visibleMonth.getFullYear();
  const month = visibleMonth.getMonth();
  const monthStart = new Date(year, month, 1);
  const weekStartIndex = settings.weekStart === "monday" ? 1 : 0;
  const weekLabels = ["日", "月", "火", "水", "木", "金", "土"];
  const visibleWeekLabels = weekLabels.map((_, index) => weekLabels[(index + weekStartIndex) % 7]);
  const monthStartOffset = (monthStart.getDay() - weekStartIndex + 7) % 7;
  const [items, setItems] = useLocalStorage<CalendarItem[]>("defaultspack.calendar.items.v1", []);
  const [activeEditor, setActiveEditor] = useState<CalendarEditorState | null>(null);
  const [dragState, setDragState] = useState<CalendarDragState | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftKind, setDraftKind] = useState<CalendarItemKind>(settings.defaultItemType);
  const [draftTime, setDraftTime] = useState(formatCalendarTime(settings.defaultTime));
  const [draftAgentEnabled, setDraftAgentEnabled] = useState(settings.agentTaskDefault);
  const [draftAgentPrompt, setDraftAgentPrompt] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isTimeMenuOpen, setIsTimeMenuOpen] = useState(false);
  const [lastAgentResult, setLastAgentResult] = useState<string | null>(null);
  const calendarRef = useRef<HTMLElement | null>(null);
  const suppressNextCellOpenRef = useRef(false);

  useEffect(() => {
    setDraftKind(settings.defaultItemType);
  }, [settings.defaultItemType]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setActiveEditor(null);
        setDragState(null);
        setIsTimeMenuOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!calendarRef.current?.contains(target)) {
        setActiveEditor(null);
        setDragState(null);
        setIsTimeMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const calendarCells = Array.from({ length: 42 }, (_, index): CalendarCell => {
    const date = new Date(year, month, 1 + index - monthStartOffset);
    const isCurrentMonth = date.getMonth() === month;
    const isToday = date.getFullYear() === year && date.getMonth() === month && date.getDate() === today.getDate();
    const row = Math.floor(index / 7);
    const col = index % 7;
    return {
      col,
      date,
      isCurrentMonth,
      isToday,
      key: calendarDateKey(date),
      label: date.getDate() === 1 ? `${date.getMonth() + 1}月 1日` : String(date.getDate()),
      row,
    };
  });
  const itemsByDate = items.reduce<Record<string, CalendarItem[]>>((acc, item) => {
    if (!item.date || !item.title) return acc;
    for (const key of calendarKeysBetween(item.date, item.endDate ?? item.date)) {
      acc[key] = [...(acc[key] ?? []), item].sort((left, right) => {
        const timeOrder = String(left.time ?? "").localeCompare(String(right.time ?? ""));
        return timeOrder || left.title.localeCompare(right.title);
      });
    }
    return acc;
  }, {});
  const activeRangeKeys = activeEditor ? new Set(calendarKeysBetween(activeEditor.startKey, activeEditor.endKey)) : new Set<string>();
  const dragRangeKeys = dragState ? new Set(calendarKeysBetween(dragState.startKey, dragState.currentKey)) : new Set<string>();
  const activeItem = activeEditor?.itemId ? items.find((item) => item.id === activeEditor.itemId) ?? null : null;
  const timeOptions = buildCalendarTimeOptions(settings.timeSlotMinutes);
  const popoverStyle = activeEditor ? {
    left: `${(activeEditor.cell.col / 7) * 100}%`,
    top: `${(activeEditor.cell.row / 6) * 100}%`,
    transform: `${activeEditor.cell.col >= 5 ? "translateX(calc(-100% - 10px))" : "translateX(10px)"} ${activeEditor.cell.row >= 4 ? "translateY(calc(-100% - 10px))" : "translateY(36px)"}`,
  } : undefined;

  const dismissActiveEditorForSelection = (suppressCellMouseUp = false) => {
    if (!activeEditor) return false;
    suppressNextCellOpenRef.current = suppressCellMouseUp;
    setActiveEditor(null);
    setDragState(null);
    setIsTimeMenuOpen(false);
    return true;
  };

  const moveVisibleMonth = (offset: number) => {
    suppressNextCellOpenRef.current = false;
    setActiveEditor(null);
    setDragState(null);
    setIsTimeMenuOpen(false);
    setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));
  };

  const returnToToday = () => {
    suppressNextCellOpenRef.current = false;
    setActiveEditor(null);
    setDragState(null);
    setIsTimeMenuOpen(false);
    setVisibleMonth(new Date(today.getFullYear(), today.getMonth(), 1));
  };

  const resetDraftForCreate = (kind = settings.defaultItemType) => {
    setDraftTitle("");
    setDraftKind(kind);
    setDraftTime(formatCalendarTime(settings.defaultTime));
    setDraftAgentEnabled(settings.agentTaskDefault && kind === "task");
    setDraftAgentPrompt("");
    setDraftError(null);
    setLastAgentResult(null);
    setIsTimeMenuOpen(false);
  };

  const openCreateEditor = (cell: CalendarCell, startKey = cell.key, endKey = cell.key) => {
    if (!settings.quickAddEnabled) return;
    resetDraftForCreate(settings.defaultItemType);
    setActiveEditor({ mode: "create", cell, startKey, endKey });
  };

  const openEditEditor = (item: CalendarItem, cell: CalendarCell) => {
    setActiveEditor({
      mode: "edit",
      itemId: item.id,
      cell,
      startKey: item.date,
      endKey: item.endDate ?? item.date,
    });
    setDraftTitle(item.title);
    setDraftKind(item.kind);
    setDraftTime(formatCalendarTime(item.time ?? settings.defaultTime));
    setDraftAgentEnabled(Boolean(item.scheduleId));
    setDraftAgentPrompt(item.agentPrompt ?? item.title);
    setDraftError(null);
    setLastAgentResult(item.lastRunStatus ? `Agent last run: ${item.lastRunStatus}` : null);
    setIsTimeMenuOpen(false);
  };

  const schedulePayloadForItem = (itemId: string, title: string, startKey: string, endKey: string, time: string, agentPrompt: string) => ({
    name: `Calendar: ${title}`,
    description: `Created from Rumi calendar for ${calendarRangeLabel(startKey, endKey)}.`,
    schedule_type: "once",
    schedule_config: { run_at: calendarRunAtIso(startKey, time) },
    task: {
      message: agentPrompt || title,
      model: resolveCalendarAgentModel(settings, modelId, modelProfiles),
      conversation_id: settings.agentCurrentChat ? conversationId || null : null,
      metadata: {
        source: "calendar",
        calendar_item_id: itemId,
        calendar_start_date: startKey,
        calendar_end_date: endKey,
        calendar_time: normalizeCalendarTimeInput(time),
      },
    },
  });

  const extractScheduleRecord = (response: Record<string, unknown>): Record<string, unknown> => {
    const data = response.data;
    return isRecord(data) ? data : response;
  };

  const persistAgentSchedule = async (
    existing: CalendarItem | null,
    itemId: string,
    title: string,
    startKey: string,
    endKey: string,
    time: string,
    agentPrompt: string,
  ): Promise<{ scheduleId?: string; scheduleStatus?: string }> => {
    const payload = schedulePayloadForItem(itemId, title, startKey, endKey, time, agentPrompt);
    if (existing?.scheduleId) {
      const updated = extractScheduleRecord(await api.updateSchedule(existing.scheduleId, payload));
      return {
        scheduleId: String(updated.id ?? existing.scheduleId),
        scheduleStatus: String(updated.status ?? existing.scheduleStatus ?? "active"),
      };
    }
    const created = extractScheduleRecord(await api.createSchedule(payload));
    const scheduleId = created.id ? String(created.id) : undefined;
    return {
      scheduleId,
      scheduleStatus: String(created.status ?? "active"),
    };
  };

  const submitDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activeEditor) return;
    setIsSavingDraft(true);
    setDraftError(null);
    setLastAgentResult(null);
    const [startKey, endKey] = orderedCalendarRange(activeEditor.startKey, activeEditor.endKey);
    const title = draftTitle.trim() || (draftKind === "task" ? "New task" : draftKind === "event" ? "New event" : "Reminder");
    const normalizedTime = normalizeCalendarTimeInput(draftTime, settings.defaultTime);
    const existing = activeEditor.itemId ? items.find((item) => item.id === activeEditor.itemId) ?? null : null;
    const itemId = existing?.id ?? createCalendarItemId();
    const agentPrompt = draftAgentPrompt.trim() || title;
    try {
      let scheduleId = existing?.scheduleId;
      let scheduleStatus = existing?.scheduleStatus;
      if (draftKind === "task" && draftAgentEnabled) {
        const schedule = await persistAgentSchedule(existing, itemId, title, startKey, endKey, normalizedTime, agentPrompt);
        scheduleId = schedule.scheduleId;
        scheduleStatus = schedule.scheduleStatus;
      } else if (existing?.scheduleId) {
        await api.deleteSchedule(existing.scheduleId).catch(() => undefined);
        scheduleId = undefined;
        scheduleStatus = undefined;
      }
      const nextItem: CalendarItem = {
        id: itemId,
        date: startKey,
        endDate: endKey === startKey ? undefined : endKey,
        kind: draftKind,
        title,
        time: normalizedTime,
        agentPrompt: draftKind === "task" && draftAgentEnabled ? agentPrompt : undefined,
        scheduleId,
        scheduleStatus,
        lastRunStatus: existing?.lastRunStatus,
      };
      setItems((current) => activeEditor.mode === "edit"
        ? current.map((item) => item.id === itemId ? nextItem : item)
        : [...current, nextItem]);
      setActiveEditor(null);
      setDraftTitle("");
      setIsTimeMenuOpen(false);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Agent task schedule failed.");
    } finally {
      setIsSavingDraft(false);
    }
  };

  const deleteActiveItem = async () => {
    if (!activeItem) return;
    setIsSavingDraft(true);
    setDraftError(null);
    try {
      if (activeItem.scheduleId) await api.deleteSchedule(activeItem.scheduleId).catch(() => undefined);
      setItems((current) => current.filter((item) => item.id !== activeItem.id));
      setActiveEditor(null);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Delete failed.");
    } finally {
      setIsSavingDraft(false);
    }
  };

  const runActiveAgentNow = async () => {
    if (!activeItem?.scheduleId) return;
    setIsSavingDraft(true);
    setDraftError(null);
    try {
      const response = extractScheduleRecord(await api.triggerSchedule(activeItem.scheduleId));
      const status = String(response.status ?? "triggered");
      setItems((current) => current.map((item) => item.id === activeItem.id ? { ...item, lastRunStatus: status } : item));
      setLastAgentResult(`Agent run: ${status}`);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Agent trigger failed.");
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handleCellMouseDown = (event: ReactMouseEvent<HTMLDivElement>, cell: CalendarCell) => {
    if (event.button !== 0 || cell.isCurrentMonth === false && !settings.showOutsideDays) return;
    event.preventDefault();
    if (dismissActiveEditorForSelection(true)) return;
    setDragState({ startKey: cell.key, currentKey: cell.key, startedAt: Date.now() });
  };

  const handleCellMouseEnter = (cell: CalendarCell) => {
    setDragState((current) => current ? { ...current, currentKey: cell.key } : current);
  };

  const handleCellMouseUp = (event: ReactMouseEvent<HTMLDivElement>, cell: CalendarCell) => {
    if (event.button !== 0) return;
    event.preventDefault();
    if (suppressNextCellOpenRef.current) {
      suppressNextCellOpenRef.current = false;
      return;
    }
    const currentDrag = dragState;
    setDragState(null);
    if (!currentDrag) {
      openCreateEditor(cell);
      return;
    }
    const holdMs = Date.now() - currentDrag.startedAt;
    const endKey = currentDrag.currentKey || cell.key;
    openCreateEditor(cell, currentDrag.startKey, endKey);
    if (holdMs > 360 || currentDrag.startKey !== endKey) {
      setDraftTitle("");
    }
  };

  return (
    <section
      ref={calendarRef}
      aria-label="Calendar month"
      className="relative h-full min-h-0 w-full overflow-hidden rounded-[26px] border border-zinc-800 bg-[#101112] shadow-[0_24px_80px_rgba(0,0,0,0.36)]"
    >
      <div className="pointer-events-none absolute left-4 top-3 rumi-layer-local-popover flex items-center gap-2">
        <button
          type="button"
          aria-label="前の月"
          title="前の月"
          className="pointer-events-auto flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-700/80 bg-zinc-950/82 text-lg leading-none text-zinc-300 shadow-lg backdrop-blur transition-colors hover:border-zinc-500 hover:bg-zinc-900 hover:text-zinc-50"
          onClick={() => moveVisibleMonth(-1)}
        >
          ‹
        </button>
        <button
          type="button"
          aria-label="今日"
          title="今日"
          className="pointer-events-auto rounded-lg border border-zinc-700/80 bg-zinc-950/82 px-3 py-1.5 text-[12px] font-semibold text-zinc-200 shadow-lg backdrop-blur transition-colors hover:border-zinc-500 hover:bg-zinc-900 hover:text-zinc-50"
          onClick={returnToToday}
        >
          {year}年{month + 1}月
        </button>
        <button
          type="button"
          aria-label="次の月"
          title="次の月"
          className="pointer-events-auto flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-700/80 bg-zinc-950/82 text-lg leading-none text-zinc-300 shadow-lg backdrop-blur transition-colors hover:border-zinc-500 hover:bg-zinc-900 hover:text-zinc-50"
          onClick={() => moveVisibleMonth(1)}
        >
          ›
        </button>
      </div>
      <div className="grid h-full min-h-[620px] grid-cols-7 grid-rows-6 overflow-hidden">
        {calendarCells.map((cell, index) => {
          const visibleItems = (itemsByDate[cell.key] ?? []).slice(0, settings.maxItemsPerDay);
          const hiddenCount = Math.max(0, (itemsByDate[cell.key] ?? []).length - visibleItems.length);
          const isOutsideHidden = !cell.isCurrentMonth && !settings.showOutsideDays;
          const isWeekend = (cell.date.getDay() === 0 || cell.date.getDay() === 6) && settings.dimWeekends;
          const isSelected = activeRangeKeys.has(cell.key);
          const isDragSelected = dragRangeKeys.has(cell.key);
          return (
            <div
              key={`${cell.date.toISOString()}-${index}`}
              role="button"
              tabIndex={isOutsideHidden ? -1 : 0}
              data-testid={`calendar-day-${cell.key}`}
              aria-label={`${calendarDateLabel(cell.date)} の予定を追加`}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  if (dismissActiveEditorForSelection()) return;
                  openCreateEditor(cell);
                }
              }}
              onMouseDown={(event) => handleCellMouseDown(event, cell)}
              onMouseEnter={() => handleCellMouseEnter(cell)}
              onMouseUp={(event) => handleCellMouseUp(event, cell)}
              className={cn(
                "relative flex min-h-0 flex-col items-stretch border-b border-r border-zinc-800/90 px-2 py-2 text-left transition-colors hover:bg-zinc-900/70 focus:outline-none focus-visible:bg-zinc-900 focus-visible:ring-2 focus-visible:ring-blue-400/70",
                !cell.isCurrentMonth && "text-zinc-600",
                isOutsideHidden && "cursor-default text-transparent hover:bg-transparent",
                isWeekend && cell.isCurrentMonth && "bg-black/10",
                isSelected && "bg-blue-950/20 ring-2 ring-inset ring-blue-400/70",
                isDragSelected && "bg-blue-950/35",
              )}
            >
              {cell.row === 0 && (
                <div className="mb-1.5 text-center text-[12px] font-semibold text-zinc-500">
                  {visibleWeekLabels[cell.col]}
                </div>
              )}
              <div className="flex justify-center">
                <span
                  className={cn(
                    "inline-flex min-h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-[13px] font-semibold leading-none text-zinc-300",
                    !cell.isCurrentMonth && "text-zinc-500",
                    cell.isToday && "bg-zinc-100 text-zinc-950 shadow-[0_0_0_1px_rgba(255,255,255,0.18)]",
                  )}
                >
                  {isOutsideHidden ? "" : cell.label}
                </span>
              </div>
              <div className="mt-2 flex min-h-0 flex-1 flex-col gap-1 overflow-hidden">
                {visibleItems.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    data-testid={`calendar-item-${item.id}`}
                    className={cn("truncate rounded-[7px] px-2 py-0.5 text-left text-[10.5px] font-medium leading-5 shadow-sm transition-opacity hover:opacity-90", calendarItemClassName(item, settings))}
                    title={item.title}
                    onPointerDown={(event) => event.stopPropagation()}
                    onPointerUp={(event) => event.stopPropagation()}
                    onMouseDown={(event) => event.stopPropagation()}
                    onMouseUp={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (dismissActiveEditorForSelection()) return;
                      openEditEditor(item, cell);
                    }}
                  >
                    {item.time && <span className="mr-1 opacity-75">{formatCalendarTime(item.time)}</span>}
                    {item.title}
                  </button>
                ))}
                {hiddenCount > 0 && (
                  <div className="text-[10px] font-medium text-zinc-500">ほか{hiddenCount}件</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {activeEditor && settings.quickAddEnabled && (
        <form
          key={`${activeEditor.mode}-${activeEditor.itemId ?? "new"}-${activeEditor.startKey}-${activeEditor.endKey}`}
          role="dialog"
          aria-label={`${calendarRangeLabel(activeEditor.startKey, activeEditor.endKey)}に追加`}
          className="rumi-calendar-popover absolute rumi-layer-global-overlay w-[min(320px,calc(100%-24px))] rounded-2xl border border-zinc-700 bg-zinc-950/95 p-3 text-left shadow-[0_24px_70px_rgba(0,0,0,0.65)] backdrop-blur"
          style={popoverStyle}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onSubmit={submitDraft}
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-600">{activeEditor.mode === "edit" ? "項目を編集" : "新規項目"}</p>
              <p className="truncate text-sm font-semibold text-zinc-100">{calendarRangeLabel(activeEditor.startKey, activeEditor.endKey)}</p>
            </div>
            <button
              type="button"
              onClick={() => setActiveEditor(null)}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
              aria-label="カレンダーのクイック追加を閉じる"
            >
              ×
            </button>
          </div>
          <input
            autoFocus
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            placeholder="何を追加しますか？"
            className="h-10 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-blue-400/70"
          />
          <div className="mt-3 grid grid-cols-3 gap-1.5">
            {(["task", "event", "reminder"] as CalendarItemKind[]).map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => {
                  setDraftKind(kind);
                  setDraftAgentEnabled((current) => kind === "task" ? current || settings.agentTaskDefault : false);
                }}
                className={cn(
                  "rounded-lg border px-2 py-1.5 text-xs font-medium transition-colors",
                  draftKind === kind
                    ? "border-zinc-200 bg-zinc-100 text-zinc-950"
                    : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
                )}
              >
                {kind === "task" ? "タスク" : kind === "event" ? "予定" : "リマインダー"}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-end gap-2">
            <label className="relative flex-1">
              <span className="mb-1 block text-[10px] uppercase tracking-[0.18em] text-zinc-600">時刻</span>
              <input
                type="text"
                value={draftTime}
                aria-label="カレンダー項目の時刻"
                onClick={() => setIsTimeMenuOpen(settings.showTimePicker)}
                onFocus={() => setIsTimeMenuOpen(settings.showTimePicker)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.stopPropagation();
                    setIsTimeMenuOpen(false);
                  }
                  if (event.key === "Enter") {
                    setIsTimeMenuOpen(false);
                  }
                }}
                onBlur={() => window.setTimeout(() => setIsTimeMenuOpen(false), 120)}
                onChange={(event) => {
                  setDraftTime(event.target.value);
                  setIsTimeMenuOpen(settings.showTimePicker);
                }}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-200 outline-none focus:border-zinc-600"
              />
              {isTimeMenuOpen && settings.showTimePicker && (
                <div
                  role="listbox"
                  aria-label="カレンダー時刻候補"
                  className="absolute bottom-11 left-0 rumi-layer-global-overlay max-h-[300px] w-[210px] overflow-y-auto rounded-[22px] border border-zinc-700 bg-zinc-800 p-1.5 shadow-[0_18px_60px_rgba(0,0,0,0.55)]"
                >
                  {timeOptions.map((option) => (
                    <button
                      key={option}
                      type="button"
                      role="option"
                      aria-selected={normalizeCalendarTimeInput(draftTime, settings.defaultTime) === option}
                      className={cn(
                        "block w-full rounded-xl px-3 py-2 text-left text-[15px] leading-6 text-zinc-100 hover:bg-zinc-700",
                        normalizeCalendarTimeInput(draftTime, settings.defaultTime) === option && "bg-zinc-700",
                      )}
                      onClick={() => {
                        setDraftTime(formatCalendarTime(option));
                        setIsTimeMenuOpen(false);
                      }}
                    >
                      {formatCalendarTime(option)}
                    </button>
                  ))}
                </div>
              )}
            </label>
            <button
              type="submit"
              disabled={isSavingDraft}
              className="h-9 rounded-lg bg-zinc-100 px-4 text-xs font-semibold text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {activeEditor.mode === "edit" ? "保存" : "追加"}
            </button>
          </div>
          {draftKind === "task" && (
            <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-2.5">
              <label className="flex items-center justify-between gap-3 text-xs font-medium text-zinc-200">
                <span>Agentタスク</span>
                <input
                  type="checkbox"
                  checked={draftAgentEnabled}
                  onChange={(event) => setDraftAgentEnabled(event.target.checked)}
                  className="h-4 w-4 accent-blue-500"
                />
              </label>
              {draftAgentEnabled && (
                <textarea
                  value={draftAgentPrompt}
                  onChange={(event) => setDraftAgentPrompt(event.target.value)}
                  placeholder="エージェントに実行させる内容。空ならタイトルを使います。"
                  className="mt-2 h-16 w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-blue-400/70"
                />
              )}
            </div>
          )}
          {(draftError || lastAgentResult || activeItem?.scheduleId) && (
            <div className={cn(
              "mt-3 rounded-lg border px-2.5 py-2 text-xs",
              draftError ? "border-red-500/40 bg-red-500/10 text-red-100" : "border-blue-500/30 bg-blue-500/10 text-blue-100",
            )}>
              {draftError ?? lastAgentResult ?? `Agentスケジュール: ${activeItem?.scheduleStatus ?? "有効"}`}
            </div>
          )}
          {activeEditor.mode === "edit" && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => void deleteActiveItem()}
                disabled={isSavingDraft}
                className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/10 disabled:opacity-50"
              >
                削除
              </button>
              {activeItem?.scheduleId && (
                <button
                  type="button"
                  onClick={() => void runActiveAgentNow()}
                  disabled={isSavingDraft}
                  className="rounded-lg border border-blue-500/30 px-3 py-1.5 text-xs font-medium text-blue-100 hover:bg-blue-500/10 disabled:opacity-50"
                >
                  今すぐ実行
                </button>
              )}
            </div>
          )}
          <div className="sr-only">
            <input
              type="time"
              value={normalizeCalendarTimeInput(draftTime, settings.defaultTime)}
              readOnly
            />
          </div>
        </form>
      )}
    </section>
  );
}

function useLocalStorage<T>(key: string, defaultValue: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? JSON.parse(saved) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue];
}

function clampNumber(value: unknown, min: number, max: number, fallback: number): number {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, numeric));
}

export function shouldAutoCompactHistory(width: number): boolean {
  return width < 760;
}

function writeJsonLocalStorage<T>(key: string, value: T) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}

function cleanOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function workspaceContextFromMetadata(metadata: Record<string, unknown> | null | undefined): PendingNewTaskContext {
  return {
    groupId: cleanOptionalString(metadata?.group_id ?? metadata?.groupId) ?? undefined,
    workspaceId: cleanOptionalString(metadata?.workspace_id ?? metadata?.workspaceId),
    workspaceLabel: cleanOptionalString(metadata?.workspace_label ?? metadata?.workspaceLabel),
    workspaceRoot: cleanOptionalString(metadata?.workspace_root ?? metadata?.workspaceRoot ?? metadata?.rootPath),
    rumiDataPath: cleanOptionalString(metadata?.rumi_data_path ?? metadata?.rumiDataPath ?? metadata?.rumi_dp_path),
  };
}

function workspaceContextFromConversation(conversation: Conversation | null | undefined): PendingNewTaskContext {
  const metadataContext = workspaceContextFromMetadata(conversation?.metadata);
  return {
    ...metadataContext,
    groupId: cleanOptionalString(conversation?.group_id) ?? metadataContext.groupId,
  };
}

function workspaceContextFromHistoryOptions(options?: HistoryBoardNewTaskOptions): PendingNewTaskContext | null {
  if (!options) return null;
  const context: PendingNewTaskContext = {
    groupId: cleanOptionalString(options.groupId) ?? undefined,
    workspaceId: cleanOptionalString(options.workspaceId),
    workspaceLabel: cleanOptionalString(options.workspaceLabel),
    workspaceRoot: cleanOptionalString(options.workspaceRoot),
    rumiDataPath: cleanOptionalString(options.rumiDataPath),
  };
  return context.groupId || context.workspaceId || context.workspaceRoot || context.rumiDataPath ? context : null;
}

function formatBoardDate(updatedAt: number): string {
  const diffHours = (Date.now() - updatedAt) / 3_600_000;
  if (diffHours < 24) return "今日";
  if (diffHours < 48) return "昨日";
  if (diffHours < 24 * 7) return "過去7日";
  return formatRelativeTime(updatedAt);
}

function externalConversationSection(conversation: Conversation): { id: string; title: string } | null {
  const metadata = conversation.metadata ?? {};
  const provider = typeof metadata.external_provider === "string" ? metadata.external_provider.trim().toLowerCase() : "";
  if (!provider) return null;
  if (provider === "line") {
    return { id: "integration-line", title: "LINE" };
  }
  return {
    id: `integration-${provider}`,
    title: provider.slice(0, 1).toUpperCase() + provider.slice(1),
  };
}

function toChatItem(conversation: Conversation): ChatItem {
  const section = externalConversationSection(conversation);
  const metadata = conversation.metadata ?? {};
  return {
    id: conversation.id,
    title: conversation.title,
    date: formatBoardDate(conversation.updated_at),
    type: "chat",
    parentId: conversation.parent_conversation_id ?? null,
    conversationKind: conversation.conversation_kind ?? "chat",
    sectionId: section?.id ?? null,
    sectionTitle: section?.title ?? null,
    tags: conversation.tags ?? [],
    isStarred: conversation.is_starred,
    isPinned: Boolean(conversation.is_pinned),
    companyId: typeof metadata.company_id === "string" ? metadata.company_id : null,
    workspaceId: typeof metadata.workspace_id === "string" ? metadata.workspace_id : null,
    metadata,
  };
}

function buildChatItems(conversations: Conversation[]): ChatItem[] {
  const byId = new Map(conversations.map((conversation) => [conversation.id, conversation]));
  const childIds = new Set<string>();

  for (const conversation of conversations) {
    if (conversation.parent_conversation_id) {
      childIds.add(conversation.id);
    }
    for (const childId of conversation.child_conversation_ids ?? []) {
      if (byId.has(childId)) childIds.add(childId);
    }
  }

  const build = (conversation: Conversation): ChatItem => {
    const linkedChildren = [
      ...new Set([
        ...(conversation.child_conversation_ids ?? []),
        ...conversations
          .filter((candidate) => candidate.parent_conversation_id === conversation.id)
          .map((candidate) => candidate.id),
      ]),
    ]
      .map((childId) => byId.get(childId))
      .filter((child): child is Conversation => Boolean(child))
      .sort((a, b) => b.updated_at - a.updated_at)
      .map(build);
    return { ...toChatItem(conversation), children: linkedChildren };
  };

  return conversations
    .filter((conversation) => !childIds.has(conversation.id))
    .map(build);
}

function normalizeBlocks(message: ChatMessage): ChatContentBlock[] {
  if (typeof message.content === "string") {
    return [{ type: "text", text: message.content }];
  }
  return message.content;
}

function toUiMessage(message: ChatMessage, profile?: ModelProfile | null): ChatUiMessage {
  const isUser = message.role === "user";
  const metadata = message.metadata ?? {};
  const thinking = metadata.thinking as Record<string, unknown> | undefined;
  const timing = metadata.timing as Record<string, unknown> | undefined;
  const pendingApproval = metadata.pending_approval;
  const attachedToolCount = Number(metadata.attached_tool_count ?? 0);
  const thinkingDuration = String(timing?.thinking_duration_label ?? "")
    || boundedDurationLabel(timing?.thinking_started_at, timing?.completed_at);
  return {
    id: message.id,
    conversationId: message.conversation_id,
    role: isUser ? "user" : "agent",
    content: normalizeBlocks(message),
    rawText: messageToText(message),
    widget: message.widget,
    events: message.events ?? [],
    toolLogs: message.tool_logs ?? [],
    metadata: isUser
      ? undefined
      : {
          executionTime: formatRelativeTime(message.created_at),
          modelName: profile?.display_name ?? String(message.model ?? ""),
          thinkingLabel: String(thinking?.state ?? ""),
          thinkingDuration,
          thinkingTranscript: String(thinking?.transcript ?? ""),
          attachedToolCount,
          pendingApproval: pendingApproval && typeof pendingApproval === "object" && !Array.isArray(pendingApproval)
            ? pendingApproval as Record<string, unknown>
            : undefined,
        },
  };
}

function optimisticUserMessage(conversationId: string, text: string): ChatMessage {
  return {
    id: `optimistic-${Date.now()}`,
    role: "user",
    content: [{ type: "text", text }],
    raw_text: text,
    created_at: Date.now(),
    conversation_id: conversationId,
    parent_id: null,
    children_ids: [],
    sequence_number: 0,
    finish_reason: null,
    usage: null,
    widget: null,
  };
}

function optimisticAssistantMessage(conversationId: string, model: string): ChatMessage {
  return {
    id: `optimistic-assistant-${Date.now()}`,
    role: "assistant",
    content: [{ type: "text", text: "" }],
    raw_text: "",
    created_at: Date.now(),
    conversation_id: conversationId,
    parent_id: null,
    children_ids: [],
    sequence_number: 0,
    finish_reason: null,
    usage: null,
    widget: null,
    metadata: { model, thinking: { state: "streaming" }, attached_tool_count: 0 },
    events: [],
    tool_logs: [],
    model,
  };
}

function mergeChatActivityEvents(base: ChatActivityEvent[] | null | undefined, extra: ChatActivityEvent[] | null | undefined): ChatActivityEvent[] {
  let merged = [...(base ?? [])];
  for (const event of extra ?? []) {
    merged = upsertStreamActivityEvent(merged, event);
  }
  return merged;
}

function mergeStreamingFinalMessage(existing: ChatMessage | undefined, incoming: ChatMessage): ChatMessage {
  return {
    ...incoming,
    events: mergeChatActivityEvents(incoming.events, existing?.events),
    tool_logs: incoming.tool_logs ?? existing?.tool_logs ?? null,
  };
}

function previewFromAction(action: SidebarAction, title: string, data: unknown): ToolPreviewItem {
  const content = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return {
    id: `sidebar-${action.id}-${Date.now()}`,
    toolStepId: action.id,
    timestamp: Date.now(),
    data: {
      type: "file",
      filename: `${title}.json`,
      size: "sidebar action",
      content,
    },
  };
}

function previewLabel(preview: ToolPreviewItem | undefined): string {
  if (!preview) return "memo.md";
  const data = preview.data;
  if (data.type === "web") return data.title || data.url || "Web preview";
  if (data.type === "code") return data.filename || "Code preview";
  if (data.type === "file") return data.filename || "File preview";
  return data.alt || "Image preview";
}

function CanvasPeek({
  previews,
  memo,
  activePreviewId,
  onOpen,
}: {
  previews: ToolPreviewItem[];
  memo: string;
  activePreviewId: string | null;
  onOpen: () => void;
}) {
  const items = buildToolPreviewDisplayItems(previews, memo, activePreviewId);
  if (items.length === 0) return null;

  const latest = items[0];
  const count = items.length;
  const isMemo = latest.id === "__memo__";
  const subLabel = isMemo ? "Canvas · memo" : "Canvas · tool activity";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="mx-auto mb-2 flex w-[min(620px,calc(100%_-_40px))] items-center justify-between gap-3 rounded-xl border border-zinc-800/90 bg-zinc-950/85 px-3 py-2 text-left shadow-[0_14px_38px_rgba(0,0,0,0.24)] transition-colors hover:border-zinc-700 hover:bg-zinc-900/90"
      title="Canvas を開く"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="h-8 w-8 flex-shrink-0 rounded-lg border border-zinc-800 bg-zinc-900/80" />
        <span className="min-w-0">
          <span className="block truncate text-[12px] font-medium text-zinc-300">
            {previewLabel(latest)}
          </span>
          <span className="block truncate text-[10px] text-zinc-600">{subLabel}</span>
        </span>
      </span>
      <span className="flex-shrink-0 rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-500">
        {count}
      </span>
    </button>
  );
}

function approvalPayloadPreview(payload: Record<string, unknown>): string {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function normalizedPreviewUrl(value: string): string {
  try {
    const url = new URL(value);
    url.hash = "";
    return url.href;
  } catch {
    return value.trim();
  }
}

function canvasPreviewIdentity(preview: ToolPreviewItem): string {
  const data = preview.data;
  if (data.type === "web") return `web:${normalizedPreviewUrl(data.url)}`;
  if (data.type === "image") return `image:${data.path || data.url || data.alt}`;
  if (data.type === "file") return `file:${data.path || data.url || `${data.filename}:${data.content ?? ""}`}`;
  return `code:${data.filename}:${data.diff ?? data.content ?? ""}`;
}

function runtimeApprovalRuntimeContent(approval: RuntimeApproval, token?: string): string {
  const payload = approvalPayloadPreview({
    ...approval.payload,
    ...(token ? { approval_token: token } : {}),
  });
  return [
    "The user approved the pending server-side tool operation.",
    "Continue by calling the exact pending tool once with the approved arguments below.",
    "Do not ask the user for the same approval again unless the tool returns a new approval_request_id.",
    `Tool: ${approval.toolName}`,
    `Operation: ${approval.operation}`,
    `Approval request id: ${approval.requestId}`,
    "Approved arguments JSON:",
    payload,
  ].join("\n");
}

function browserApprovalRuntimeContent(approval: BrowserApproval): string {
  const payload = approvalPayloadPreview({
    ...approval.payload,
    approval_token: approval.token,
  });
  return [
    "The user approved the pending browser/computer action.",
    "Continue by calling the exact pending tool once with the approved arguments below.",
    "Do not ask the user for the same approval again unless the tool returns a new approval request.",
    `Tool: ${approval.toolName}`,
    `Action: ${approval.action}`,
    "Approved arguments JSON:",
    payload,
  ].join("\n");
}

function staleRuntimeApprovalTitle(approval: StaleRuntimeApproval): string {
  const label = approval.operation || approval.toolName || "tool";
  return `${label} は再実行が必要です`;
}

function hasOperationsProfile(catalog: UICatalog | null): boolean {
  const profiles = catalog?.agent_service?.profiles ?? [];
  return profiles.some((profile) => String(profile.profile_id ?? profile.id ?? "") === "defaultspack.operations_company");
}

function isOperationsConversation(conversation: Conversation | null): boolean {
  if (!conversation) return false;
  return (
    conversation.conversation_kind === "operations_company"
    || conversation.metadata?.profile_id === "defaultspack.operations_company"
    || conversation.tags?.includes("operations-company")
  );
}

function settingList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function settingNumber(value: unknown, fallback: number): number {
  const numeric = Number(value ?? fallback);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function isAbortError(errorValue: unknown): boolean {
  return Boolean(
    errorValue
    && typeof errorValue === "object"
    && "name" in errorValue
    && String((errorValue as { name?: unknown }).name) === "AbortError",
  );
}

function isCancelledStreamError(errorValue: unknown): boolean {
  if (isAbortError(errorValue)) return true;
  const message = errorValue instanceof Error ? errorValue.message : String(errorValue ?? "");
  return message.trim().toLowerCase() === "cancelled";
}

function isActivityStreamEvent(event: ChatStreamEvent): event is ChatToolStreamEvent {
  return (
    event.type === "status"
    || event.type === "tool_call"
    || event.type === "tool_call_started"
    || event.type === "tool_call_delta"
    || event.type === "tool_call_completed"
    || event.type === "tool_result"
    || event.type === "browser_state_invalidated"
    || event.type === "browser_state_snapshot"
    || event.type === "browser_dom_snapshot"
    || event.type === "browser_screenshot"
    || event.type === "approval_requested"
    || event.type === "ai_retry_scheduled"
    || event.type === "task_failed"
  );
}

function isConversationSteerItem(value: unknown): value is ConversationSteerItem {
  return Boolean(
    value
    && typeof value === "object"
    && "id" in value
    && "prompt" in value
  );
}

function activeComposerSteerItems(items: ConversationSteerItem[], isRunning: boolean): ConversationSteerItem[] {
  return items
    .filter((item) => item.visible !== false && String(item.prompt ?? "").trim())
    .filter((item) => {
      const status = String(item.status || "").toLowerCase();
      return status === "queued" || status === "sending" || (isRunning && status === "injected");
    })
    .slice(-3)
    .reverse();
}

function profileKey(profile: ModelProfile | null | undefined, fallback: string): string {
  return profile?.profile_id || profile?.qualified_model_id || fallback;
}

function getNewConversationPlaceholder(): string {
  return "指示を入力するか、/ でツール・コマンドを選択します...";
}

function getNewConversationGreeting(): string {
  return "Defaults Console";
}

function findProfile(profiles: ModelProfile[], modelId: string): ModelProfile | null {
  return profiles.find((profile) => (
    profile.profile_id === modelId
    || profile.qualified_model_id === modelId
    || `${profile.provider_id}/${profile.model_id}` === modelId
  )) ?? null;
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

function isConfiguredProfile(profile: ModelProfile): boolean {
  const availability = profile.availability ?? {};
  return Boolean(
    availability.configured
    || availability.active
    || availability.status === "configured"
    || availability.status === "active",
  );
}

export function profileNeedsApiKey(profile: ModelProfile | null | undefined): boolean {
  if (!profile) return false;
  const providerId = String(profile.provider_id ?? "").trim();
  if (!providerId || providerId === "rumi" || LOCAL_MODEL_PROVIDER_IDS.has(providerId)) return false;
  const availability = profile.availability ?? {};
  if (profile.local || availability.local || availability.offline || isConfiguredProfile(profile)) return false;
  return API_KEY_PROVIDER_IDS.has(providerId);
}

function isUserFacingModelProfile(profile: ModelProfile, preferredModel: string): boolean {
  const providerId = String(profile.provider_id ?? "").trim();
  const modelId = String(profile.model_id ?? "").trim();
  const profileId = profile.profile_id || profile.qualified_model_id || `${providerId}/${modelId}`;

  if (profileId === preferredModel) return true;
  if (!profileIsChatSelectable(profile)) return false;
  if (providerId === "rumi") return false;
  if (providerId === "stub") return modelId === "default";
  if (profile.local || profile.availability?.local || profile.availability?.offline || LOCAL_MODEL_PROVIDER_IDS.has(providerId)) return true;
  return isConfiguredProfile(profile);
}

function modelProfileSortKey(profile: ModelProfile): [number, number, string] {
  const modelId = String(profile.model_id ?? "").trim();
  const providerId = String(profile.provider_id ?? "").trim();
  const isDefault = profile.profile_id === "stub/default";
  const isLocal = Boolean(
    profile.local
    || profile.availability?.local
    || profile.availability?.offline
    || LOCAL_MODEL_PROVIDER_IDS.has(providerId),
  );
  const isConfigured = isConfiguredProfile(profile);
  const providerOrder = isDefault ? 0 : isLocal ? 1 : isConfigured ? 2 : 9;
  const modelOrder = modelId === "default" ? 0 : 20;
  return [
    providerOrder,
    modelOrder,
    profile.display_name || profile.profile_id,
  ];
}

export function userFacingModelProfiles(profiles: ModelProfile[], preferredModel: string): ModelProfile[] {
  const deduped = new Map<string, ModelProfile>();
  for (const profile of profiles) {
    if (!isUserFacingModelProfile(profile, preferredModel)) continue;
    const key = profile.profile_id || profile.qualified_model_id || `${profile.provider_id}/${profile.model_id}`;
    if (key) deduped.set(key, profile);
  }
  return [...deduped.values()].sort((a, b) => {
    const aKey = modelProfileSortKey(a);
    const bKey = modelProfileSortKey(b);
    return aKey[0] - bKey[0] || aKey[1] - bKey[1] || aKey[2].localeCompare(bKey[2]);
  });
}

function favoriteModelProfiles(rawFavorites: unknown, profiles: ModelProfile[], preferredModel: string): ModelProfile[] {
  const favoriteIds = Array.isArray(rawFavorites)
    ? rawFavorites.map((item) => String(item))
    : typeof rawFavorites === "string"
      ? rawFavorites.split(/\r?\n|,/).map((item) => item.trim())
      : [preferredModel];
  const uniqueIds = favoriteIds.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index);
  const selected = uniqueIds
    .map((profileId) => findProfile(profiles, profileId) ?? {
      profile_id: profileId,
      qualified_model_id: profileId,
      display_name: profileId,
      max_context: -1,
      supports_thinking: false,
      thinking_levels: [],
    })
    .filter(Boolean);
  if (selected.length > 0) return selected;
  const fallback = findProfile(profiles, preferredModel);
  return fallback ? [fallback] : [];
}

function profileIdentity(profile: ModelProfile | null | undefined): string {
  if (!profile) return "";
  return profile.profile_id || profile.qualified_model_id || `${profile.provider_id ?? ""}/${profile.model_id ?? ""}`;
}

function profileDefaults(profile: ModelProfile | null | undefined): Record<string, unknown> {
  if (!profile) return {};
  const metadataDefaults = profile.metadata?.defaults;
  if (metadataDefaults && typeof metadataDefaults === "object" && !Array.isArray(metadataDefaults)) {
    return { ...(metadataDefaults as Record<string, unknown>), ...(profile.defaults ?? {}) };
  }
  return profile.defaults ?? {};
}

function profileIsChatSelectable(profile: ModelProfile | null | undefined): boolean {
  if (!profile) return false;
  const type = String(profile.type ?? "chat").toLowerCase();
  if (!type || type === "chat") return true;
  if (type !== "reasoning") return false;
  const defaults = profileDefaults(profile);
  const metadataCapabilities = profile.metadata?.capabilities;
  const capabilities = metadataCapabilities && typeof metadataCapabilities === "object" && !Array.isArray(metadataCapabilities)
    ? metadataCapabilities as Record<string, unknown>
    : {};
  return Boolean(
    defaults.chat
    || capabilities.chat
    || capabilities.text
    || profile.capability_tags?.includes("chat"),
  );
}

function profilePriceTier(profile: ModelProfile | null | undefined): string {
  if (!profile) return "";
  if (profile.cost_tier) return String(profile.cost_tier);
  const defaults = profileDefaults(profile);
  const pricing = profile.pricing ?? (profile.metadata?.pricing as Record<string, unknown> | undefined) ?? {};
  const explicit = String(
    pricing.tier
    ?? pricing.price_tier
    ?? defaults.price
    ?? defaults.price_tier
    ?? "",
  ).toLowerCase();
  if (explicit) return explicit;
  const modelId = String(profile.model_id ?? profile.profile_id ?? "").toLowerCase();
  if (defaults.large || defaults.heavy) return "high";
  if (defaults.fast || /(?:mini|nano|lite|flash|free|small|cheap)/.test(modelId)) return "low";
  return "";
}

function profileSupportsFast(profile: ModelProfile | null | undefined): boolean {
  if (!profile) return false;
  if (profile.supports_fast || profile.speed_tier === "fast") return true;
  const defaults = profileDefaults(profile);
  const tags = Array.isArray(profile.metadata?.tags) ? profile.metadata?.tags : [];
  const traits = Array.isArray(profile.metadata?.traits) ? profile.metadata?.traits : [];
  return Boolean(defaults.fast || tags.includes("fast") || traits.includes("fast_response"));
}

function profileSupportsThinking(profile: ModelProfile | null | undefined): boolean {
  return Boolean(profile?.supports_thinking && profile.thinking_levels?.length);
}

function bestConfiguredCandidate(candidates: ModelProfile[]): ModelProfile | null {
  if (candidates.length === 0) return null;
  return [...candidates].sort((a, b) => {
    const configured = Number(isConfiguredProfile(b)) - Number(isConfiguredProfile(a));
    if (configured) return configured;
    const local = Number(Boolean(b.local)) - Number(Boolean(a.local));
    if (local) return local;
    return (a.display_name || a.profile_id).localeCompare(b.display_name || b.profile_id);
  })[0] ?? null;
}

function fastCandidateForProfile(activeProfile: ModelProfile | null, profiles: ModelProfile[]): ModelProfile | null {
  if (!activeProfile) return null;
  if (profileSupportsFast(activeProfile)) return activeProfile;
  const providerId = String(activeProfile.provider_id ?? "");
  const providerDefaults = activeProfile.metadata?.default_model_for;
  const fastModel = providerDefaults && typeof providerDefaults === "object"
    ? String((providerDefaults as Record<string, unknown>).fast ?? "")
    : "";
  if (providerId && fastModel) {
    const providerFast = profiles.find((profile) => (
      profile.provider_id === providerId
      && (profile.model_id === fastModel || profile.qualified_model_id === `${providerId}/${fastModel}`)
      && profileSupportsFast(profile)
    ));
    if (providerFast) return providerFast;
  }
  const sameModelKey = String(activeProfile.same_model_across_providers_key ?? activeProfile.model_id ?? "").toLowerCase();
  const sameModelFast = profiles.filter((profile) => (
    profileIdentity(profile) !== profileIdentity(activeProfile)
    && profileSupportsFast(profile)
    && String(profile.same_model_across_providers_key ?? profile.model_id ?? "").toLowerCase() === sameModelKey
  ));
  if (sameModelFast.length) return bestConfiguredCandidate(sameModelFast);
  const providerFast = profiles.filter((profile) => (
    profile.provider_id === providerId
    && profileSupportsFast(profile)
    && profileIsChatSelectable(profile)
  ));
  return bestConfiguredCandidate(providerFast);
}

function priceCandidateForProfile(activeProfile: ModelProfile | null, profiles: ModelProfile[], tier: string): ModelProfile | null {
  const normalizedTier = tier === "high" ? "high" : "low";
  if (!activeProfile) return null;
  if (profilePriceTier(activeProfile) === normalizedTier || profileDefaults(activeProfile)[`price_${normalizedTier}`]) {
    return activeProfile;
  }
  const sameModelKey = String(activeProfile.same_model_across_providers_key ?? activeProfile.model_id ?? "").toLowerCase();
  if (!sameModelKey) return null;
  const sameModelCandidates = profiles.filter((profile) => (
    profileIdentity(profile) !== profileIdentity(activeProfile)
    && String(profile.same_model_across_providers_key ?? profile.model_id ?? "").toLowerCase() === sameModelKey
    && (profilePriceTier(profile) === normalizedTier || Boolean(profileDefaults(profile)[`price_${normalizedTier}`]))
  ));
  if (sameModelCandidates.length) return bestConfiguredCandidate(sameModelCandidates);
  return null;
}

function visionCandidateForProfile(activeProfile: ModelProfile | null, profiles: ModelProfile[]): ModelProfile | null {
  if (activeProfile?.supports_vision || activeProfile?.supports_image_input) return activeProfile;
  const providerId = String(activeProfile?.provider_id ?? "");
  const sameProvider = profiles.filter((profile) => (
    profile.provider_id === providerId
    && (profile.supports_vision || profile.supports_image_input)
    && profileIsChatSelectable(profile)
  ));
  if (sameProvider.length > 0) return bestConfiguredCandidate(sameProvider);
  const anyVision = profiles.filter((profile) => (
    (profile.supports_vision || profile.supports_image_input)
    && profileIsChatSelectable(profile)
  ));
  return bestConfiguredCandidate(anyVision);
}

function contextUsageFor(conversation: Conversation | null, profile: ModelProfile | null): ContextUsageInfo {
  const usedTokens = (conversation?.messages ?? []).reduce((total, message) => {
    const usage = message.usage ?? {};
    return total + Number(usage.total_tokens ?? usage.input_tokens ?? usage.prompt_tokens ?? 0);
  }, 0);
  const maxContext = Number(profile?.max_context_tokens ?? profile?.max_context ?? 0);
  if (maxContext < 0) {
    return { usedTokens, maxContext, ratio: 0, label: "∞" };
  }
  if (!maxContext) {
    return { usedTokens, maxContext: 0, ratio: 0, label: "?" };
  }
  const ratio = Math.min(1, Math.max(0, usedTokens / maxContext));
  return { usedTokens, maxContext, ratio, label: `${Math.round(ratio * 100)}%` };
}

function composerExtensionItems(items: SidebarItem[]): ComposerExtensionItem[] {
  return items
    .filter((item) => item.category === "tool" || item.category === "capability")
    .map((item) => ({
      id: item.id,
      label: item.label,
      category: item.category,
      description: item.description,
      tags: item.tags ?? [],
      ui: item.ui,
    }));
}

function chatIdFromLocation(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("chat") || null;
}

function isPendingInLocation(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get("pending") === "1";
}

function replaceChatIdInUrl(conversationId: string | null, pending?: boolean) {
  const url = new URL(window.location.href);
  url.pathname = window.location.pathname === "/coding" ? "/coding" : "/chat";
  if (conversationId) {
    url.searchParams.set("chat", conversationId);
  } else {
    url.searchParams.delete("chat");
  }
  if (pending === true) {
    url.searchParams.set("pending", "1");
  } else if (pending === false || !conversationId) {
    url.searchParams.delete("pending");
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== current) {
    window.history.pushState({ conversationId }, "", next);
  }
}

function commandNames(command: ComposerCommandItem): string[] {
  return [command.id, command.name, ...(command.aliases ?? [])]
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function matchCommandName(body: string, candidate: string): string | null {
  const directPattern = new RegExp(`^${escapeRegExp(candidate)}(?:\\s+|$)`, "i");
  const directMatch = body.match(directPattern);
  if (directMatch) return directMatch[0].trimEnd();

  const candidateParts = candidate.split(/[\s_-]+/).filter(Boolean);
  if (candidateParts.length < 2) return null;
  const flexiblePattern = new RegExp(`^${candidateParts.map(escapeRegExp).join("[\\s_-]+")}(?:\\s+|$)`, "i");
  const flexibleMatch = body.match(flexiblePattern);
  return flexibleMatch ? flexibleMatch[0].trimEnd() : null;
}

type ParsedSlashCommandInput = {
  command: ComposerCommandItem;
  args: Record<string, unknown>;
  raw: string;
};

export function parseSlashCommandInput(input: string, commands: ComposerCommandItem[]): ParsedSlashCommandInput | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return null;
  const body = trimmed.slice(1).trim();
  if (!body) return null;
  const normalizedBody = body.toLowerCase();

  let matchedCommand: ComposerCommandItem | null = null;
  let matchedName = "";
  for (const item of commands) {
    const candidate = commandNames(item)
      .map((name) => matchCommandName(normalizedBody, name))
      .find((name): name is string => Boolean(name));
    if (!candidate || candidate.length <= matchedName.length) continue;
    matchedCommand = item;
    matchedName = candidate;
  }
  if (!matchedCommand) return null;

  const rest = body.slice(matchedName.length).trim();
  const args: Record<string, unknown> = {};
  const specs = matchedCommand.args ?? [];
  if (specs.length === 1 && rest) {
    args[specs[0].name] = rest;
  } else if (specs.length > 1 && rest) {
    const tokens = rest.split(/\s+/);
    specs.forEach((spec, index) => {
      if (index === specs.length - 1) {
        const remainder = tokens.slice(index).join(" ");
        if (remainder) args[spec.name] = remainder;
      } else if (tokens[index]) {
        args[spec.name] = tokens[index];
      }
    });
  }
  return { command: matchedCommand, args, raw: trimmed };
}

export function parseCommandBoolean(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return fallback;
    if (["false", "0", "off", "no", "n", "disable", "disabled"].includes(normalized)) return false;
    if (["true", "1", "on", "yes", "y", "enable", "enabled"].includes(normalized)) return true;
  }
  return Boolean(value);
}

export function frontendCommandArgs(
  parsedArgs: Record<string, unknown>,
  backendArgs: unknown,
): Record<string, unknown> {
  return isRecord(backendArgs) ? { ...backendArgs } : parsedArgs;
}

export function resolvedFrontendCommandArgs(
  command: ComposerCommandItem,
  parsedArgs: Record<string, unknown>,
  backendArgs: unknown,
): Record<string, unknown> {
  return command.execution.type === "frontend"
    ? parsedArgs
    : frontendCommandArgs(parsedArgs, backendArgs);
}

type UltraYoloModeState = {
  yoloMode: boolean;
  ultraYoloMode: boolean;
  restoreYoloMode: boolean;
};

export function resolveUltraYoloModeState(
  state: UltraYoloModeState,
  enabled: boolean,
): UltraYoloModeState {
  if (enabled) {
    if (state.ultraYoloMode) {
      return { ...state, yoloMode: true, ultraYoloMode: true };
    }
    return {
      yoloMode: true,
      ultraYoloMode: true,
      restoreYoloMode: state.yoloMode,
    };
  }

  if (!state.ultraYoloMode) {
    return {
      yoloMode: state.yoloMode,
      ultraYoloMode: false,
      restoreYoloMode: false,
    };
  }

  return {
    yoloMode: state.restoreYoloMode,
    ultraYoloMode: false,
    restoreYoloMode: false,
  };
}

export function keepSelectedToolsAfterSend(settingsValues: Record<string, Record<string, unknown>>): boolean {
  return parseCommandBoolean(settingsValues.tools?.keep_selected_tools_after_send, true);
}

function commandSearchText(command: ComposerCommandItem): string {
  return [
    command.id,
    command.name,
    ...(command.aliases ?? []),
    command.label,
    command.description ?? "",
  ].join(" ").toLowerCase();
}

function isModelCommand(command: ComposerCommandItem | undefined): boolean {
  if (!command) return false;
  return [command.id, command.name, ...(command.aliases ?? [])]
    .map((value) => String(value ?? "").toLowerCase())
    .includes("model");
}

function modelCandidateProfileId(candidate: ModelCommandCandidate): string {
  return String(candidate.profile_id ?? candidate.qualified_model_id ?? "").trim();
}

function selectedModelProfileId(value: ComposerCommandExecuteResult["selected_model"]): string {
  if (typeof value === "string") return value.trim();
  if (value && typeof value === "object") return modelCandidateProfileId(value);
  return "";
}

function modelCommandInputQuery(value: string): string | null {
  const match = value.trim().match(/^\/models?(?:\s+([\s\S]*))?$/i);
  if (!match) return null;
  return String(match[1] ?? "").trim();
}

export default function App() {
  const [catalog, setCatalog] = useState<UICatalog | null>(null);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [settingsSections, setSettingsSections] = useState<SettingsSection[]>([]);
  const [settingsValues, setSettingsValues] = useState<Record<string, Record<string, unknown>>>({});
  const [desktopSystemInfo, setDesktopSystemInfo] = useState<DesktopSystemInfo | null>(null);
  const [commandCatalog, setCommandCatalog] = useState<ComposerCommandItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useLocalStorage("rumi-input", "");
  const [composerCandidateMenu, setComposerCandidateMenu] = useState<ComposerCandidateMenuState>(null);
  const [isSpotlightOpen, setIsSpotlightOpen] = useState(false);
  const [spotlightQuery, setSpotlightQuery] = useState("");
  const [spotlightFilter, setSpotlightFilter] = useState<SpotlightFilter>("all");
  const [spotlightResults, setSpotlightResults] = useState<ConversationSearchResult[]>([]);
  const [spotlightSelectedIndex, setSpotlightSelectedIndex] = useState(0);
  const [spotlightLoading, setSpotlightLoading] = useState(false);
  const [modelPickerRequestId, setModelPickerRequestId] = useState(0);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [requestedSettingsSectionId, setRequestedSettingsSectionId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useLocalStorage("rumi-show-preview", false);
  const [workspacePanelMode, setWorkspacePanelMode] = useState<WorkspacePanelMode>("composer");
  const [isHistoryMinimized, setIsHistoryMinimized] = useLocalStorage("rumi-history-minimized", false);
  const [isNewChatLaunching, setIsNewChatLaunching] = useState(false);
  const [modelSteerStatus, setModelSteerStatus] = useState<string | null>(null);
  const [modelSteerBusy, setModelSteerBusy] = useState(false);
  const [steerItems, setSteerItems] = useState<ConversationSteerItem[]>([]);
  const [previewMode, setPreviewMode] = useLocalStorage<ToolPreviewMode>("rumi-preview-mode", "auto");
  const [activityPreviewWidth, setActivityPreviewWidth] = useLocalStorage("rumi-activity-preview-width", 340);
  const [canvasMemo, setCanvasMemo] = useLocalStorage("rumi-canvas-memo", "");
  const [activePreviewId, setActivePreviewId] = useState<string | null>(null);
  const [previews, setPreviews] = useState<ToolPreviewItem[]>([]);
  const [settledRuntimeApprovalIds, setSettledRuntimeApprovalIds] = useState<string[]>([]);
  const [health, setHealth] = useState<{ status: string; pack: string; ts: string } | null>(null);
  const [operationsStatus, setOperationsStatus] = useState<OperationsCompanyStatus | null>(null);
  const [operationsBusy, setOperationsBusy] = useState(false);
  const [activeSidebarItemId, setActiveSidebarItemId] = useState<string | null>(null);
  const [sidebarSelectionTick, setSidebarSelectionTick] = useState(0);
  const [yoloMode, setYoloMode] = useLocalStorage("rumi-yolo-mode", false);
  const [ultraYoloMode, setUltraYoloMode] = useLocalStorage("rumi-ultra-yolo-mode", false);
  const [ultraYoloRestoreYoloMode, setUltraYoloRestoreYoloMode] = useLocalStorage("rumi-ultra-yolo-restore-yolo-mode", false);
  const [mode, setMode] = useLocalStorage<AppMode>("rumi-app-mode", "agent");
  const [codingContext, setCodingContext] = useState<CodingContext | null>(null);
  const [codingWorkspaces, setCodingWorkspaces] = useState<CodingWorkspaceRecord[]>([]);
  const [selectedCodingWorkspaceId, setSelectedCodingWorkspaceId] = useState<string | null>(null);
  const [pendingNewTaskContext, setPendingNewTaskContext] = useState<PendingNewTaskContext | null>(null);
  const [codingDirectory, setCodingDirectory] = useState(".");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [droppedWidgets, setDroppedWidgets] = useState<DroppedWidget[]>([]);
  const [storedSelectedToolIds, setStoredSelectedToolIds] = useLocalStorage<string[]>("rumi-selected-tool-ids", []);
  const pendingStorageKey = "rumi-pending-chat-requests";
  const [pendingRequests, setPendingRequests] = useLocalStorage<Record<string, PendingChatRequest>>(pendingStorageKey, {});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isUnloadingRef = useRef(false);
  const currentAbortControllerRef = useRef<AbortController | null>(null);
  const streamingConversationIdRef = useRef<string | null>(null);
  const activeRuntimeApprovalActionRef = useRef<string | null>(null);

  useEffect(() => {
    if (mode === "chat") {
      setMode("agent");
    }
  }, [mode, setMode]);

  const rawSidebarItems: SidebarItem[] = catalog?.sidebar.items ?? [];
  const chatItems = buildChatItems(conversations);
  const recentSpotlightResults = useMemo(
    () => conversations
      .filter((conversation) => conversationMatchesSpotlightFilter(conversation, spotlightFilter))
      .slice(0, 10)
      .map(conversationToSearchResult),
    [conversations, spotlightFilter],
  );
  const visibleSpotlightResults = spotlightQuery.trim() ? spotlightResults : recentSpotlightResults;
  const activeModelId = activeConversation?.model ?? String(settingsValues.models?.preferred_model ?? "stub/default").trim();
  const activeProfile = findProfile(modelProfiles, activeModelId);
  const orderedMessages = useMemo(
    () => activeConversation ? orderConversationMessages(activeConversation.messages) : [],
    [activeConversation?.messages],
  );
  const latestActiveMessage = activeConversation?.messages[activeConversation.messages.length - 1];
  const latestActiveMetadata = latestActiveMessage?.metadata && typeof latestActiveMessage.metadata === "object"
    ? latestActiveMessage.metadata as Record<string, unknown>
    : {};
  const latestActiveThinking = latestActiveMetadata.thinking && typeof latestActiveMetadata.thinking === "object"
    ? latestActiveMetadata.thinking as Record<string, unknown>
    : {};
  const latestActivePendingSignature = latestActiveMessage
    ? `${latestActiveMessage.id}:${latestActiveMessage.role}:${latestActiveMessage.finish_reason ?? ""}:${String(latestActiveThinking.state ?? "")}`
    : "";
  const messages = orderedMessages.map((message) => toUiMessage(message, activeProfile));
  const activeChatTitle = activeConversation?.title ?? "New Conversation";
  const isNewConversation = activeConversation === null || activeConversation.messages.length === 0;
  const placeholder = String(settingsValues.general?.composer_placeholder ?? "メッセージを入力...");
  const locale = normalizeLocale(settingsValues.general?.language);
  const keyboardButtonNavigation = parseCommandBoolean(settingsValues.general?.keyboard_button_navigation, false);
  const disabledToolIds = settingList(settingsValues.tools?.disabled_tool_ids);
  const hiddenToolIds = settingList(settingsValues.tools?.hidden_tool_ids);
  const disabledToolIdSet = useMemo(() => new Set(disabledToolIds), [disabledToolIds]);
  const hiddenToolIdSet = useMemo(() => new Set(hiddenToolIds), [hiddenToolIds]);
  const sidebarItems: SidebarItem[] = useMemo(
    () => rawSidebarItems.filter((item) => item.category !== "tool" || !hiddenToolIdSet.has(item.id)),
    [hiddenToolIdSet, rawSidebarItems],
  );
  const preferredModel = activeModelId;
  const selectableModelProfiles = userFacingModelProfiles(modelProfiles, preferredModel);
  const favoriteProfiles = favoriteModelProfiles(settingsValues.models?.favorite_profiles, selectableModelProfiles, preferredModel);
  const thinkingLevels = (settingsValues.models?.thinking_level_by_profile ?? {}) as Record<string, unknown>;
  const selectedThinkingLevel = String(
    thinkingLevels[profileKey(activeProfile, preferredModel)]
    ?? settingsValues.models?.thinking_level
    ?? activeProfile?.default_thinking_level
    ?? "medium",
  );
  const contextUsage = contextUsageFor(activeConversation, activeProfile);
  const composerExtensions = useMemo(
    () => composerExtensionItems(sidebarItems).filter((item) => !disabledToolIdSet.has(item.id)),
    [disabledToolIdSet, sidebarItems],
  );
  const composerSkills = useMemo<ComposerSkillItem[]>(() => (
    (catalog?.skills ?? []).map((skill) => ({
      id: skill.id,
      label: skill.label ?? skill.id,
      description: skill.description,
      triggers: skill.triggers ?? [],
      appliesToTools: skill.applies_to_tools ?? [],
      aliases: skill.aliases ?? [],
      metadata: skill.metadata,
    }))
  ), [catalog?.skills]);
  const selectedTools = useMemo(() => storedSelectedToolIds
    .map((toolId) => composerExtensions.find((tool) => tool.id === toolId))
    .filter((tool): tool is ComposerExtensionItem => Boolean(tool)), [composerExtensions, storedSelectedToolIds]);
  const selectedToolIds = useMemo(() => selectedTools.map((tool) => tool.id), [selectedTools]);
  const selectedToolIdSet = useMemo(() => new Set(selectedToolIds), [selectedToolIds]);
  const pendingRequest = activeConversationId ? pendingRequests[activeConversationId] : null;
  const isConversationPending = Boolean(
    pendingRequest && Date.now() - pendingRequest.startedAt < PENDING_CHAT_REQUEST_TTL_MS,
  );
  const browserApproval = pendingBrowserApproval(messages);
  const rawRuntimeApproval = pendingRuntimeApproval(messages);
  const settledRuntimeApprovalIdSet = useMemo(() => new Set(settledRuntimeApprovalIds), [settledRuntimeApprovalIds]);
  const runtimeApproval = !ultraYoloMode && rawRuntimeApproval && !settledRuntimeApprovalIdSet.has(rawRuntimeApproval.requestId)
    ? rawRuntimeApproval
    : null;
  const staleRuntimeApprovalNotice = !ultraYoloMode && !rawRuntimeApproval ? staleRuntimeApproval(messages) : null;
  const visibleBrowserApproval = !ultraYoloMode ? browserApproval : null;
  const composerModelStatusIndicators = useMemo<ComposerModelStatusIndicator[]>(() => {
    if (ultraYoloMode) {
      return [
        {
          id: "ultra-yolo",
          name: "Ultra YOLO",
          description: "Ultra YOLO が ON です。承認が必要な coding / browser 操作まで自動許可されます。",
          svgMarkup: dangerShieldSvg,
          tone: "danger",
          action: {
            label: "YOLO に戻す",
            tone: "danger",
            onSelect: () => {
              setUltraYoloMode(false);
              setYoloMode(true);
              setUltraYoloRestoreYoloMode(false);
            },
          },
        },
      ];
    }

    if (yoloMode) {
      return [
        {
          id: "yolo",
          name: "YOLO",
          description: "YOLO が ON です。承認不要の tool は自動実行されます。",
          svgMarkup: dangerShieldSvg,
          tone: "warning",
          action: {
            label: "標準に戻す",
            tone: "warning",
            onSelect: () => {
              setUltraYoloMode(false);
              setYoloMode(false);
              setUltraYoloRestoreYoloMode(false);
            },
          },
        },
      ];
    }

    return [];
  }, [ultraYoloMode, yoloMode, setUltraYoloMode, setUltraYoloRestoreYoloMode, setYoloMode]);
  const messageToolPreviews = useMemo(
    () => toolPreviewsFromMessages(activeConversation?.messages ?? []),
    [activeConversation?.messages],
  );
  const liveBrowserState = useMemo(
    () => reduceBrowserStateFromEvents((activeConversation?.messages ?? []).flatMap((message) => message.events ?? [])),
    [activeConversation?.messages],
  );
  const latestToolFilterContext = useMemo(
    () => extractLatestToolFilterContext(activeConversation?.messages ?? []),
    [activeConversation?.messages],
  );
  const runtimeCapabilitySnapshot = latestToolFilterContext.snapshot;
  const toolFilterEntries = latestToolFilterContext.entries;
  const preferredVisionCandidate = useMemo(
    () => visionCandidateForProfile(activeProfile, selectableModelProfiles),
    [activeProfile, selectableModelProfiles],
  );
  const canvasPreviews = useMemo(() => {
    const seenIds = new Set(previews.map((preview) => preview.id));
    const seenIdentities = new Set(previews.map(canvasPreviewIdentity));
    return [
      ...previews,
      ...messageToolPreviews.filter((preview) => {
        const identity = canvasPreviewIdentity(preview);
        if (seenIds.has(preview.id) || seenIdentities.has(identity)) return false;
        seenIds.add(preview.id);
        seenIdentities.add(identity);
        return true;
      }),
    ].sort((a, b) => b.timestamp - a.timestamp);
  }, [messageToolPreviews, previews]);
  const canShowCanvas = hasCanvasItems(canvasPreviews, canvasMemo) || liveBrowserState.state_revision >= 0;
  const effectiveShowPreview = showPreview && canShowCanvas;
  const composerCommands = useMemo(() => {
    const showAdvanced = settingsValues.commands?.show_advanced_commands === true;
    const fastCandidate = fastCandidateForProfile(activeProfile, selectableModelProfiles);
    const priceLowCandidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, "low");
    const priceHighCandidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, "high");
    return commandCatalog
      .filter((command) => command.visibility !== "hidden")
      .filter((command) => showAdvanced || command.visibility === "default")
      .filter((command) => !command.modes?.length || command.modes.includes(mode as ComposerCommandMode))
      .filter((command) => command.id !== "fast" || Boolean(fastCandidate))
      .filter((command) => command.id !== "price" || Boolean(priceLowCandidate || priceHighCandidate))
      .filter((command) => command.id !== "think" || profileSupportsThinking(activeProfile))
      .map((command) => ({
        ...command,
        active: command.id === "yolo" ? (yoloMode || ultraYoloMode) : command.id === "ultra_yolo" ? ultraYoloMode : command.id === mode,
        enabled: command.id === "yolo" ? (yoloMode || ultraYoloMode) : command.id === "ultra_yolo" ? ultraYoloMode : command.id === mode,
      }));
  }, [activeProfile, commandCatalog, mode, selectableModelProfiles, settingsValues.commands?.show_advanced_commands, ultraYoloMode, yoloMode]);
  const modelCommandCandidates = composerCandidateMenu?.mode === "model" ? composerCandidateMenu.candidates : [];
  const unknownBlockStrategy = String(settingsValues.chat_rendering?.unknown_block_strategy ?? "hidden");
  const showWidgets = settingsValues.chat_rendering?.show_widgets !== false;
  const showActivityInMessages = settingsValues.general?.show_activity_in_messages !== false;
  const showRegion = (regionId: string) => !catalog?.shell || hasShellRegion(catalog, regionId);
  const isActivityPreviewVisible = showRegion("activity_preview") && effectiveShowPreview;
  const activityPreviewWidthPx = clampNumber(activityPreviewWidth, 220, 720, 340);
  const operationsProfileAvailable = hasOperationsProfile(catalog);

  const startActivityPreviewResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = activityPreviewWidthPx;
      const handlePointerMove = (moveEvent: PointerEvent) => {
        const nextWidth = clampNumber(startWidth + (startX - moveEvent.clientX), 220, 720, startWidth);
        setActivityPreviewWidth(nextWidth);
      };
      const handlePointerUp = () => {
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
      };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp, { once: true });
    },
    [activityPreviewWidthPx, setActivityPreviewWidth],
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 759px)");
    const applyMobileHistoryLayout = () => {
      if (shouldAutoCompactHistory(window.innerWidth)) {
        setIsHistoryMinimized(true);
      }
    };
    applyMobileHistoryLayout();
    media.addEventListener("change", applyMobileHistoryLayout);
    return () => media.removeEventListener("change", applyMobileHistoryLayout);
  }, [setIsHistoryMinimized]);

  useEffect(() => {
    const validIds = new Set(composerExtensions.map((tool) => tool.id));
    setStoredSelectedToolIds((current) => {
      const next = current.filter((toolId) => validIds.has(toolId));
      return next.length === current.length ? current : next;
    });
  }, [composerExtensions, setStoredSelectedToolIds]);

  const updatePendingRequests = (updater: (current: Record<string, PendingChatRequest>) => Record<string, PendingChatRequest>) => {
    setPendingRequests((current) => {
      const next = updater(current);
      writeJsonLocalStorage(pendingStorageKey, next);
      return next;
    });
  };

  const rememberPendingRequest = (request: PendingChatRequest) => {
    updatePendingRequests((current) => ({
      ...current,
      [request.conversationId]: request,
    }));
  };

  const forgetPendingRequest = (conversationId: string) => {
    updatePendingRequests((current) => {
      const next = { ...current };
      delete next[conversationId];
      return next;
    });
  };

  const loadCodingWorkspaces = useCallback(async () => {
    try {
      const result = await api.listCodingWorkspaces();
      setCodingWorkspaces(result.workspaces);
      setSelectedCodingWorkspaceId((current) => current ?? result.selected_workspace_id ?? result.workspaces[0]?.workspace_id ?? null);
      return result;
    } catch {
      setCodingWorkspaces([]);
      return { workspaces: [], selected_workspace_id: null };
    }
  }, []);

  const activeConversationWorkspaceContext = useMemo(
    () => workspaceContextFromConversation(activeConversation),
    [activeConversation],
  );
  const effectiveWorkspaceId = pendingNewTaskContext?.workspaceId
    ?? activeConversationWorkspaceContext.workspaceId
    ?? selectedCodingWorkspaceId;
  const effectiveGroupId = pendingNewTaskContext?.groupId
    ?? activeConversationWorkspaceContext.groupId
    ?? undefined;
  const effectiveConsoleKey = `${effectiveGroupId ?? "ungrouped"}:${effectiveWorkspaceId ?? "no-workspace"}`;

  const loadCodingContext = useCallback(async () => {
    const workspaceId = effectiveWorkspaceId;
    try {
      const [result, branchInfo] = await Promise.all([
        api.getCodingContext({ directory: codingDirectory, workspace_id: workspaceId }),
        api.getGitBranch({ workspace_id: workspaceId }).catch(() => null),
      ]);
      setCodingContext({
        branch: result.branch,
        rootFolder: result.root_folder,
        workspaceId: result.workspace_id ?? workspaceId,
        directory: result.directory ?? codingDirectory,
        branches: branchInfo?.branches ?? [],
        files: result.files,
        entries: result.entries,
        git: result.git,
      });
    } catch {
      setCodingContext(null);
    }
  }, [codingDirectory, effectiveWorkspaceId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  useEffect(() => {
    const markUnloading = () => {
      isUnloadingRef.current = true;
    };
    window.addEventListener("beforeunload", markUnloading);
    window.addEventListener("pagehide", markUnloading);
    return () => {
      window.removeEventListener("beforeunload", markUnloading);
      window.removeEventListener("pagehide", markUnloading);
    };
  }, []);

  useEffect(() => {
    const handleOauthMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const payload = event.data;
      if (!payload || typeof payload !== "object") return;
      if ((payload as Record<string, unknown>).type !== "rumi_provider_oauth") return;
      const providerId = String((payload as Record<string, unknown>).provider_id ?? "").trim();
      if (providerId) {
        void refreshProviderOAuthStatus(providerId).catch(console.error);
        return;
      }
      void refreshCatalog().catch(console.error);
    };
    window.addEventListener("message", handleOauthMessage);
    return () => {
      window.removeEventListener("message", handleOauthMessage);
    };
  }, []);

  useEffect(() => {
    if (mode === "coding") {
      void loadCodingWorkspaces().then(() => loadCodingContext());
    }
  }, [mode, loadCodingContext, loadCodingWorkspaces]);

  useEffect(() => {
    if (window.location.pathname !== "/coding") return;
    setMode("coding");
  }, [setMode]);

  useEffect(() => {
    if (!isSettingsOpen) return;
    let cancelled = false;
    void fetchDesktopSystemInfo()
      .then((info) => {
        if (!cancelled) setDesktopSystemInfo(info);
      })
      .catch((infoError) => {
        console.error(infoError);
        if (!cancelled) setDesktopSystemInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isSettingsOpen]);

  async function refreshHealth() {
    try {
      setHealth(await api.health());
    } catch (healthError) {
      console.error(healthError);
    }
  }

  function mergeProviderOAuthStatus(providerId: string, oauthStatus: Record<string, unknown>) {
    setSettingsValues((current) => {
      const apiSection = current.apis;
      const apiKeys = apiSection?.api_keys;
      if (!Array.isArray(apiKeys)) return current;

      let updated = false;
      const nextApiKeys = apiKeys.map((entry) => {
        if (!entry || typeof entry !== "object") return entry;
        const provider = entry as Record<string, unknown>;
        if (String(provider.provider_id ?? "").trim() !== providerId) return provider;

        updated = true;
        const existingOauth = provider.oauth && typeof provider.oauth === "object" && !Array.isArray(provider.oauth)
          ? provider.oauth as Record<string, unknown>
          : {};
        return {
          ...provider,
          oauth: {
            ...existingOauth,
            ...oauthStatus,
          },
        };
      });

      if (!updated) return current;
      return {
        ...current,
        apis: {
          ...(apiSection ?? {}),
          api_keys: nextApiKeys,
        },
      };
    });
  }

  async function refreshProviderOAuthStatus(providerId: string) {
    const result = await api.providerOAuthStatus(providerId);
    if (result.provider && typeof result.provider === "object" && !Array.isArray(result.provider)) {
      mergeProviderOAuthStatus(providerId, result.provider as Record<string, unknown>);
    }
    void refreshCatalog().catch(console.error);
  }

  async function refreshCatalog() {
    const [catalogResult, settingsResult, profilesResult, commandsResult] = await Promise.allSettled([
      api.uiCatalog(),
      api.uiSettings(),
      api.listModelProfiles(),
      api.uiCommands(),
    ]);
    const nextCatalog = catalogResult.status === "fulfilled" ? catalogResult.value : null;
    const nextSettings = settingsResult.status === "fulfilled" ? settingsResult.value : null;
    if (nextCatalog) {
      setCatalog(nextCatalog);
    } else {
      if (catalogResult.status === "rejected") console.error(catalogResult.reason);
      setCatalog(null);
    }
    if (profilesResult.status === "fulfilled") {
      setModelProfiles(profilesResult.value.profiles);
    } else {
      console.error(profilesResult.reason);
      setModelProfiles([]);
    }
    if (nextSettings) {
      setSettingsSections(withCalendarSettingsSections(nextSettings.sections));
      setSettingsValues(withCalendarSettingsValues(nextSettings.values));
    } else {
      if (settingsResult.status === "rejected") console.error(settingsResult.reason);
    }
    if (commandsResult.status === "fulfilled") {
      setCommandCatalog(commandsResult.value.commands);
    } else {
      console.error(commandsResult.reason);
      setCommandCatalog([]);
    }
    const defaultMode = nextSettings?.values.preview?.default_mode;
    if (defaultMode === "auto" || defaultMode === "manual") {
      setPreviewMode(defaultMode);
    }
    return nextCatalog;
  }

  async function refreshOperationsStatus() {
    try {
      setOperationsStatus(await api.getOperationsCompanyStatus());
    } catch (statusError) {
      console.error(statusError);
    }
  }

  async function refreshPreview(conversationId: string | null) {
    if (!conversationId) {
      setPreviews([]);
      setActivePreviewId(null);
      return;
    }
    try {
      const result = await api.conversationPreview(conversationId);
      const limit = Number(settingsValues.preview?.max_items ?? 12);
      const nextPreviews = result.previews.slice(0, limit);
      setPreviews(nextPreviews);
      setActivePreviewId(nextPreviews[0]?.id ?? null);
      if (settingsValues.preview?.auto_open && nextPreviews.length > 0) {
        setShowPreview(true);
      }
    } catch (previewError) {
      console.error(previewError);
      setPreviews([]);
      setActivePreviewId(null);
    }
  }

  async function loadConversation(conversationId: string | null, updateUrl = true) {
    if (!conversationId) {
      setActiveConversationId(null);
      setActiveConversation(null);
      void refreshPreview(null);
      if (updateUrl) replaceChatIdInUrl(null, false);
      return;
    }
    const conversation = await api.getConversation(conversationId);
    setActiveConversationId(conversationId);
    setActiveConversation(conversation);
    if (updateUrl) replaceChatIdInUrl(conversationId);
    void refreshPreview(conversationId);
  }

  async function refreshConversations(preferredId?: string | null) {
    const result = await api.listConversations();
    setConversations(result.conversations);

    const targetId = preferredId ?? activeConversationId ?? chatIdFromLocation() ?? result.conversations[0]?.id ?? null;
    if (!targetId) {
      setActiveConversationId(null);
      setActiveConversation(null);
      void refreshPreview(null);
      return;
    }

    if (!result.conversations.some((conversation) => conversation.id === targetId)) {
      await loadConversation(result.conversations[0]?.id ?? null);
      return;
    }

    await loadConversation(targetId);
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setIsLoading(true);
      const pendingConversationId = chatIdFromLocation();
      if (pendingConversationId && isPendingInLocation()) {
        rememberPendingRequest({
          conversationId: pendingConversationId,
          startedAt: Date.now(),
          status: "Processing...",
          toolNames: [],
          recoveredFromLocation: true,
        });
      }
      const shellBootstrap = Promise.all([refreshHealth(), refreshCatalog()])
        .then(([, nextCatalog]) => {
          if (cancelled || !hasOperationsProfile(nextCatalog)) return;
          return refreshOperationsStatus();
        })
        .catch((shellError) => {
          if (!cancelled) console.error(shellError);
        });
      try {
        if (!cancelled) {
          await refreshConversations(null);
        }
      } catch (bootstrapError) {
        if (!cancelled) {
          setError(
            bootstrapError instanceof Error
              ? bootstrapError.message
              : "defaultspack の読み込みに失敗しました。",
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
      void shellBootstrap;
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!operationsProfileAvailable) return;
    void refreshOperationsStatus();
  }, [operationsProfileAvailable]);

  useEffect(() => {
    const handlePopState = () => {
      setError(null);
      void loadConversation(chatIdFromLocation(), false).catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : "会話の読み込みに失敗しました。");
      });
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshPreview(activeConversationId);
  }, [settingsValues.preview?.max_items, settingsValues.preview?.auto_open, activeConversationId]);

  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey && event.key.toLowerCase() === "k")) return;
      event.preventDefault();
      setIsSpotlightOpen(true);
      setSpotlightSelectedIndex(0);
    };
    document.addEventListener("keydown", handleGlobalKeyDown);
    return () => document.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  useEffect(() => {
    if (!isSpotlightOpen) return;
    const query = spotlightQuery.trim();
    if (!query) {
      setSpotlightResults([]);
      setSpotlightLoading(false);
      return;
    }
    let cancelled = false;
    setSpotlightLoading(true);
    const timeout = window.setTimeout(() => {
      void api.searchConversations(query, {
        date_filter: spotlightFilter === "starred" ? "all" : spotlightFilter,
        is_starred: spotlightFilter === "starred" ? true : undefined,
        role: "all",
        limit: 12,
      }).then((result) => {
        if (cancelled) return;
        setSpotlightResults(result.results);
      }).catch((searchError) => {
        if (cancelled) return;
        console.error(searchError);
        setSpotlightResults([]);
      }).finally(() => {
        if (!cancelled) setSpotlightLoading(false);
      });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [isSpotlightOpen, spotlightFilter, spotlightQuery]);

  useEffect(() => {
    setSpotlightSelectedIndex(0);
  }, [spotlightFilter, spotlightQuery, spotlightResults.length]);

  useEffect(() => {
    if (!activeConversationId || !isConversationPending) return;
    const latestKnown = latestActiveMessage;
    if (shouldClearPendingAfterConversationRefresh(latestKnown, pendingRequest, Date.now())) {
      forgetPendingRequest(activeConversationId);
      replaceChatIdInUrl(activeConversationId, false);
      setIsGenerating(false);
      return;
    }
    if (streamingConversationIdRef.current === activeConversationId) return;
    setIsGenerating(true);
    const pollPendingConversation = () => {
      void api.getConversation(activeConversationId).then((conversation) => {
        setActiveConversation(conversation);
        const latest = conversation.messages[conversation.messages.length - 1];
        if (shouldClearPendingAfterConversationRefresh(latest, pendingRequest, Date.now())) {
          forgetPendingRequest(activeConversationId);
          replaceChatIdInUrl(activeConversationId, false);
          setIsGenerating(false);
          void refreshConversations(conversation.id);
        }
      }).catch((pollError) => {
        console.error(pollError);
        forgetPendingRequest(activeConversationId);
        replaceChatIdInUrl(activeConversationId, false);
        setIsGenerating(false);
        setError(pollError instanceof Error ? pollError.message : "stream 状態の確認に失敗しました。");
      });
    };
    pollPendingConversation();
    const interval = window.setInterval(pollPendingConversation, 1500);
    return () => window.clearInterval(interval);
  }, [activeConversationId, isConversationPending, latestActivePendingSignature, pendingRequest]);

  useEffect(() => {
    const staleIds = Object.entries(pendingRequests)
      .filter(([, request]) => Date.now() - request.startedAt >= PENDING_CHAT_REQUEST_TTL_MS)
      .map(([id]) => id);
    if (staleIds.length === 0) return;
    updatePendingRequests((current) => {
      const next = { ...current };
      for (const id of staleIds) delete next[id];
      return next;
    });
    if (activeConversationId && staleIds.includes(activeConversationId)) {
      setIsGenerating(false);
      replaceChatIdInUrl(activeConversationId, false);
    }
  }, [pendingRequests, activeConversationId]);

  const handleNewTask = (options?: HistoryBoardNewTaskOptions) => {
    const nextContext = workspaceContextFromHistoryOptions(options);
    setPendingNewTaskContext(nextContext);
    if (nextContext?.workspaceId) {
      setMode("coding");
    }
    setActiveConversationId(null);
    setActiveConversation(null);
    setPreviews([]);
    setError(null);
    setIsGenerating(false);
    setAttachedFiles([]);
    setDroppedWidgets([]);
    setWorkspacePanelMode("composer");
    replaceChatIdInUrl(null, false);
  };

  const handleStopGenerating = () => {
    const conversationId = activeConversationId;
    if (conversationId) {
      void api.stopMessage(conversationId).catch(console.error);
    }
    currentAbortControllerRef.current?.abort();
    currentAbortControllerRef.current = null;
    if (conversationId) {
      forgetPendingRequest(conversationId);
      replaceChatIdInUrl(conversationId, false);
    }
    setIsGenerating(false);
    setIsNewChatLaunching(false);
  };

  const handleHistoryClick = (conversationId: string) => {
    setError(null);
    setPendingNewTaskContext(null);
    setWorkspacePanelMode("composer");
    void loadConversation(conversationId);
  };

  const handleHistoryMetadataChange = (conversationId: string, updates: { is_pinned?: boolean; is_starred?: boolean; tags?: string[] }) => {
    setError(null);
    void api.updateConversation(conversationId, updates as Partial<Conversation>)
      .then((conversation) => {
        setConversations((current) => current.map((item) => item.id === conversation.id ? { ...conversation, messages: [] } : item));
        if (activeConversationId === conversation.id) setActiveConversation(conversation);
      })
      .catch((updateError) => setError(updateError instanceof Error ? updateError.message : "会話メタデータの更新に失敗しました。"));
  };

  const closeSpotlight = () => {
    setIsSpotlightOpen(false);
    setSpotlightQuery("");
    setSpotlightResults([]);
    setSpotlightSelectedIndex(0);
  };

  const openSpotlightResult = (result: ConversationSearchResult | undefined) => {
    if (!result?.conversation_id) return;
    closeSpotlight();
    setError(null);
    void loadConversation(result.conversation_id);
  };

  const handleSpotlightKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSpotlight();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSpotlightSelectedIndex((index) => Math.min(index + 1, Math.max(visibleSpotlightResults.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSpotlightSelectedIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      openSpotlightResult(visibleSpotlightResults[spotlightSelectedIndex] ?? visibleSpotlightResults[0]);
    }
  };

  const handleSettingChange = (sectionId: string, fieldId: string, value: unknown) => {
    setSettingsValues((current) => {
      const section = settingsSections.find((item) => item.id === sectionId);
      const field = section?.fields.find((item) => item.id === fieldId);
      const sectionPatch = {
        ...(current[sectionId] ?? {}),
        [fieldId]: field?.type === "secret" || field?.type === "api_keys" || field?.type === "external_tokens" ? "" : value,
      };
      if (sectionId === "external_input" && fieldId === "input_provider") {
        const provider = String(value ?? "line");
        const templateByProvider: Record<string, { template: string; profile: string; endpoint: string; route: string }> = {
          line: { template: "line.input.default", profile: "line.default", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          discord: { template: "discord.input.default", profile: "discord.default", endpoint: "discord-main", route: "/api/integrations/discord/interactions" },
          slack: { template: "slack.input.default", profile: "slack.default", endpoint: "slack-main", route: "/api/integrations/slack/events" },
          generic: { template: "generic.input.default", profile: "generic.webhook.default", endpoint: "generic-main", route: "/api/webhooks/inbound/{webhook_id}" },
        };
        const mapped = templateByProvider[provider] ?? templateByProvider.line;
        sectionPatch.input_template_id = mapped.template;
        sectionPatch.input_profile_id = mapped.profile;
        sectionPatch.input_endpoint_id = mapped.endpoint;
        sectionPatch.public_url_launcher = {
          ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
          route_path: mapped.route,
        };
      } else if (sectionId === "external_input" && fieldId === "input_template_id") {
        const templateId = String(value ?? "");
        const inputByTemplate: Record<string, { provider: string; profile: string; endpoint: string; route: string }> = {
          "line.input.default": { provider: "line", profile: "line.default", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          "line.input.computer_use": { provider: "line", profile: "line.computer_use", endpoint: "line-main", route: "/api/integrations/line/webhook" },
          "discord.input.default": { provider: "discord", profile: "discord.default", endpoint: "discord-main", route: "/api/integrations/discord/interactions" },
          "slack.input.default": { provider: "slack", profile: "slack.default", endpoint: "slack-main", route: "/api/integrations/slack/events" },
          "generic.input.default": { provider: "generic", profile: "generic.webhook.default", endpoint: "generic-main", route: "/api/webhooks/inbound/{webhook_id}" },
        };
        const mapped = inputByTemplate[templateId];
        const provider = mapped?.provider ?? (templateId.split(".")[0] || "line");
        const routeByProvider: Record<string, string> = {
          line: "/api/integrations/line/webhook",
          discord: "/api/integrations/discord/interactions",
          slack: "/api/integrations/slack/events",
          generic: "/api/webhooks/inbound/{webhook_id}",
        };
        sectionPatch.input_provider = provider;
        sectionPatch.input_profile_id = mapped?.profile ?? (provider === "discord" ? "discord.default" : provider === "slack" ? "slack.default" : provider === "generic" ? "generic.webhook.default" : "line.default");
        sectionPatch.input_endpoint_id = mapped?.endpoint ?? `${provider}-main`;
        sectionPatch.public_url_launcher = {
          ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
          route_path: mapped?.route ?? routeByProvider[provider] ?? routeByProvider.line,
        };
      } else if (sectionId === "external_input" && fieldId === "input_response_preset") {
        const preset = String(value ?? "");
        if (preset === "computer_use_line_biz") {
          sectionPatch.input_provider = "line";
          sectionPatch.input_template_id = "line.input.computer_use";
          sectionPatch.input_profile_id = "line.computer_use";
          sectionPatch.input_endpoint_id = "line-main";
          sectionPatch.public_url_launcher = {
            ...((current.external_input?.public_url_launcher as Record<string, unknown> | undefined) ?? {}),
            route_path: "/api/integrations/line/webhook",
          };
        }
      } else if (sectionId === "external_output" && fieldId === "output_provider") {
        const provider = String(value ?? "line");
        const templateByProvider: Record<string, { template: string; profile: string; mode: string }> = {
          line: { template: "line.output.default", profile: "line.default", mode: "reply_to_origin" },
          discord: { template: "discord.output.bot_channel", profile: "discord.bot_channel", mode: "discord_bot_channel" },
          slack: { template: "slack.output.default", profile: "slack.default", mode: "slack_channel" },
          generic: { template: "generic.output.webhook", profile: "generic.webhook", mode: "generic_webhook" },
          web: { template: "generic.output.webhook", profile: "generic.webhook", mode: "web_local" },
        };
        const mapped = templateByProvider[provider] ?? templateByProvider.line;
        sectionPatch.output_template_id = mapped.template;
        sectionPatch.output_profile_id = mapped.profile;
        sectionPatch.output_send_mode = mapped.mode;
      } else if (sectionId === "external_output" && fieldId === "output_template_id") {
        const templateId = String(value ?? "");
        const outputByTemplate: Record<string, { provider: string; profile: string; mode: string }> = {
          "line.output.default": { provider: "line", profile: "line.default", mode: "reply_to_origin" },
          "discord.output.bot_channel": { provider: "discord", profile: "discord.bot_channel", mode: "discord_bot_channel" },
          "discord.output.webhook": { provider: "discord", profile: "discord.webhook", mode: "discord_webhook_url" },
          "slack.output.default": { provider: "slack", profile: "slack.default", mode: "slack_channel" },
          "generic.output.webhook": { provider: "generic", profile: "generic.webhook", mode: "generic_webhook" },
        };
        const mapped = outputByTemplate[templateId];
        if (mapped) {
          sectionPatch.output_provider = mapped.provider;
          sectionPatch.output_profile_id = mapped.profile;
          sectionPatch.output_send_mode = mapped.mode;
        }
      }
      const next = {
        ...current,
        [sectionId]: sectionPatch,
      };
      if (field?.type === "api_keys") {
        const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
        const providerId = String(payload.provider_id ?? "").trim();
        const apiId = String(payload.api_id ?? payload.name ?? "").trim();
        const name = String(payload.name ?? apiId).trim();
        const secret = String(payload.value ?? "");
        const action = String(payload.action ?? "upsert").trim();
        const kind = String(payload.kind ?? "").trim() || undefined;
        if (action === "oauth_refresh") {
          if (providerId) {
            void refreshProviderOAuthStatus(providerId).catch(console.error);
          } else {
            void refreshCatalog().catch(console.error);
          }
          return current;
        } else if (action === "register_provider" && providerId) {
          void api.registerCustomProvider(providerId, {
            label: String(payload.label ?? "").trim() || undefined,
            kind,
          })
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "delete_provider" && providerId) {
          void api.deleteCustomProvider(providerId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "delete" && providerId && apiId) {
          void api.deleteProviderApiKey(providerId, apiId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "rename" && providerId && apiId && name) {
          void api.renameProviderApiKey(providerId, apiId, name)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (providerId && name && secret.trim()) {
          void api.saveProviderApiKey(providerId, secret, {
            apiId: name,
            name,
            baseUrl: String(payload.base_url ?? "").trim() || undefined,
            allowedModels: Array.isArray(payload.allowed_models)
              ? payload.allowed_models.map((item) => String(item ?? "").trim()).filter(Boolean)
              : undefined,
            defaultModel: String(payload.default_model ?? "").trim() || undefined,
            quotaLabel: String(payload.quota_label ?? "").trim() || undefined,
            notes: String(payload.notes ?? "").trim() || undefined,
            kind,
          })
            .then(() => refreshCatalog())
            .catch(console.error);
        }
      } else if (field?.type === "external_tokens") {
        const payload = value && typeof value === "object" ? value as Record<string, unknown> : {};
        const providerId = String(payload.provider_id ?? "").trim();
        const tokenId = String(payload.token_id ?? payload.name ?? "").trim();
        const name = String(payload.name ?? tokenId).trim();
        const kind = String(payload.kind ?? "token").trim();
        const secret = String(payload.value ?? "");
        const action = String(payload.action ?? "upsert").trim();
        if (action === "delete" && providerId && tokenId) {
          void api.deleteExternalToken(providerId, tokenId)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (action === "rename" && providerId && tokenId && name) {
          void api.renameExternalToken(providerId, tokenId, name)
            .then(() => refreshCatalog())
            .catch(console.error);
        } else if (providerId && name && secret.trim()) {
          void api.saveExternalToken(providerId, secret, { tokenId: name, name, kind })
            .then(() => refreshCatalog())
            .catch(console.error);
        }
      } else if (field?.type === "secret") {
        const providerId = field.provider_id ?? fieldId.replace(/_api_key$/, "");
        void api.saveProviderApiKey(providerId, String(value ?? ""))
          .then(() => refreshCatalog())
          .catch(console.error);
      } else {
        void api.updateUiSettings(next).then((result) => setSettingsValues(withCalendarSettingsValues(result.values))).catch(console.error);
      }
      return next;
    });
  };

  const updateModelSettings = (updates: Record<string, unknown>) => {
    const next = {
      ...settingsValues,
      models: {
        ...(settingsValues.models ?? {}),
        ...updates,
      },
    };
    setSettingsValues(withCalendarSettingsValues(next));
    void api.updateUiSettings(next).then((result) => setSettingsValues(withCalendarSettingsValues(result.values))).catch(console.error);
  };

  const handleModelProfileSelect = (profileId: string) => {
    updateModelSettings({ preferred_model: profileId });
    if (activeConversationId) {
      void api.updateConversation(activeConversationId, { model: profileId }).then((conversation) => {
        setActiveConversation(conversation);
        void refreshConversations(conversation.id);
      }).catch(console.error);
    }
  };

  const handleProviderApiKeySave = async (providerId: string, value: string) => {
    await api.saveProviderApiKey(providerId, value);
    await refreshCatalog();
  };

  const handleThinkingLevelChange = (level: string | null) => {
    const key = profileKey(activeProfile, preferredModel);
    updateModelSettings({
      thinking_level: level ?? "medium",
      thinking_level_by_profile: {
        ...thinkingLevels,
        [key]: level,
      },
    });
  };

  const openSettingsSection = useCallback((sectionId: string) => {
    setRequestedSettingsSectionId(sectionId);
    setIsSettingsOpen(true);
  }, []);

  const handleSwitchToVisionModel = useCallback(() => {
    if (preferredVisionCandidate) {
      handleModelProfileSelect(preferredVisionCandidate.profile_id);
      return;
    }
    setError("Vision対応モデルが見つかりません。Model設定から追加してください。");
  }, [handleModelProfileSelect, preferredVisionCandidate]);

  const refreshSteerQueue = useCallback(async (conversationIdOverride?: string) => {
    const conversationId = conversationIdOverride ?? activeConversationId;
    if (!conversationId) {
      setSteerItems([]);
      return;
    }
    setModelSteerBusy(true);
    try {
      const result = await api.conversationSteer({
        action: "list",
        conversation_id: conversationId,
      });
      const items = "items" in result && Array.isArray(result.items) ? result.items : [];
      setSteerItems(items);
      const queuedCount = items.filter((item) => item.status === "queued").length;
      setModelSteerStatus(queuedCount ? `${queuedCount}件のステアが待機中` : null);
    } catch (steerError) {
      setModelSteerStatus(steerError instanceof Error ? steerError.message : "Steer refresh failed");
    } finally {
      setModelSteerBusy(false);
    }
  }, [activeConversationId]);

  const queueConversationSteer = useCallback(async (promptOverride?: string) => {
    const prompt = String(promptOverride ?? input).trim();
    if (!activeConversationId || !prompt) return;
    setModelSteerBusy(true);
    try {
      await api.conversationSteer({
        action: "enqueue",
        prompt,
        target_type: "conversation",
        target_id: activeConversationId,
        conversation_id: activeConversationId,
        visible: true,
        auto_send: true,
        metadata: {
          source: "composer_steer",
          live: isGenerating || isConversationPending,
        },
      });
      setInput("");
      setModelSteerStatus(isGenerating || isConversationPending ? "ステアを送りました" : "ステアを予約しました");
      await refreshSteerQueue();
    } catch (steerError) {
      setModelSteerStatus(steerError instanceof Error ? steerError.message : "Steer queue failed");
    } finally {
      setModelSteerBusy(false);
    }
  }, [activeConversationId, input, isConversationPending, isGenerating, refreshSteerQueue, setInput]);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshSteerQueue();
  }, [activeConversationId, refreshSteerQueue]);

  const handleComposerExtensionSelect = (item: ComposerExtensionItem) => {
    setActiveSidebarItemId(item.id);
    setSidebarSelectionTick((value) => value + 1);
    toggleSelectedTool(item);
  };

  const toggleSelectedTool = (item: ComposerExtensionItem) => {
    if (disabledToolIdSet.has(item.id)) {
      setError(`${item.label || item.id} は Settings > Tools で OFF です。`);
      return;
    }
    setStoredSelectedToolIds((current) => {
      if (current.includes(item.id)) {
        return current.filter((selectedId) => selectedId !== item.id);
      }
      return [...current, item.id];
    });
  };

  const runFrontendCommandAction = (
    action: string | undefined,
    command: ComposerCommandItem,
    args: Record<string, unknown>,
  ) => {
    switch (action) {
      case "open_model_picker": {
        const query = String(args.query ?? "").trim().toLowerCase();
        setComposerCandidateMenu(null);
        if (!query) {
          setModelPickerRequestId((value) => value + 1);
          return;
        }
        if (query) {
          const profile = selectableModelProfiles.find((item) => commandSearchText({
            id: item.profile_id,
            name: item.profile_id,
            aliases: [item.qualified_model_id ?? "", `${item.provider_id ?? ""}/${item.model_id ?? ""}`],
            label: item.display_name,
            description: item.provider_display_name,
            category: "model",
            visibility: "default",
            risk: "low",
            execution: { type: "frontend", action: "open_model_picker" },
          }).includes(query));
          if (profile) {
            handleModelProfileSelect(profile.profile_id);
          } else {
            setError(`"${query}" に一致する model が見つかりません。`);
          }
        }
        return;
      }
      case "set_fast_mode": {
        const enabled = parseCommandBoolean(args.enabled, true);
        if (!enabled) {
          handleThinkingLevelChange("medium");
          return;
        }
        const candidate = fastCandidateForProfile(activeProfile, selectableModelProfiles);
        if (!candidate) {
          setError("このモデルには fast 対応モデル/プロバイダーがありません。");
          return;
        }
        if (profileIdentity(candidate) !== profileIdentity(activeProfile)) {
          handleModelProfileSelect(candidate.profile_id);
        }
        if (candidate.supports_thinking) {
          const levels = candidate.thinking_levels?.length ? candidate.thinking_levels : ["low", "medium", "high"];
          if (levels.includes("low")) handleThinkingLevelChange("low");
        }
        return;
      }
      case "set_price_mode": {
        const tier = String(args.tier ?? "low").trim().toLowerCase() === "high" ? "high" : "low";
        const candidate = priceCandidateForProfile(activeProfile, selectableModelProfiles, tier);
        if (!candidate) {
          setError(`このモデルには price=${tier} の候補がありません。`);
          return;
        }
        if (profileIdentity(candidate) !== profileIdentity(activeProfile)) {
          handleModelProfileSelect(candidate.profile_id);
        }
        return;
      }
      case "new_conversation":
        handleNewTask();
        return;
      case "clear_composer_state":
        setInput("");
        setAttachedFiles([]);
        setDroppedWidgets([]);
        if (activeConversationId) {
          forgetPendingRequest(activeConversationId);
          replaceChatIdInUrl(activeConversationId, false);
        }
        return;
      case "set_mode_coding":
        handleModeChange(mode === "coding" ? "agent" : "coding");
        return;
      case "set_mode_chat":
        handleModeChange("agent");
        return;
      case "set_mode_agent":
        handleModeChange("agent");
        return;
      case "toggle_yolo":
        setYoloMode((value) => parseCommandBoolean(args.enabled, !value));
        return;
      case "toggle_ultra_yolo": {
        const nextState = resolveUltraYoloModeState(
          {
            yoloMode,
            ultraYoloMode,
            restoreYoloMode: ultraYoloRestoreYoloMode,
          },
          parseCommandBoolean(args.enabled, !ultraYoloMode),
        );
        setYoloMode(nextState.yoloMode);
        setUltraYoloMode(nextState.ultraYoloMode);
        setUltraYoloRestoreYoloMode(nextState.restoreYoloMode);
        return;
      }
      case "open_tool_picker": {
        const query = String(args.query ?? "").trim().toLowerCase();
        if (query) {
          const item = composerExtensions.find((candidate) => (
            `${candidate.id} ${candidate.label} ${candidate.description ?? ""}`.toLowerCase().includes(query)
          ));
          if (item) {
            handleComposerExtensionSelect(item);
          } else {
            setError(`"${query}" に一致する tool が見つかりません。`);
          }
        }
        return;
      }
      case "show_status":
        setError(
          `status: mode=${mode}, model=${activeProfile?.display_name ?? preferredModel}, thinking=${selectedThinkingLevel}, yolo=${yoloMode ? "on" : "off"}, ultra_yolo=${ultraYoloMode ? "on" : "off"}, tools=${selectedTools.length}`,
        );
        return;
      case "open_settings":
      case "open_permissions":
      case "open_theme_settings":
      case "open_keymap_settings":
        if (action === "open_settings" && args.section) {
          const requested = String(args.section).trim().toLowerCase();
          const matchedSection = settingsSections.find((section) => (
            section.id.toLowerCase() === requested
            || section.label.toLowerCase() === requested
          ));
          setRequestedSettingsSectionId(matchedSection?.id ?? requested);
        } else if (action === "open_permissions") {
          setRequestedSettingsSectionId("permissions");
        } else if (action === "open_theme_settings") {
          setRequestedSettingsSectionId("theme");
        } else if (action === "open_keymap_settings") {
          setRequestedSettingsSectionId("keymap");
        }
        setIsSettingsOpen(true);
        return;
      case "open_command_help":
        setError(composerCommands.map((item) => `/${item.name}: ${item.description ?? item.label}`).join("\n"));
        return;
      case "open_diff_preview":
        handleModeChange("coding");
        setInput("Preview the current git diff.");
        return;
      case "start_review":
        handleModeChange("coding");
        setInput("Review the current diff and call out bugs, risks, and missing tests.");
        return;
      case "open_branch_picker":
        handleModeChange("coding");
        if (args.name) setInput(`Create or switch to branch ${String(args.name)}.`);
        return;
      case "prepare_test_run":
        handleModeChange("coding");
        setInput(args.target ? `Run tests for ${String(args.target)}.` : "Run the recommended tests.");
        return;
      case "prepare_lint_run":
        handleModeChange("coding");
        setInput("Run lint and formatting checks.");
        return;
      case "open_file_search":
        handleModeChange("coding");
        if (args.query) setInput(`Find workspace files matching ${String(args.query)}.`);
        return;
      default:
        if (command.risk === "high") {
          setError(`/${command.name} は high risk command のため approval center 経由で実行してください。`);
        }
    }
  };

  const executeComposerCommand = async (commandId: string, rawInput = `/${commandId}`): Promise<boolean | void> => {
    const parsed = parseSlashCommandInput(rawInput, commandCatalog) ?? {
      command: commandCatalog.find((command) => command.id === commandId || command.name === commandId),
      args: {},
      raw: rawInput,
    };
    if (!parsed.command) {
      setError(`/${commandId} は未登録の command です。`);
      return;
    }
    try {
      setError(null);
      const commandArgs = { ...parsed.args };
      if (parsed.command.id === "think" && commandArgs.level && activeProfile) {
        commandArgs.scope = "profile";
        commandArgs.profile_id = profileKey(activeProfile, preferredModel);
      }
      const result = await api.executeUiCommand({
        command: parsed.command.name ?? parsed.command.id,
        args: commandArgs,
        conversation_id: activeConversationId,
        mode: mode as ComposerCommandMode,
      });
      if (result.requires_approval) {
        setError(result.message ?? `/${parsed.command.name} は approval center 経由で実行してください。`);
        return;
      }
      if (isModelCommand(parsed.command)) {
        if (result.action === "show_model_candidates") {
          setComposerCandidateMenu({
            mode: "model",
            query: String(result.args?.query ?? commandArgs.query ?? "").trim(),
            candidates: Array.isArray(result.candidates) ? result.candidates : [],
          });
          if (result.message) setError(result.message);
          return false;
        }
        if (result.action === "open_model_picker") {
          setComposerCandidateMenu(null);
          setModelPickerRequestId((value) => value + 1);
          if (result.message) setError(result.message);
          return true;
        }
        if (result.executed) {
          const selectedProfileId = selectedModelProfileId(result.selected_model);
          setComposerCandidateMenu(null);
          setInput("");
          if (result.message) setError(result.message);
          await refreshCatalog();
          if (activeConversationId && selectedProfileId) {
            const conversation = await api.updateConversation(activeConversationId, { model: selectedProfileId });
            setActiveConversation(conversation);
            await refreshConversations(conversation.id);
          } else if (activeConversationId) {
            await refreshConversations(activeConversationId);
          }
          return true;
        }
      }

      if (result.action || parsed.command.execution.type === "frontend") {
        const frontendAction = parsed.command.execution.type === "frontend" ? parsed.command.execution.action : undefined;
        runFrontendCommandAction(
          result.action ?? frontendAction,
          parsed.command,
          resolvedFrontendCommandArgs(parsed.command, parsed.args, result.args),
        );
      }
      if (parsed.command.execution.type === "rumi_function") {
        await refreshCatalog();
      }
    } catch (commandError) {
      setError(commandError instanceof Error ? commandError.message : "command execution に失敗しました。");
    }
  };

  const handleComposerCommand = (commandId: string, rawInput?: string) => {
    void executeComposerCommand(commandId, rawInput);
  };

  const handleModelCommandCandidateSelect = (candidate: ModelCommandCandidate) => {
    const profileId = modelCandidateProfileId(candidate);
    if (!profileId) {
      setError("Selected model candidate is missing a profile id.");
      return;
    }
    void executeComposerCommand("model", `/model ${profileId}`);
  };

  const handleComposerInputChange = (value: string) => {
    setInput(value);
    if (isGenerating || isConversationPending) {
      setComposerCandidateMenu(null);
      return;
    }
    const modelQuery = modelCommandInputQuery(value);
    if (composerCandidateMenu && modelQuery !== composerCandidateMenu.query) {
      setComposerCandidateMenu(null);
    }
  };

  const handleModeChange = (newMode: AppMode) => {
    setMode(newMode);
    if (newMode === "coding" && window.location.pathname !== "/coding") {
      const url = new URL(window.location.href);
      url.pathname = "/coding";
      window.history.pushState({ mode: "coding", conversationId: activeConversationId }, "", `${url.pathname}${url.search}${url.hash}`);
    } else if (newMode !== "coding" && window.location.pathname === "/coding") {
      const url = new URL(window.location.href);
      url.pathname = "/chat";
      if (activeConversationId) url.searchParams.set("chat", activeConversationId);
      else url.searchParams.delete("chat");
      url.searchParams.delete("pending");
      window.history.pushState({ mode: newMode, conversationId: activeConversationId }, "", `${url.pathname}${url.search}${url.hash}`);
    }
  };

  const handleCodingBranchSwitch = (branch: string, create = false) => {
    void api.switchGitBranch(branch, create, { workspace_id: effectiveWorkspaceId })
      .then(() => loadCodingContext())
      .catch((branchError) => setError(branchError instanceof Error ? branchError.message : "ブランチ切り替えに失敗しました。"));
  };

  const handleCodingDirectoryChange = (directory: string) => {
    setCodingDirectory(directory || ".");
  };

  const handleFileAttach = (files: AttachedFile[]) => {
    setAttachedFiles((prev) => [...prev, ...files]);
  };

  const handleAtFileAttach = (path: string) => {
    if (mode !== "coding") return;
    if (hasWorkspaceAttachment(attachedFiles, path)) return;

    void api.readWorkspaceFile(path, { workspace_id: effectiveWorkspaceId })
      .then((result) => {
        setAttachedFiles((prev) => {
          if (hasWorkspaceAttachment(prev, path)) return prev;
          return [...prev, workspaceFileToAttachment(result.path || path, result.content, result.size)];
        });
      })
      .catch((readError) => {
        setError(readError instanceof Error ? readError.message : "workspace file の添付に失敗しました。");
      });
  };

  const handleCodingWorkspaceSelect = (workspaceId: string) => {
    handleModeChange("coding");
    setSelectedCodingWorkspaceId(workspaceId);
    void api.selectCodingWorkspace(workspaceId)
      .then(() => loadCodingWorkspaces())
      .then(() => loadCodingContext())
      .catch((workspaceError) => setError(workspaceError instanceof Error ? workspaceError.message : "workspace selection failed."));
  };

  const handleCodingWorkspaceTrust = (workspaceId: string) => {
    void api.trustCodingWorkspace(workspaceId)
      .then(() => loadCodingWorkspaces())
      .then(() => loadCodingContext())
      .catch((workspaceError) => setError(workspaceError instanceof Error ? workspaceError.message : "workspace trust failed."));
  };

  const handleCodingWorkspaceCreate = async (rootPathOverride?: string) => {
    const rootPath = rootPathOverride?.trim() || codingContext?.rootFolder;
    if (!rootPath) {
      setError("Current coding context has no workspace root to add.");
      return null;
    }
    try {
      const created = await api.createCodingWorkspace({ root_path: rootPath, trusted: false });
      const selected = await api.selectCodingWorkspace(created.workspace.workspace_id);
      setSelectedCodingWorkspaceId(selected.selected_workspace_id);
      await loadCodingWorkspaces();
      await loadCodingContext();
      return created.workspace;
    } catch (workspaceError) {
      setError(workspaceError instanceof Error ? workspaceError.message : "workspace creation failed.");
      throw workspaceError;
    }
  };

  const handleDirectorySelect = async () => {
    const selected = await api.selectDirectory("New Group の保存先フォルダを選択");
    return selected.cancelled ? null : selected.path;
  };

  const handlePrepareChatGroupStorage = async (rootPath: string) => {
    const prepared = await api.prepareChatGroupStorage(rootPath);
    return {
      rootPath: prepared.root_path,
      rumiDataPath: prepared.rumi_data_path,
    };
  };

  const handleFileRemove = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const handleDropWidget = (widget: DroppedWidget) => {
    setDroppedWidgets((prev) => {
      if (prev.some((w) => w.id === widget.id)) return prev;
      return [...prev, { ...widget, enabled: widget.enabled ?? true }];
    });
    if ((widget.widgetKind === "tool_toggle" || widget.type === "tool") && widget.enabled !== false) {
      const toolId = widget.sourceItemId || widget.id;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) {
        setStoredSelectedToolIds((current) => current.includes(item.id) ? current : [...current, item.id]);
      }
    }
  };

  const handleWidgetToggle = (widgetId: string) => {
    const widget = droppedWidgets.find((candidate) => candidate.id === widgetId);
    if (widget?.widgetKind === "tool_toggle" || widget?.type === "tool") {
      const toolId = widget.sourceItemId || widgetId;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) {
        toggleSelectedTool(item);
        return;
      }
    }
    setDroppedWidgets((prev) => prev.map((w) => (w.id === widgetId ? { ...w, enabled: !w.enabled } : w)));
  };

  const handleToolBatchSet = (toolIds: string[], enabled: boolean) => {
    const validIds = new Set(composerExtensions.map((tool) => tool.id));
    const requestedIds = [...new Set(toolIds.filter((toolId) => validIds.has(toolId)))];
    if (requestedIds.length === 0) return;
    setStoredSelectedToolIds((current) => {
      if (enabled) return [...new Set([...current, ...requestedIds])];
      const requestedIdSet = new Set(requestedIds);
      return current.filter((toolId) => !requestedIdSet.has(toolId));
    });
  };

  const handleComposerEndpointAction = async (widget: DroppedWidget, action: Extract<ComposerWidgetAction, { type: "call_endpoint" }>) => {
    if (!canExecuteComposerEndpointAction(action)) {
      setError("この widget action は安全な /api/ endpoint ではないか、承認が必要なため直接実行できません。");
      return;
    }

    const method = (action.method ?? "GET").toUpperCase();
    const result = await defaultspackApiFetch(action.endpoint, {
      method,
      body: method === "GET" ? undefined : JSON.stringify(action.payload ?? {}),
    }).then((response) => response.json());

    if (action.result_surface === "silent") return;
    pushActionPreview(
      { id: `composer.${widget.id}`, label: widget.label, icon: widget.icon },
      widget.label,
      result,
    );
  };

  const handleWidgetAction = (widget: DroppedWidget) => {
    const action = widget.action;

    if (!action) {
      const target = widget.sourceItemId || widget.id;
      setActiveSidebarItemId(target);
      setSidebarSelectionTick((value) => value + 1);
      return;
    }

    if (action.type === "open_panel") {
      const target = action.target_item_id || widget.sourceItemId || widget.id;
      setActiveSidebarItemId(target);
      setSidebarSelectionTick((value) => value + 1);
      return;
    }

    if (action.type === "toggle_tool") {
      const toolId = action.tool_id || widget.sourceItemId || widget.id;
      const item = composerExtensions.find((candidate) => candidate.id === toolId);
      if (item) toggleSelectedTool(item);
      return;
    }

    if (action.type === "select_model") {
      if (action.profile_id) handleModelProfileSelect(action.profile_id);
      return;
    }

    if (action.type === "call_endpoint") {
      setError(null);
      void handleComposerEndpointAction(widget, action).catch((actionError) => {
        setError(actionError instanceof Error ? actionError.message : "composer widget action に失敗しました。");
      });
    }
  };

  const approveBrowserAction = async () => {
    if (!browserApproval) return;
    if (!activeConversationId) return;
    setError(null);
    setIsGenerating(true);
    const approvalToolIds = selectedToolIds.length
      ? selectedToolIds
      : [browserApproval.toolName].filter(Boolean);
    rememberPendingRequest({
      conversationId: activeConversationId,
      startedAt: Date.now(),
      status: "ユーザー承認をAIへ伝えています",
      toolNames: approvalToolIds,
    });
    try {
      await api.sendMessage(activeConversationId, "ユーザーが許可しました。承認済みの操作を踏まえて続行してください。", {
        tool_choice: "required",
        tool_policy: {
          ...((yoloMode || ultraYoloMode) ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...(disabledToolIds.length ? { disabled_tools: disabledToolIds } : {}),
          ...(approvalToolIds.length ? { selected_tools: approvalToolIds } : {}),
        },
        tools: approvalToolIds.length ? approvalToolIds : undefined,
        metadata: {
          mode: "agent",
          approval_followup: {
            action: browserApproval.action,
            approval_token: browserApproval.token,
            tool_name: browserApproval.toolName,
          },
          runtime_content: browserApprovalRuntimeContent(browserApproval),
          selected_tools: approvalToolIds,
        },
      });
      forgetPendingRequest(activeConversationId);
      replaceChatIdInUrl(activeConversationId, false);
      await loadConversation(activeConversationId, false);
      await refreshConversations(activeConversationId);
    } catch (approvalError) {
      forgetPendingRequest(activeConversationId);
      setError(approvalError instanceof Error ? approvalError.message : "browser/computer の承認に失敗しました。");
    } finally {
      setIsGenerating(false);
    }
  };

  const approveCodingAction = async () => {
    if (!runtimeApproval) return;
    if (!activeConversationId) return;
    if (activeRuntimeApprovalActionRef.current === runtimeApproval.requestId) return;
    activeRuntimeApprovalActionRef.current = runtimeApproval.requestId;
    setError(null);
    setIsGenerating(true);
    rememberPendingRequest({
      conversationId: activeConversationId,
      startedAt: Date.now(),
      status: "承認済みの操作を続行しています",
      toolNames: [runtimeApproval.toolName],
      toolStartedAt: { [runtimeApproval.toolName]: Date.now() },
    });
    try {
      const approvalWorkspace = workspaceContextFromConversation(activeConversation);
      const decision = await api.approveCodingApproval(runtimeApproval.requestId);
      if (!decision.approved) {
        throw new Error(decision.reason || "approval failed");
      }
      setSettledRuntimeApprovalIds((ids) => (
        ids.includes(runtimeApproval.requestId) ? ids : [...ids, runtimeApproval.requestId].slice(-50)
      ));
      await api.sendMessage(activeConversationId, "ユーザーが許可しました。承認済みの操作を続行してください。", {
        tool_choice: "required",
        tool_policy: {
          ...(ultraYoloMode ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...(approvalWorkspace.workspaceId ? { workspace_id: approvalWorkspace.workspaceId } : {}),
          selected_tools: [runtimeApproval.toolName],
        },
        tools: [runtimeApproval.toolName],
        metadata: {
          mode,
          ...(approvalWorkspace.workspaceId ? {
            workspace_id: approvalWorkspace.workspaceId,
            workspace_label: approvalWorkspace.workspaceLabel,
            workspace_root: approvalWorkspace.workspaceRoot,
          } : {}),
          approval_followup: {
            action: runtimeApproval.action,
            operation: runtimeApproval.operation,
            approval_token: decision.token,
            request_id: runtimeApproval.requestId,
            tool_name: runtimeApproval.toolName,
          },
          runtime_content: runtimeApprovalRuntimeContent(runtimeApproval, decision.token),
          selected_tools: [runtimeApproval.toolName],
        },
      });
      forgetPendingRequest(activeConversationId);
      replaceChatIdInUrl(activeConversationId, false);
      await loadConversation(activeConversationId, false);
      await refreshConversations(activeConversationId);
    } catch (approvalError) {
      forgetPendingRequest(activeConversationId);
      setError(approvalError instanceof Error ? approvalError.message : "runtime 承認に失敗しました。");
    } finally {
      activeRuntimeApprovalActionRef.current = null;
      setIsGenerating(false);
    }
  };

  const denyCodingAction = async () => {
    if (!runtimeApproval) return;
    if (!activeConversationId) return;
    if (activeRuntimeApprovalActionRef.current === runtimeApproval.requestId) return;
    activeRuntimeApprovalActionRef.current = runtimeApproval.requestId;
    setError(null);
    try {
      await api.denyCodingApproval(runtimeApproval.requestId, "Denied from chat approval card");
      setSettledRuntimeApprovalIds((ids) => (
        ids.includes(runtimeApproval.requestId) ? ids : [...ids, runtimeApproval.requestId].slice(-50)
      ));
      await loadConversation(activeConversationId, false);
      await refreshConversations(activeConversationId);
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "runtime 承認の拒否に失敗しました。");
    } finally {
      activeRuntimeApprovalActionRef.current = null;
    }
  };

  const pushActionPreview = (action: SidebarAction, title: string, data: unknown) => {
    const preview = previewFromAction(action, title, data);
    setPreviews((current) => [preview, ...current].slice(0, 30));
    setActivePreviewId(preview.id);
    setShowPreview(true);
  };

  const operationsHeartbeatSchedule = () => (
    (operationsStatus?.schedules ?? []).find((schedule) => String(schedule.name ?? "").toLowerCase().includes("heartbeat"))
  );

  const preferredOperationsModel = () => {
    const allowlist = settingList(settingsValues.operations_company?.model_allowlist);
    const manifestAllowlist = operationsStatus?.manifest.model_self_selection?.allowlist ?? [];
    const effectiveAllowlist = allowlist.length ? allowlist : manifestAllowlist;
    if (effectiveAllowlist.includes(preferredModel)) return preferredModel;
    if (effectiveAllowlist.includes("stub/default")) return "stub/default";
    return effectiveAllowlist[0] ?? "stub/default";
  };

  const handleStartOperationsCompany = async () => {
    setOperationsBusy(true);
    setError(null);
    try {
      const status = await api.bootstrapOperationsCompany({
        start_nonstop: true,
        heartbeat_minutes: Math.max(1, Math.min(1440, settingNumber(settingsValues.operations_company?.heartbeat_minutes, 15))),
        model: preferredOperationsModel(),
      });
      setOperationsStatus(status);
      await refreshConversations(status.conversation_id ?? null);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Operations Company の起動に失敗しました。");
    } finally {
      setOperationsBusy(false);
    }
  };

  const handleOpenOperationsChat = async () => {
    if (!operationsStatus?.conversation_id) {
      await handleStartOperationsCompany();
      return;
    }
    setError(null);
    await loadConversation(operationsStatus.conversation_id);
  };

  const handleTriggerOperationsHeartbeat = async () => {
    const heartbeat = operationsHeartbeatSchedule();
    if (!heartbeat?.id) return;
    setOperationsBusy(true);
    setError(null);
    try {
      const result = await api.triggerSchedule(String(heartbeat.id));
      pushActionPreview(
        { id: "operations.heartbeat", label: "Operations Heartbeat", icon: "activity" },
        "operations-heartbeat",
        result,
      );
      await refreshOperationsStatus();
      if (operationsStatus?.conversation_id) {
        await refreshConversations(operationsStatus.conversation_id);
      }
    } catch (heartbeatError) {
      setError(heartbeatError instanceof Error ? heartbeatError.message : "Operations Company heartbeat に失敗しました。");
    } finally {
      setOperationsBusy(false);
    }
  };

  const handlePanelAction = async (item: SidebarItem, action: SidebarAction) => {
    setError(null);
    try {
      let result: unknown;
      if (action.id === "conversation.export") {
        if (!activeConversationId) throw new Error("エクスポートする会話がありません。");
        result = await api.exportConversation(activeConversationId, String(action.payload?.format ?? "markdown"));
      } else if (action.id === "conversation.share") {
        if (!activeConversationId) throw new Error("共有する会話がありません。");
        const exported = await api.exportConversation(activeConversationId, "markdown");
        result = await api.createShare({
          target_type: "conversation",
          target_id: activeConversationId,
          title: activeChatTitle,
          content: exported.content,
          visibility: "local",
        });
      } else if (action.id === "artifacts.list") {
        result = await api.listArtifacts();
      } else if (action.id === "research.web") {
        result = await api.webSearch(String(input || activeChatTitle || "rumi"), false);
      } else if (action.id === "research.reddit") {
        result = await api.redditSearch(String(input || activeChatTitle || "rumi"), false);
      } else if (action.id === "browser.session") {
        result = await api.browserComputer("browser.session", { dry_run: true });
      } else if (action.id === "browser.profiles.list") {
        result = await api.browserComputer("browser.profiles.list", action.payload ?? {});
      } else if (action.id === "browser.profile.create") {
        result = await api.browserComputer("browser.profile.create", action.payload ?? {});
      } else if (action.id === "browser.cookies.list") {
        result = await api.browserComputer("browser.cookies.list", action.payload ?? {});
      } else if (action.id === "browser.profile.clear_cache.dry_run") {
        result = await api.browserComputer("browser.profile.clear_cache", { ...(action.payload ?? {}), dry_run: true });
      } else if (action.id === "browser.profile.clear_cookies.dry_run") {
        result = await api.browserComputer("browser.profile.clear_cookies", { ...(action.payload ?? {}), dry_run: true });
      } else if (action.id === "browser.screenshot.dry_run") {
        result = await api.browserComputer("computer.screenshot", { dry_run: true });
      } else if (action.id === "schedules.list") {
        result = await api.listSchedules();
      } else if (action.id === "channels.list") {
        result = await api.listChannels();
      } else if (action.id === "operations.status") {
        result = await api.getOperationsCompanyStatus();
        setOperationsStatus(result as OperationsCompanyStatus);
      } else if (action.id === "operations.bootstrap") {
        result = await api.bootstrapOperationsCompany({
          start_nonstop: true,
          heartbeat_minutes: Math.max(1, Math.min(1440, settingNumber(settingsValues.operations_company?.heartbeat_minutes, 15))),
          model: preferredOperationsModel(),
        });
        setOperationsStatus(result as OperationsCompanyStatus);
      } else if (action.endpoint) {
        if (!isSafeLocalEndpoint(action.endpoint) || action.requires_approval) {
          throw new Error("この action は安全な /api/ endpoint ではないか、承認が必要なため直接実行できません。");
        }
        result = await defaultspackApiFetch(action.endpoint, { method: action.method ?? "GET" }).then((response) => response.json());
      } else {
        result = { item: item.id, action: action.id, status: "ready" };
      }
      pushActionPreview(action, action.label, result);
      const text = typeof result === "string" ? result : JSON.stringify(result, null, 2);
      void navigator.clipboard?.writeText(text).catch(() => undefined);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "サイドバー操作に失敗しました。");
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if ((!input.trim() && attachedFiles.length === 0) || isGenerating) return;

    const commandInput = parseSlashCommandInput(input, commandCatalog);
    if (commandInput) {
      const shouldClearInput = await executeComposerCommand(commandInput.command.id, commandInput.raw);
      if (shouldClearInput !== false) setInput("");
      return;
    }

    const trimmedInput = input.trim();
    const userText = (trimmedInput.startsWith("//") ? trimmedInput.slice(1) : trimmedInput) || "添付ファイルを確認してください。";
    const submittedAttachments = attachedFiles;
    const wasNewConversation = isNewConversation;
    setIsGenerating(true);
    setError(null);
    if (wasNewConversation) {
      setIsNewChatLaunching(true);
    }
    setInput("");
    setAttachedFiles([]);
    let submittedConversationId: string | null = null;
    const shouldKeepSelectedToolsAfterSend = keepSelectedToolsAfterSend(settingsValues);
    const mentionedToolIds = toolMentionIdsFromText(userText, composerExtensions);
    const mentionedSkillIdsFromText = skillMentionIdsFromText(userText, composerSkills);
    const submittedToolIds = [...new Set([...selectedToolIds, ...mentionedToolIds])];
    const submittedToolIdSet = new Set(submittedToolIds);
    const composerToolById = new Map(composerExtensions.map((item) => [item.id, item]));
    const composerSkillById = new Map(composerSkills.map((item) => [item.id, item]));
    const droppedWidgetToolIds = new Set(droppedWidgets.map((widget) => widget.sourceItemId || widget.id));
    const droppedWidgetSkillIds = new Set(
      droppedWidgets
        .filter((widget) => widget.type === "skill" || widget.widgetKind === "skill_prompt")
        .map((widget) => widget.sourceItemId || widget.id),
    );
    const submittedSkillIds = [...new Set([...Array.from(droppedWidgetSkillIds), ...mentionedSkillIdsFromText])];
    const mentionedToolWidgets = mentionedToolIds
      .map((toolId) => composerToolById.get(toolId))
      .filter((item): item is ComposerExtensionItem => Boolean(item))
      .filter((item) => !droppedWidgetToolIds.has(item.id))
      .map((item) => composerToolMentionWidget(item));
    const mentionedSkillWidgets = mentionedSkillIdsFromText
      .map((skillId) => composerSkillById.get(skillId))
      .filter((item): item is ComposerSkillItem => Boolean(item))
      .filter((item) => !droppedWidgetSkillIds.has(item.id))
      .map((item) => composerSkillMentionWidget(item));
    const submittedDroppedWidgets = [...droppedWidgets, ...mentionedToolWidgets, ...mentionedSkillWidgets];
    const selectedToolLabels = submittedToolIds.map((toolId) => composerToolById.get(toolId)?.label || toolId);
    const activeContextForSubmit = workspaceContextFromConversation(activeConversation);
    const groupIdForSubmit = pendingNewTaskContext?.groupId ?? activeContextForSubmit.groupId;
    const workspaceIdForSubmit = pendingNewTaskContext?.workspaceId
      ?? activeContextForSubmit.workspaceId
      ?? (mode === "coding" ? selectedCodingWorkspaceId : null);
    const workspaceLabelForSubmit = pendingNewTaskContext?.workspaceLabel
      ?? activeContextForSubmit.workspaceLabel
      ?? codingWorkspaces.find((workspace) => workspace.workspace_id === workspaceIdForSubmit)?.label
      ?? null;
    const workspaceRootForSubmit = pendingNewTaskContext?.workspaceRoot
      ?? activeContextForSubmit.workspaceRoot
      ?? codingWorkspaces.find((workspace) => workspace.workspace_id === workspaceIdForSubmit)?.root_path
      ?? null;
    const rumiDataPathForSubmit = pendingNewTaskContext?.rumiDataPath ?? activeContextForSubmit.rumiDataPath ?? null;
    const isCodingWorkspaceSubmit = mode === "coding" || Boolean(workspaceIdForSubmit);

    try {
      let conversation = activeConversation;
      if (!conversation) {
        conversation = await api.createConversation({
          model: preferredModel || "stub/default",
          conversation_kind: isCodingWorkspaceSubmit ? "coding" : null,
          group_id: groupIdForSubmit ?? null,
          tags: isCodingWorkspaceSubmit ? ["coding"] : undefined,
          metadata: {
            ...(groupIdForSubmit ? { group_id: groupIdForSubmit } : {}),
            ...(rumiDataPathForSubmit ? { rumi_data_path: rumiDataPathForSubmit } : {}),
            ...(isCodingWorkspaceSubmit
            ? {
                mode: "coding",
                workspace_id: workspaceIdForSubmit,
                workspace_label: workspaceLabelForSubmit,
                workspace_root: workspaceRootForSubmit,
              }
              : {}),
          },
        });
        setPendingNewTaskContext(null);
        setActiveConversationId(conversation.id);
      }
      const isOperationsMode = isOperationsConversation(conversation);
      submittedConversationId = conversation.id;
      const requestStartedAt = Date.now();
      rememberPendingRequest({
        conversationId: conversation.id,
        startedAt: requestStartedAt,
        status: `${activeProfile?.display_name ?? preferredModel} が思考中`,
        toolNames: [],
        toolStartedAt: {},
      });
      replaceChatIdInUrl(conversation.id, true);

      const title =
        conversation.title === "New Conversation"
          ? deriveConversationTitle(userText)
          : conversation.title;
      const optimisticConversation = {
        ...conversation,
        title,
        updated_at: Date.now(),
        messages: [...conversation.messages, optimisticUserMessage(conversation.id, userText)],
      };
      setActiveConversation(optimisticConversation);
      setConversations((current) => {
        const item = {
          ...optimisticConversation,
          messages: [],
        };
        const withoutCurrent = current.filter((candidate) => candidate.id !== conversation.id);
        return [item, ...withoutCurrent];
      });
      const assistantDraft = optimisticAssistantMessage(conversation.id, preferredModel || "stub/default");
      const abortController = new AbortController();
      currentAbortControllerRef.current = abortController;
      streamingConversationIdRef.current = conversation.id;
      let finalStreamMessageId: string | null = null;
      let finalStreamActivityEvents: ChatActivityEvent[] = [];
      const updateStreamingAssistant = (delta: string) => {
        if (finalStreamMessageId) return;
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          if (!existing) {
            return {
              ...current,
              messages: [
                ...current.messages,
                {
                  ...assistantDraft,
                  content: [{ type: "text", text: delta }],
                  raw_text: delta,
                },
              ],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => {
              if (message.id !== assistantDraft.id) return message;
              const nextText = `${message.raw_text ?? ""}${delta}`;
              return {
                ...message,
                content: [{ type: "text", text: nextText }],
                raw_text: nextText,
              };
            }),
          };
        });
      };
      const updateStreamingThinking = (delta: string) => {
        if (finalStreamMessageId) return;
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const existing = current.messages.find((message) => message.id === assistantDraft.id);
          const nextThinking = (message: ChatMessage) => {
            const metadata = { ...(message.metadata ?? {}) };
            const thinking = metadata.thinking as Record<string, unknown> | undefined;
            metadata.thinking = {
              ...(thinking ?? {}),
              state: "streaming",
              transcript: `${String(thinking?.transcript ?? "")}${delta}`,
            };
            return { ...message, metadata };
          };
          if (!existing) {
            return {
              ...current,
              messages: [...current.messages, nextThinking(assistantDraft)],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => message.id === assistantDraft.id ? nextThinking(message) : message),
          };
        });
      };
      const updateStreamingActivity = (streamEvent: ChatStreamEvent) => {
        if (!isActivityStreamEvent(streamEvent)) return;
        const eventTimestamp = Date.now();
        const activityEvent: ChatActivityEvent = { timestamp: eventTimestamp, ...streamEvent };
        const finalizedMessageIdAtEvent = finalStreamMessageId;
        if (finalizedMessageIdAtEvent) {
          finalStreamActivityEvents = upsertStreamActivityEvent(finalStreamActivityEvents, activityEvent);
        }
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const targetMessageId = finalizedMessageIdAtEvent ?? assistantDraft.id;
          const existing = current.messages.find((message) => message.id === targetMessageId);
          const appendEvent = (message: ChatMessage): ChatMessage => ({
            ...message,
            events: upsertStreamActivityEvent(message.events ?? [], activityEvent),
          });
          if (!existing) {
            if (finalizedMessageIdAtEvent) return current;
            return {
              ...current,
              messages: [...current.messages, appendEvent(assistantDraft)],
            };
          }
          return {
            ...current,
            messages: current.messages.map((message) => message.id === targetMessageId ? appendEvent(message) : message),
          };
        });

        if (activityEvent.phase === "conversation_steer") {
          const processed = Array.isArray(activityEvent.processed)
            ? activityEvent.processed.filter(isConversationSteerItem)
            : [];
          if (processed.length > 0) {
            setSteerItems((current) => {
              const byId = new Map(current.map((item) => [item.id, item]));
              for (const item of processed) byId.set(item.id, item);
              return Array.from(byId.values());
            });
            setModelSteerStatus("ステアを反映しました");
          }
        }

        const status = typeof activityEvent.message === "string" && activityEvent.message.trim()
          ? activityEvent.message.trim()
          : pendingRequests[conversation.id]?.status ?? `${activeProfile?.display_name ?? preferredModel} が思考中`;
        const toolName = typeof activityEvent.tool_name === "string" ? activityEvent.tool_name.trim() : "";
        if (finalizedMessageIdAtEvent) return;
        updatePendingRequests((current) => {
          const existing = current[conversation.id] ?? {
            conversationId: conversation.id,
            startedAt: requestStartedAt,
            status,
            toolNames: [],
            toolStartedAt: {},
          };
          const toolNames = toolName ? [...new Set([...existing.toolNames, toolName])] : existing.toolNames;
          const toolStartedAt = { ...(existing.toolStartedAt ?? {}) };
          if (toolName && toolStartedAt[toolName] === undefined) {
            toolStartedAt[toolName] = eventTimestamp;
          }
          return {
            ...current,
            [conversation.id]: {
              ...existing,
              status,
              toolNames,
              toolStartedAt,
            },
          };
        });
      };
      const replaceStreamingAssistant = (message: ChatMessage) => {
        finalStreamMessageId = message.id;
        const completedAt = Date.now();
        const enhancedMessage: ChatMessage = {
          ...message,
          metadata: {
            ...(message.metadata ?? {}),
            timing: {
              ...((message.metadata?.timing && typeof message.metadata.timing === "object") ? message.metadata.timing as Record<string, unknown> : {}),
              thinking_started_at: requestStartedAt,
              completed_at: completedAt,
              thinking_duration_ms: completedAt - requestStartedAt,
              thinking_duration_label: boundedDurationLabel(requestStartedAt, completedAt),
            },
          },
        };
        setActiveConversation((current) => {
          if (!current || current.id !== conversation.id) return current;
          const withoutDraft = current.messages.filter((candidate) => candidate.id !== assistantDraft.id);
          const existingFinalMessage = withoutDraft.find((candidate) => candidate.id === enhancedMessage.id);
          const baseMergedMessage = mergeStreamingFinalMessage(existingFinalMessage, enhancedMessage);
          const mergedMessage = {
            ...baseMergedMessage,
            events: mergeChatActivityEvents(baseMergedMessage.events, finalStreamActivityEvents),
          };
          return {
            ...current,
            messages: existingFinalMessage
              ? withoutDraft.map((candidate) => candidate.id === enhancedMessage.id ? mergedMessage : candidate)
              : [...withoutDraft, mergedMessage],
          };
        });
        forgetPendingRequest(conversation.id);
        replaceChatIdInUrl(conversation.id, false);
        setIsGenerating(false);
      };

      const operationsModelAllowlist = settingList(settingsValues.operations_company?.model_allowlist);
      const operationsToolDenylist = settingList(settingsValues.operations_company?.tool_denylist);
      const operationsToolAllowlist = operationsStatus?.manifest.tool_policy?.allowlist ?? [];
      const operationsPolicy = isOperationsMode
        ? {
            profile_id: "defaultspack.operations_company",
            non_stop: true,
            allow_shell: false,
            allow_file_write: true,
            write_actions_require_approval: true,
            normal_status_silent: settingsValues.operations_company?.normal_status_silent !== false,
            max_concurrent_children: Math.max(1, Math.min(12, settingNumber(settingsValues.operations_company?.max_concurrent_children, 3))),
            ...(operationsModelAllowlist.length ? { model_allowlist: operationsModelAllowlist } : {}),
            ...(operationsToolAllowlist.length ? { tool_allowlist: operationsToolAllowlist } : {}),
            ...(operationsToolDenylist.length ? { tool_denylist: operationsToolDenylist } : {}),
          }
        : {};
      const shouldSendExplicitToolSelection = submittedToolIds.length > 0;

      await api.streamMessage(conversation.id, userText, {
        thinking_level: activeProfile?.supports_thinking ? selectedThinkingLevel : null,
        tool_choice: submittedToolIds.length > 0 ? "required" : undefined,
        tool_policy: {
          ...(ultraYoloMode ? { yolo_mode: true, allow_shell: true, allow_file_write: true, write_actions_require_approval: false } : {}),
          ...operationsPolicy,
          ...(isCodingWorkspaceSubmit && workspaceIdForSubmit ? { workspace_id: workspaceIdForSubmit } : {}),
          ...(disabledToolIds.length ? { disabled_tools: disabledToolIds } : {}),
          ...(shouldSendExplicitToolSelection ? { selected_tools: submittedToolIds } : {}),
        },
        attachments: submittedAttachments,
        tools: shouldSendExplicitToolSelection ? submittedToolIds : undefined,
        metadata: {
          mode: isOperationsMode ? "operations_company" : isCodingWorkspaceSubmit ? "coding" : mode,
          ...(groupIdForSubmit ? { group_id: groupIdForSubmit } : {}),
          ...(rumiDataPathForSubmit ? { rumi_data_path: rumiDataPathForSubmit } : {}),
          ...(isOperationsMode ? {
            profile_id: "defaultspack.operations_company",
            agent_id: "client_manager",
            conversation_strategy: "one_agent_one_conversation",
            internal_channel: "ops-company",
          } : {}),
          ...(isCodingWorkspaceSubmit ? {
            workspace_id: workspaceIdForSubmit,
            workspace_label: workspaceLabelForSubmit,
            workspace_root: workspaceRootForSubmit,
          } : {}),
          attachments: submittedAttachments.map(({ name, size, type, truncated, source, sourcePath }) => ({ name, size, type, truncated, source, sourcePath })),
          ...(shouldSendExplicitToolSelection ? { selected_tools: submittedToolIds } : {}),
          ...(submittedSkillIds.length ? { skills: submittedSkillIds, skill_mentions: submittedSkillIds.map((skillId) => ({ id: skillId, label: composerSkillById.get(skillId)?.label ?? skillId })) } : {}),
          dropped_widgets: submittedDroppedWidgets
            .filter((widget) => widget.widgetKind === "tool_toggle" || widget.type === "tool" ? submittedToolIdSet.has(widget.sourceItemId || widget.id) : widget.enabled !== false)
            .map(({ id, type, label, widgetKind, sourceItemId, metadata }) => ({ id, type, label, widgetKind, sourceItemId, metadata })),
        },
      }, {
        onEvent: updateStreamingActivity,
        onDelta: updateStreamingAssistant,
        onThinkingDelta: updateStreamingThinking,
        onMessage: replaceStreamingAssistant,
        signal: abortController.signal,
      });
      setAttachedFiles([]);
      setDroppedWidgets([]);
      if (!shouldKeepSelectedToolsAfterSend) {
        setStoredSelectedToolIds([]);
      }
      forgetPendingRequest(conversation.id);
      replaceChatIdInUrl(conversation.id, false);

      if (title !== conversation.title) {
        await api.updateConversation(conversation.id, { title });
      }

      await refreshConversations(conversation.id);
      await refreshSteerQueue(conversation.id).catch(console.error);
    } catch (submitError) {
      console.error("Chat error:", submitError);
      if (isCancelledStreamError(submitError)) {
        if (submittedConversationId) {
          forgetPendingRequest(submittedConversationId);
          replaceChatIdInUrl(submittedConversationId, false);
          await refreshConversations(submittedConversationId).catch(console.error);
        }
        setError(null);
        return;
      }
      if (submittedConversationId && !isUnloadingRef.current && document.visibilityState !== "hidden") {
        forgetPendingRequest(submittedConversationId);
        replaceChatIdInUrl(submittedConversationId, false);
        await refreshConversations(submittedConversationId).catch(console.error);
      }
      setInput(userText);
      setAttachedFiles(submittedAttachments);
      setError(
        submitError instanceof Error
          ? submitError.message
          : "メッセージ送信に失敗しました。",
      );
      setIsNewChatLaunching(false);
    } finally {
      streamingConversationIdRef.current = null;
      currentAbortControllerRef.current = null;
      setIsGenerating(false);
      setIsNewChatLaunching(false);
    }
  };

  const Renderers = useMemo(() => resolveDefaultspackRenderers(catalog), [catalog]);
  const codingSidebarPanel = mode === "coding" ? (
    <CodingCockpit
      variant="sidebar"
      workspaces={codingWorkspaces}
      selectedWorkspaceId={effectiveWorkspaceId}
      consoleScopeKey={effectiveConsoleKey}
      onWorkspaceSelect={handleCodingWorkspaceSelect}
      onWorkspacesRefresh={() => void loadCodingWorkspaces()}
    />
  ) : null;
  const isCalendarMode = workspacePanelMode === "calendar";
  const calendarSettings = parseCalendarSettings(settingsValues.calendar);
  const handleCalendarModeToggle = () => setWorkspacePanelMode((current) => current === "calendar" ? "composer" : "calendar");
  const renderComposer = (isCentered = false) => (
    <Renderers.composer
      input={input}
      placeholder={isCentered ? getNewConversationPlaceholder() : placeholder}
      isNewConversation={isCentered}
      isGenerating={isGenerating || isConversationPending}
      selectedProfile={activeProfile}
      favoriteProfiles={favoriteProfiles}
      modelProfiles={selectableModelProfiles}
      thinkingLevel={activeProfile?.supports_thinking ? selectedThinkingLevel : null}
      contextUsage={contextUsage}
      inlineExtensions={composerExtensions}
      belowExtensions={[]}
      skillExtensions={composerSkills}
      commands={composerCommands}
      modelCommandCandidates={modelCommandCandidates}
      modelPickerRequestId={modelPickerRequestId}
      yoloMode={yoloMode || ultraYoloMode}
      modelStatusIndicators={composerModelStatusIndicators}
      voiceInputEnabled={settingsValues.general?.voice_input_enabled !== false}
      voiceInputUseAi={settingsValues.general?.voice_input_use_ai === true}
      mode={mode}
      codingContext={codingContext}
      codingWorkspaces={codingWorkspaces}
      selectedCodingWorkspaceId={effectiveWorkspaceId}
      attachedFiles={attachedFiles}
      droppedWidgets={droppedWidgets}
      selectedToolIds={selectedToolIds}
      keyboardButtonNavigation={keyboardButtonNavigation}
      steerStatus={modelSteerStatus}
      steerBusy={modelSteerBusy}
      steerQueuedCount={steerItems.filter((item) => item.status === "queued").length}
      steerPreviewItems={isCentered ? [] : activeComposerSteerItems(steerItems, isGenerating || isConversationPending)}
      suppressPopovers={Boolean(visibleBrowserApproval || runtimeApproval || staleRuntimeApprovalNotice)}
      onOpenModelManager={() => openSettingsSection("models")}
      onOpenToolSettings={() => openSettingsSection("tools")}
      onSwitchToVisionModel={handleSwitchToVisionModel}
      onExtensionSelect={handleComposerExtensionSelect}
      onCommandSelect={handleComposerCommand}
      onModelCommandCandidateSelect={handleModelCommandCandidateSelect}
      onModelCommandCandidatesClose={() => setComposerCandidateMenu(null)}
      onModelProfileSelect={handleModelProfileSelect}
      onProviderApiKeySave={handleProviderApiKeySave}
      onThinkingLevelChange={handleThinkingLevelChange}
      onInputChange={handleComposerInputChange}
      onSubmit={handleSubmit}
      onStopGenerating={handleStopGenerating}
      onSteerSubmit={(prompt) => void queueConversationSteer(prompt)}
      onModeChange={handleModeChange}
      onFileAttach={handleFileAttach}
      onAtFileAttach={handleAtFileAttach}
      onFileRemove={handleFileRemove}
      onDropWidget={handleDropWidget}
      onWidgetAction={handleWidgetAction}
      onWidgetToggle={handleWidgetToggle}
      onCodingBranchSwitch={handleCodingBranchSwitch}
      onCodingDirectoryChange={handleCodingDirectoryChange}
      onCodingWorkspaceSelect={handleCodingWorkspaceSelect}
      onCodingWorkspaceTrust={handleCodingWorkspaceTrust}
      onCodingWorkspaceCreate={handleCodingWorkspaceCreate}
      onCodingWorkspacesRefresh={() => void loadCodingWorkspaces()}
      onCodingContextRefresh={loadCodingContext}
    />
  );

  return (
    <RendererBoundary>
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-zinc-800">
      {showRegion("title_bar") && <Renderers.titleBar appName={catalog?.app?.name} appIcon={catalog?.app?.icon} />}

      <div className="flex flex-1 min-h-0">
        {showRegion("history") && !isHistoryMinimized && (
          <div className="w-[286px] max-w-[30vw] min-w-[240px] flex-shrink-0 overflow-hidden border-r border-zinc-800/60 animate-in slide-in-from-left-2 fade-in duration-200 ease-out max-[900px]:w-[260px]">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              codingWorkspaces={codingWorkspaces}
              selectedCodingWorkspaceId={effectiveWorkspaceId}
              onCodingWorkspaceCreate={handleCodingWorkspaceCreate}
              onDirectorySelect={handleDirectorySelect}
              onGroupDataPathPrepare={handlePrepareChatGroupStorage}
              onCodingWorkspacesRefresh={async () => {
                await loadCodingWorkspaces();
              }}
              onCalendarOpen={handleCalendarModeToggle}
              isCalendarActive={isCalendarMode}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onChatMetadataChange={handleHistoryMetadataChange}
              onMinimize={() => setIsHistoryMinimized(true)}
            />
          </div>
        )}

        {showRegion("history") && isHistoryMinimized && (
          <div className="rumi-history-rail w-14 flex-shrink-0 overflow-visible border-r border-zinc-800/60 animate-in slide-in-from-left-1 fade-in duration-150 ease-out">
            <Renderers.historyBoard
              activeChatId={activeConversationId}
              chatItems={chatItems}
              account={catalog?.app?.account}
              onChatSelect={handleHistoryClick}
              onNewTask={handleNewTask}
              codingWorkspaces={codingWorkspaces}
              selectedCodingWorkspaceId={effectiveWorkspaceId}
              onCodingWorkspaceCreate={handleCodingWorkspaceCreate}
              onDirectorySelect={handleDirectorySelect}
              onGroupDataPathPrepare={handlePrepareChatGroupStorage}
              onCodingWorkspacesRefresh={async () => {
                await loadCodingWorkspaces();
              }}
              onCalendarOpen={handleCalendarModeToggle}
              isCalendarActive={isCalendarMode}
              onSettingsClick={() => setIsSettingsOpen(true)}
              onChatMetadataChange={handleHistoryMetadataChange}
              onRestore={() => setIsHistoryMinimized(false)}
              isCompact
            />
          </div>
        )}

        <main
          className={cn("rumi-workspace-main flex-1 flex min-w-0 bg-[#09090b] relative", isActivityPreviewVisible && "has-activity-preview")}
          style={{ "--rumi-activity-preview-width": `${activityPreviewWidthPx}px` } as CSSProperties}
        >
          <div className={cn("rumi-chat-pane flex-1 flex flex-col min-w-0", isActivityPreviewVisible && "border-r border-zinc-800/40")}>
            {showRegion("chat_header") && !isCalendarMode && (
              <Renderers.chatHeader
                title={activeChatTitle}
                showPreview={effectiveShowPreview}
                canShowPreview={showRegion("activity_preview") && canShowCanvas}
                canOpenSettings={showRegion("settings_modal")}
                onTogglePreview={() => {
                  if (canShowCanvas) setShowPreview((value) => !value);
                }}
                onOpenSettings={() => setIsSettingsOpen(true)}
              />
            )}

            {isCalendarMode ? (
              <div className="flex min-h-0 flex-1 p-1.5">
                <CalendarComposerPanel
                  conversationId={activeConversationId}
                  modelId={activeModelId}
                  modelProfiles={selectableModelProfiles}
                  settings={calendarSettings}
                />
              </div>
            ) : isNewConversation && !isLoading ? (
              <div className={cn("rumi-new-chat-stage flex flex-1 items-center justify-center px-5 pb-[10vh]", isNewChatLaunching && "is-launching")}>
                <div className="w-full">
                  <h1 className="rumi-greeting mx-auto mb-7 max-w-[720px] px-4 text-center text-[clamp(24px,3.2vw,44px)] font-medium leading-tight text-zinc-200">
                    {getNewConversationGreeting()}
                  </h1>
                  {renderComposer(true)}
                </div>
              </div>
            ) : (
              <Renderers.chatMessages
                error={error}
                isMessagesRegionVisible={showRegion("chat_messages")}
                isLoading={isLoading}
                isNewConversation={isNewConversation}
                isGenerating={isGenerating || isConversationPending}
                pendingStatus={pendingRequest?.status ?? null}
                pendingToolNames={pendingRequest?.toolNames ?? []}
                pendingStartedAt={pendingRequest?.startedAt ?? null}
                pendingToolStartedAt={pendingRequest?.toolStartedAt ?? {}}
                messages={messages}
                messagesEndRef={messagesEndRef}
                unknownBlockStrategy={unknownBlockStrategy}
                showActivityInMessages={showActivityInMessages}
                showWidgets={showWidgets}
                onSuggestionClick={(text) => setInput(text)}
                onOpenToolPreview={(previewId) => {
                  setActivePreviewId(previewId);
                  setShowPreview(true);
                }}
              />
            )}

            {showRegion("composer") && !isNewConversation && !isCalendarMode && (
              <div className="relative">
                {showRegion("activity_preview") && !effectiveShowPreview && canShowCanvas && (
                  <CanvasPeek
                    previews={canvasPreviews}
                    memo={canvasMemo}
                    activePreviewId={activePreviewId}
                    onOpen={() => setShowPreview(true)}
                  />
                )}
                {visibleBrowserApproval && (
                  <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(520px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-orange-500/30 bg-zinc-950 p-3 shadow-2xl">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">{visibleBrowserApproval.action} の承認が必要です</p>
                        <details className="mt-1 text-[11px] text-zinc-500">
                          <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">payload を表示</summary>
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
                            {JSON.stringify(visibleBrowserApproval.payload, null, 2)}
                          </pre>
                        </details>
                      </div>
                      <button
                        type="button"
                        onClick={approveBrowserAction}
                        className="h-8 flex-shrink-0 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
                      >
                        許可
                      </button>
                    </div>
                  </div>
                )}
                {!visibleBrowserApproval && runtimeApproval && (
                  <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-amber-500/30 bg-zinc-950 p-3 shadow-2xl">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className={cn(
                            "shrink-0 rounded border px-1.5 py-0.5 text-[10px]",
                            runtimeApproval.riskLevel === "high"
                              ? "border-red-500/30 bg-red-500/10 text-red-200"
                              : "border-amber-500/30 bg-amber-500/10 text-amber-200",
                          )}>
                            {runtimeApproval.riskLevel ?? "approval"}
                          </span>
                          <p className="truncate text-sm font-medium text-zinc-100">{runtimeApproval.operation} の承認が必要です</p>
                        </div>
                        {runtimeApproval.summary && (
                          <p className="mt-1 truncate text-[11px] text-zinc-500">{runtimeApproval.summary}</p>
                        )}
                        <details className="mt-1 text-[11px] text-zinc-500">
                          <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">payload を表示</summary>
                          <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
                            {approvalPayloadPreview(runtimeApproval.payload)}
                          </pre>
                        </details>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onPointerDown={(event) => {
                            event.preventDefault();
                            void denyCodingAction();
                          }}
                          onClick={denyCodingAction}
                          className="h-8 rounded-lg border border-zinc-800 px-3 text-xs font-semibold text-zinc-400 hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-200"
                        >
                          拒否
                        </button>
                        <button
                          type="button"
                          onPointerDown={(event) => {
                            event.preventDefault();
                            void approveCodingAction();
                          }}
                          onClick={approveCodingAction}
                          className="h-8 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
                        >
                          許可
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                {!visibleBrowserApproval && !runtimeApproval && staleRuntimeApprovalNotice && (
                  <div className="pointer-events-auto absolute bottom-full left-1/2 rumi-layer-modal mb-2 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-zinc-700 bg-zinc-950 p-3 shadow-2xl">
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="shrink-0 rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-400">
                          expired
                        </span>
                        <p className="truncate text-sm font-medium text-zinc-100">{staleRuntimeApprovalTitle(staleRuntimeApprovalNotice)}</p>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-zinc-500">
                        古い承認カードを検出しました。最新の承認カードが届くと、この画面からそのまま許可できます。
                      </p>
                      <details className="mt-1 text-[11px] text-zinc-500">
                        <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">payload を表示</summary>
                        <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono">
                          {approvalPayloadPreview(staleRuntimeApprovalNotice.payload)}
                        </pre>
                      </details>
                    </div>
                  </div>
                )}
                {renderComposer(false)}
              </div>
            )}
          </div>

          {isActivityPreviewVisible && (
            <div
              role="separator"
              aria-label="Canvas幅を変更"
              title="Canvas幅を変更"
              className="rumi-activity-preview-resize-handle"
              onPointerDown={startActivityPreviewResize}
            />
          )}

          {isActivityPreviewVisible && (
            <aside className="rumi-activity-preview-pane" aria-label="Activity preview">
              <Renderers.toolPreviewPanel
                previews={canvasPreviews}
                showPreview={effectiveShowPreview}
                onClose={() => setShowPreview(false)}
                previewMode={previewMode}
                onModeChange={setPreviewMode}
                activePreviewId={activePreviewId}
                memo={canvasMemo}
                onMemoChange={setCanvasMemo}
              />
            </aside>
          )}
        </main>

        {showRegion("right_sidebar") && (
          <Renderers.rightSidebar
            items={sidebarItems}
            activeItemId={activeSidebarItemId ? `${activeSidebarItemId}:${sidebarSelectionTick}` : null}
            settingsValues={settingsValues}
            settingsSections={settingsSections}
            selectedToolIds={selectedToolIds}
            companyPanel={<CompanyWorkspacePanel />}
            codingPanel={codingSidebarPanel}
            keyboardButtonNavigation={keyboardButtonNavigation}
            selectedProfile={activeProfile}
            toolFilterEntries={toolFilterEntries}
            runtimeCapabilitySnapshot={runtimeCapabilitySnapshot}
            yoloMode={yoloMode}
            onSettingChange={handleSettingChange}
            onOpenSettings={() => setIsSettingsOpen(true)}
            onOpenSettingsSection={openSettingsSection}
            onToggleYolo={() => setYoloMode((value) => !value)}
            onToolToggle={(item) => toggleSelectedTool({
              id: item.id,
              label: item.label,
              category: item.category,
              description: item.description,
              tags: item.tags ?? [],
              ui: item.ui,
            })}
            onToolBatchSet={handleToolBatchSet}
            onPanelAction={handlePanelAction}
          />
        )}
      </div>

      <ConversationSpotlight
        isOpen={isSpotlightOpen}
        query={spotlightQuery}
        filter={spotlightFilter}
        results={visibleSpotlightResults}
        selectedIndex={spotlightSelectedIndex}
        loading={spotlightLoading}
        locale={locale}
        onQueryChange={setSpotlightQuery}
        onFilterChange={setSpotlightFilter}
        onKeyDown={handleSpotlightKeyDown}
        onClose={closeSpotlight}
        onOpenResult={openSpotlightResult}
      />

      {showRegion("settings_modal") && (
        <Renderers.settingsModal
          isOpen={isSettingsOpen}
          activeSectionId={requestedSettingsSectionId}
          catalog={catalog}
          health={health}
          previewsCount={canvasPreviews.length}
          settingsSections={settingsSections}
          settingsValues={settingsValues}
          desktopSystemInfo={desktopSystemInfo}
          locale={locale}
          onClose={() => setIsSettingsOpen(false)}
          onOpenSection={openSettingsSection}
          onSettingChange={handleSettingChange}
        />
      )}
    </div>
    </RendererBoundary>
  );
}
