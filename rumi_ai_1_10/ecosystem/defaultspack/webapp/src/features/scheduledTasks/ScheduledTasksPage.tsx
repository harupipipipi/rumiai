import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { AlertCircle, CalendarClock, CheckCircle2, Loader2, Pause, Pencil, Play, RefreshCw, Save, Search, Trash2, X } from "lucide-react";

import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import {
  confirmCloseScheduledTaskEditor,
  draftFromScheduledTask,
  extractScheduleRecords,
  filterScheduledTasks,
  normalizeScheduledTask,
  saveScheduledTaskEdit,
  scheduledTaskDraftHasChanges,
  setScheduledTaskEnabled,
  type ScheduledTask,
  type ScheduledTaskDraft,
  type ScheduledTaskIntervalUnit,
  type ScheduledTasksApiClient,
} from "./scheduledTaskModels";

export type ScheduledTasksPageApiClient = ScheduledTasksApiClient & {
  listSchedules(): Promise<Record<string, unknown>>;
};

const defaultApiClient: ScheduledTasksPageApiClient = {
  listSchedules: () => api.listSchedules(),
  updateSchedule: (scheduleId, payload) => api.updateSchedule(scheduleId, payload),
  pauseSchedule: (scheduleId) => api.pauseSchedule(scheduleId),
  resumeSchedule: (scheduleId) => api.resumeSchedule(scheduleId),
  deleteSchedule: (scheduleId) => api.deleteSchedule(scheduleId),
};

type EditorState = {
  task: ScheduledTask;
  draft: ScheduledTaskDraft;
  error: string | null;
};

type ScheduledTasksPageProps = {
  apiClient?: ScheduledTasksPageApiClient;
  autoLoad?: boolean;
  initialError?: string | null;
  initialTasks?: ScheduledTask[];
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function replaceTask(tasks: ScheduledTask[], nextTask: ScheduledTask): ScheduledTask[] {
  let replaced = false;
  const nextTasks = tasks.map((task) => {
    if (task.id !== nextTask.id) return task;
    replaced = true;
    return nextTask;
  });
  return replaced ? nextTasks : [nextTask, ...nextTasks];
}

function StatusBadge({ task }: { task: ScheduledTask }) {
  return (
    <span
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border",
        task.isEnabled
          ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-300"
          : "border-zinc-700 bg-zinc-900 text-zinc-500",
      )}
      title={task.isEnabled ? "ON" : "OFF"}
      aria-label={task.isEnabled ? "ON" : "OFF"}
    >
      <span className={cn("h-2.5 w-2.5 rounded-full", task.isEnabled ? "bg-emerald-300" : "bg-zinc-600")} />
    </span>
  );
}

function ScheduledTaskRow({
  task,
  busy,
  onToggle,
  onEdit,
  onDelete,
}: {
  task: ScheduledTask;
  busy: boolean;
  onToggle: (task: ScheduledTask, enabled: boolean) => void;
  onEdit: (task: ScheduledTask) => void;
  onDelete: (task: ScheduledTask) => void;
}) {
  return (
    <li
      data-testid={`scheduled-task-row-${task.id}`}
      className="group flex min-w-0 items-center gap-3 border-b border-zinc-800/70 px-4 py-3 transition-colors last:border-b-0 hover:bg-zinc-900/45"
    >
      <StatusBadge task={task} />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-sm font-semibold text-zinc-100">{task.name}</p>
          <span className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold",
            task.isEnabled
              ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
              : "border-zinc-700 bg-zinc-900 text-zinc-500",
          )}>
            {task.isEnabled ? "ON" : "OFF"}
          </span>
        </div>
        <p className="mt-1 truncate text-xs text-zinc-500">{task.context}</p>
        <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-zinc-400">
          <span className="rounded-md border border-zinc-800 bg-zinc-950/70 px-2 py-1">{task.cadenceLabel}</span>
          <span className="rounded-md border border-zinc-800 bg-zinc-950/50 px-2 py-1">{task.nextRunLabel}</span>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          type="button"
          disabled={busy}
          onClick={() => onToggle(task, !task.isEnabled)}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-950 px-2 text-[11px] font-semibold text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:cursor-wait disabled:opacity-60"
          title={task.isEnabled ? "停止" : "再開"}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : task.isEnabled ? <Pause size={13} /> : <Play size={13} />}
          <span>{task.isEnabled ? "停止" : "再開"}</span>
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onEdit(task)}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950 text-zinc-400 transition-colors hover:border-zinc-600 hover:bg-zinc-900 hover:text-zinc-100 disabled:cursor-wait disabled:opacity-60"
          title="プロンプト編集"
          aria-label={`${task.name} のプロンプト編集`}
        >
          <Pencil size={14} />
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDelete(task)}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950 text-zinc-500 transition-colors hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-200 disabled:cursor-wait disabled:opacity-60"
          title="削除"
          aria-label={`${task.name} を削除`}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </li>
  );
}

function ScheduleFields({
  draft,
  onDraftChange,
}: {
  draft: ScheduledTaskDraft;
  onDraftChange: (updates: Partial<ScheduledTaskDraft>) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-[140px_1fr]">
      <label className="space-y-1.5">
        <span className="text-[11px] font-semibold text-zinc-500">種類</span>
        <select
          value={draft.scheduleType}
          onChange={(event) => onDraftChange({ scheduleType: event.target.value as ScheduledTaskDraft["scheduleType"] })}
          className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
        >
          <option value="interval">間隔</option>
          <option value="cron">Cron</option>
          <option value="once">1回</option>
        </select>
      </label>
      {draft.scheduleType === "interval" && (
        <div className="grid grid-cols-[1fr_132px] gap-2">
          <label className="space-y-1.5">
            <span className="text-[11px] font-semibold text-zinc-500">間隔</span>
            <input
              type="number"
              min="1"
              value={draft.intervalValue}
              onChange={(event) => onDraftChange({ intervalValue: event.target.value })}
              className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-[11px] font-semibold text-zinc-500">単位</span>
            <select
              value={draft.intervalUnit}
              onChange={(event) => onDraftChange({ intervalUnit: event.target.value as ScheduledTaskIntervalUnit })}
              className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
            >
              <option value="minutes">分</option>
              <option value="hours">時間</option>
              <option value="seconds">秒</option>
            </select>
          </label>
        </div>
      )}
      {draft.scheduleType === "cron" && (
        <label className="space-y-1.5">
          <span className="text-[11px] font-semibold text-zinc-500">Cron</span>
          <input
            value={draft.cronExpression}
            onChange={(event) => onDraftChange({ cronExpression: event.target.value })}
            className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 font-mono text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
            placeholder="0 9 * * *"
          />
        </label>
      )}
      {draft.scheduleType === "once" && (
        <label className="space-y-1.5">
          <span className="text-[11px] font-semibold text-zinc-500">日時</span>
          <input
            type="datetime-local"
            value={draft.onceRunAt}
            onChange={(event) => onDraftChange({ onceRunAt: event.target.value })}
            className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
          />
        </label>
      )}
    </div>
  );
}

function ScheduledTaskEditDialog({
  editor,
  dirty,
  saving,
  onDraftChange,
  onClose,
  onSave,
}: {
  editor: EditorState;
  dirty: boolean;
  saving: boolean;
  onDraftChange: (updates: Partial<ScheduledTaskDraft>) => void;
  onClose: () => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="fixed inset-0 rumi-layer-modal flex items-center justify-center bg-black/60 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="プロンプト編集">
      <form
        onSubmit={onSave}
        className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-zinc-700 bg-[#111113] shadow-[0_24px_80px_rgba(0,0,0,0.7)]"
      >
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-800 px-4">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-zinc-100">プロンプト編集</h2>
            <p className="truncate text-[11px] text-zinc-500">{editor.task.context}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-900 hover:text-zinc-100"
            title="閉じる"
            aria-label="閉じる"
          >
            <X size={16} />
          </button>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {editor.error && (
            <div role="alert" className="flex items-start gap-2 rounded-md border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-100">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{editor.error}</span>
            </div>
          )}
          <label className="block space-y-1.5">
            <span className="text-[11px] font-semibold text-zinc-500">タスク名</span>
            <input
              value={editor.draft.name}
              onChange={(event) => onDraftChange({ name: event.target.value })}
              className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none transition focus:border-zinc-500"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-[11px] font-semibold text-zinc-500">プロンプト本文</span>
            <textarea
              value={editor.draft.prompt}
              onChange={(event) => onDraftChange({ prompt: event.target.value })}
              className="min-h-40 w-full resize-y rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm leading-6 text-zinc-100 outline-none transition focus:border-zinc-500"
            />
          </label>
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-zinc-500">スケジュール</span>
            <ScheduleFields draft={editor.draft} onDraftChange={onDraftChange} />
          </div>
          <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold text-zinc-500">関連先</span>
              <input
                value={editor.draft.context}
                readOnly
                className="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950/70 px-3 text-sm text-zinc-400"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold text-zinc-500">状態</span>
              <button
                type="button"
                onClick={() => onDraftChange({ enabled: !editor.draft.enabled })}
                className={cn(
                  "flex h-10 w-full items-center justify-between rounded-md border px-3 text-sm font-semibold transition",
                  editor.draft.enabled
                    ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-100"
                    : "border-zinc-700 bg-zinc-950 text-zinc-400",
                )}
              >
                <span>{editor.draft.enabled ? "ON" : "OFF"}</span>
                <span className={cn(
                  "h-5 w-9 rounded-full border p-0.5 transition",
                  editor.draft.enabled ? "border-emerald-300/40 bg-emerald-300/20" : "border-zinc-700 bg-zinc-900",
                )}>
                  <span className={cn(
                    "block h-3.5 w-3.5 rounded-full transition",
                    editor.draft.enabled ? "translate-x-4 bg-emerald-200" : "bg-zinc-600",
                  )} />
                </span>
              </button>
            </label>
          </div>
        </div>
        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-zinc-800 px-4 py-3">
          <span className={cn("text-[11px]", dirty ? "text-amber-300" : "text-zinc-600")}>{dirty ? "未保存" : "保存済み"}</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="h-9 rounded-md border border-zinc-700 bg-zinc-950 px-3 text-sm font-semibold text-zinc-300 transition hover:bg-zinc-900 hover:text-zinc-100"
            >
              閉じる
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-emerald-400/35 bg-emerald-400/15 px-3 text-sm font-semibold text-emerald-100 transition hover:bg-emerald-400/20 disabled:cursor-wait disabled:opacity-60"
            >
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              保存
            </button>
          </div>
        </footer>
      </form>
    </div>
  );
}

export function ScheduledTasksPage({
  apiClient = defaultApiClient,
  autoLoad = true,
  initialError = null,
  initialTasks = [],
}: ScheduledTasksPageProps) {
  const [tasks, setTasks] = useState<ScheduledTask[]>(initialTasks);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(autoLoad);
  const [error, setError] = useState<string | null>(initialError);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);

  const loadSchedules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.listSchedules();
      setTasks(extractScheduleRecords(response).map((record, index) => normalizeScheduledTask(record, index)));
    } catch (loadError) {
      setError(errorMessage(loadError, "予定済みタスクの読み込みに失敗しました。"));
    } finally {
      setLoading(false);
    }
  }, [apiClient]);

  useEffect(() => {
    if (!autoLoad) return;
    void loadSchedules();
  }, [autoLoad, loadSchedules]);

  const filteredTasks = useMemo(() => filterScheduledTasks(tasks, query), [tasks, query]);
  const activeCount = tasks.filter((task) => task.isEnabled).length;
  const dirty = editor ? scheduledTaskDraftHasChanges(editor.task, editor.draft) : false;

  const handleToggle = async (task: ScheduledTask, enabled: boolean) => {
    setBusyTaskId(task.id);
    setError(null);
    try {
      const nextTask = await setScheduledTaskEnabled(task, enabled, apiClient);
      setTasks((current) => replaceTask(current, nextTask));
    } catch (toggleError) {
      setError(errorMessage(toggleError, enabled ? "再開に失敗しました。" : "停止に失敗しました。"));
    } finally {
      setBusyTaskId(null);
    }
  };

  const handleDelete = async (task: ScheduledTask) => {
    if (!window.confirm("この予定済みタスクを完全に削除しますか？")) return;
    setBusyTaskId(task.id);
    setError(null);
    try {
      await apiClient.deleteSchedule(task.id);
      setTasks((current) => current.filter((item) => item.id !== task.id));
    } catch (deleteError) {
      setError(errorMessage(deleteError, "削除に失敗しました。"));
    } finally {
      setBusyTaskId(null);
    }
  };

  const openEditor = (task: ScheduledTask) => {
    setEditor({ task, draft: draftFromScheduledTask(task), error: null });
  };

  const closeEditor = () => {
    if (!editor) return;
    if (!confirmCloseScheduledTaskEditor(dirty)) return;
    setEditor(null);
  };

  const updateDraft = (updates: Partial<ScheduledTaskDraft>) => {
    setEditor((current) => current ? { ...current, draft: { ...current.draft, ...updates }, error: null } : current);
  };

  const saveEditor = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editor) return;
    setSaving(true);
    setEditor((current) => current ? { ...current, error: null } : current);
    try {
      const nextTask = await saveScheduledTaskEdit(editor.task, editor.draft, apiClient);
      setTasks((current) => replaceTask(current, nextTask));
      setEditor(null);
    } catch (saveError) {
      setEditor((current) => current ? { ...current, error: errorMessage(saveError, "保存に失敗しました。") } : current);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section aria-label="予定済み" className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-zinc-800 bg-[#0c0d0f] shadow-[0_20px_60px_rgba(0,0,0,0.32)]">
      <header className="flex shrink-0 flex-col gap-4 border-b border-zinc-800 bg-[#111214] px-5 py-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 bg-zinc-950 text-zinc-300">
              <CalendarClock size={17} />
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold text-zinc-100">予定済み</h1>
              <p className="mt-1 truncate text-sm text-zinc-500">定期的なタスク、リマインダー、モニターを管理</p>
            </div>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <div className="relative min-w-0 flex-1 md:w-72">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="予定済みタスクを検索"
              className="h-10 w-full rounded-md border border-zinc-700 bg-zinc-950 pl-9 pr-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-zinc-500"
            />
          </div>
          <button
            type="button"
            onClick={() => void loadSchedules()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-zinc-950 text-zinc-400 transition hover:border-zinc-500 hover:bg-zinc-900 hover:text-zinc-100"
            title="更新"
            aria-label="更新"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-200">現在</h2>
            <span className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">{filteredTasks.length}</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            <CheckCircle2 size={13} className="text-emerald-300" />
            <span>{activeCount} ON</span>
          </div>
        </div>

        {error && (
          <div role="alert" className="mb-3 flex items-start gap-2 rounded-md border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-100">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-[#101114]">
          {loading && tasks.length === 0 ? (
            <div className="flex h-40 items-center justify-center gap-2 text-sm text-zinc-500">
              <Loader2 size={16} className="animate-spin" />
              読み込み中
            </div>
          ) : filteredTasks.length > 0 ? (
            <ul>
              {filteredTasks.map((task) => (
                <ScheduledTaskRow
                  key={task.id}
                  task={task}
                  busy={busyTaskId === task.id}
                  onToggle={(target, enabled) => void handleToggle(target, enabled)}
                  onEdit={openEditor}
                  onDelete={(target) => void handleDelete(target)}
                />
              ))}
            </ul>
          ) : (
            <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
              該当する予定済みタスクはありません
            </div>
          )}
        </div>
      </div>

      {editor && (
        <ScheduledTaskEditDialog
          editor={editor}
          dirty={dirty}
          saving={saving}
          onDraftChange={updateDraft}
          onClose={closeEditor}
          onSave={(event) => void saveEditor(event)}
        />
      )}
    </section>
  );
}
