export type ScheduledTaskStatus = "active" | "paused" | "completed" | "unknown";
export type ScheduledTaskScheduleType = "interval" | "cron" | "once";
export type ScheduledTaskIntervalUnit = "seconds" | "minutes" | "hours";

export type ScheduledTask = {
  id: string;
  name: string;
  context: string;
  prompt: string;
  status: ScheduledTaskStatus;
  isEnabled: boolean;
  scheduleType: ScheduledTaskScheduleType;
  scheduleConfig: Record<string, unknown>;
  cadenceLabel: string;
  nextRunLabel: string;
  updatedAt: string;
  raw: Record<string, unknown>;
};

export type ScheduledTaskDraft = {
  name: string;
  prompt: string;
  scheduleType: ScheduledTaskScheduleType;
  intervalValue: string;
  intervalUnit: ScheduledTaskIntervalUnit;
  cronExpression: string;
  onceRunAt: string;
  enabled: boolean;
  context: string;
};

export type ScheduledTasksApiClient = {
  updateSchedule(scheduleId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>>;
  pauseSchedule(scheduleId: string): Promise<Record<string, unknown>>;
  resumeSchedule(scheduleId: string): Promise<Record<string, unknown>>;
  deleteSchedule(scheduleId: string): Promise<Record<string, unknown>>;
};

const SCHEDULE_TYPES = new Set(["interval", "cron", "once"]);
const INTERVAL_UNITS = new Set(["seconds", "minutes", "hours"]);

export function isScheduledTaskRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function optionalString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = optionalString(value);
    if (text) return text;
  }
  return "";
}

function nestedRecord(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key];
  return isScheduledTaskRecord(value) ? value : {};
}

function normalizeScheduleStatus(record: Record<string, unknown>): ScheduledTaskStatus {
  const status = optionalString(record.status).toLowerCase();
  if (status === "active" || status === "paused" || status === "completed") return status;
  if (record.enabled === true) return "active";
  if (record.enabled === false) return "paused";
  return "unknown";
}

function scheduleTypeFrom(record: Record<string, unknown>, config: Record<string, unknown>): ScheduledTaskScheduleType {
  const raw = optionalString(record.type || record.schedule_type).toLowerCase();
  if (SCHEDULE_TYPES.has(raw)) return raw as ScheduledTaskScheduleType;
  if (typeof config.expression === "string") return "cron";
  if (typeof config.run_at === "string") return "once";
  return "interval";
}

function intervalUnitFrom(value: unknown): ScheduledTaskIntervalUnit {
  const unit = optionalString(value).toLowerCase();
  return INTERVAL_UNITS.has(unit) ? unit as ScheduledTaskIntervalUnit : "minutes";
}

function intervalUnitLabel(unit: ScheduledTaskIntervalUnit): string {
  if (unit === "seconds") return "秒";
  if (unit === "hours") return "時間";
  return "分";
}

function timeLabel(hour: string, minute: string): string {
  return `${Number(hour)}:${minute.padStart(2, "0")}`;
}

function formatCronCadence(expression: string): string {
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return `Cron ${expression}`;
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const fixedMinute = /^\d{1,2}$/.test(minute);
  const fixedHour = /^\d{1,2}$/.test(hour);
  if (fixedMinute && fixedHour && dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `毎日 ${timeLabel(hour, minute)}`;
  }
  if (fixedMinute && fixedHour && dayOfMonth === "*" && month === "*" && dayOfWeek !== "*") {
    return `毎週 ${timeLabel(hour, minute)}`;
  }
  if (minute.startsWith("*/") && hour === "*" && dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `${minute.slice(2)}分ごと`;
  }
  return `Cron ${expression}`;
}

function formatDateTime(value: unknown): string {
  const text = optionalString(value);
  if (!text) return "";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatScheduledTaskCadence(
  scheduleType: ScheduledTaskScheduleType,
  config: Record<string, unknown>,
): string {
  if (scheduleType === "interval") {
    const value = Number(config.value ?? 0);
    const unit = intervalUnitFrom(config.unit);
    if (Number.isFinite(value) && value > 0) return `${value}${intervalUnitLabel(unit)}ごと`;
    return "間隔指定";
  }
  if (scheduleType === "cron") {
    const expression = optionalString(config.expression);
    return expression ? formatCronCadence(expression) : "Cron";
  }
  const runAt = formatDateTime(config.run_at);
  return runAt ? `1回 ${runAt}` : "1回";
}

function nextRunLabel(record: Record<string, unknown>, status: ScheduledTaskStatus): string {
  const nextRun = firstString(record.next_execution_at, record.next_run_at, record.next_run);
  if (nextRun) return `次回 ${formatDateTime(nextRun)}`;
  if (status === "paused") return "停止中";
  if (status === "completed") return "完了";
  return "次回未定";
}

function promptPreview(prompt: string): string {
  return prompt.split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? "";
}

function contextFrom(record: Record<string, unknown>, task: Record<string, unknown>, metadata: Record<string, unknown>): string {
  const source = optionalString(metadata.source);
  const workspaceRoot = optionalString(metadata.workspace_root || metadata.root_path);
  const workspaceLabel = optionalString(metadata.workspace_label || metadata.workspaceLabel);
  const context = firstString(
    record.context_name,
    record.context,
    task.context_name,
    task.context,
    metadata.context_name,
    metadata.context,
    workspaceLabel,
    workspaceRoot.split("/").filter(Boolean).pop(),
    metadata.conversation_title,
    metadata.chat_title,
  );
  if (context) return context;
  const conversationId = firstString(task.conversation_id, metadata.conversation_id);
  if (conversationId) return `会話 ${conversationId}`;
  if (source) return source === "calendar" ? "Calendar" : source;
  return "ローカル";
}

export function extractScheduleRecords(response: unknown): Record<string, unknown>[] {
  if (Array.isArray(response)) {
    return response.filter(isScheduledTaskRecord);
  }
  if (!isScheduledTaskRecord(response)) return [];
  const data = response.data;
  const root = isScheduledTaskRecord(data) ? data : response;
  const candidates = [root.schedules, root.jobs, root.items, root.results, data];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate.filter(isScheduledTaskRecord);
  }
  return [];
}

export function extractScheduleRecord(response: unknown): Record<string, unknown> {
  if (isScheduledTaskRecord(response)) {
    const data = response.data;
    if (isScheduledTaskRecord(data)) return data;
    return response;
  }
  return {};
}

export function normalizeScheduledTask(record: Record<string, unknown>, index = 0): ScheduledTask {
  const task = nestedRecord(record, "task");
  const metadata = {
    ...nestedRecord(record, "metadata"),
    ...nestedRecord(task, "metadata"),
  };
  const config = isScheduledTaskRecord(record.config)
    ? record.config
    : isScheduledTaskRecord(record.schedule_config)
      ? record.schedule_config
      : {};
  const status = normalizeScheduleStatus(record);
  const scheduleType = scheduleTypeFrom(record, config);
  const prompt = firstString(task.message, task.prompt, record.prompt, record.description);
  const name = firstString(
    record.name,
    record.title,
    task.title,
    metadata.title,
    promptPreview(prompt),
    `予定済みタスク ${index + 1}`,
  );
  const isEnabled = status === "active" || (status === "unknown" && record.enabled !== false);
  return {
    id: firstString(record.id, record.schedule_id, record.job_id, `schedule-${index}`),
    name,
    context: contextFrom(record, task, metadata),
    prompt,
    status,
    isEnabled,
    scheduleType,
    scheduleConfig: { ...config },
    cadenceLabel: formatScheduledTaskCadence(scheduleType, config),
    nextRunLabel: nextRunLabel(record, status),
    updatedAt: firstString(record.updated_at),
    raw: { ...record },
  };
}

export function filterScheduledTasks(tasks: ScheduledTask[], query: string): ScheduledTask[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return tasks;
  return tasks.filter((task) => {
    const haystack = [
      task.id,
      task.name,
      task.context,
      task.prompt,
      task.cadenceLabel,
      task.nextRunLabel,
      task.status,
      task.scheduleType,
    ].join(" ").toLowerCase();
    return terms.every((term) => haystack.includes(term));
  });
}

function localDateTimeInput(value: unknown): string {
  const text = optionalString(value);
  if (!text) return "";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function draftFromScheduledTask(task: ScheduledTask): ScheduledTaskDraft {
  return {
    name: task.name,
    prompt: task.prompt,
    scheduleType: task.scheduleType,
    intervalValue: String(task.scheduleConfig.value ?? "30"),
    intervalUnit: intervalUnitFrom(task.scheduleConfig.unit),
    cronExpression: optionalString(task.scheduleConfig.expression) || "0 9 * * *",
    onceRunAt: localDateTimeInput(task.scheduleConfig.run_at),
    enabled: task.isEnabled,
    context: task.context,
  };
}

function scheduleConfigFromDraft(draft: ScheduledTaskDraft): Record<string, unknown> {
  if (draft.scheduleType === "interval") {
    const value = Number(draft.intervalValue);
    return {
      value: Number.isFinite(value) && value > 0 ? value : 1,
      unit: draft.intervalUnit,
    };
  }
  if (draft.scheduleType === "cron") {
    return { expression: draft.cronExpression.trim() || "0 9 * * *" };
  }
  const date = new Date(draft.onceRunAt);
  return { run_at: Number.isNaN(date.getTime()) ? draft.onceRunAt : date.toISOString() };
}

export function scheduledTaskUpdatePayloadFromDraft(draft: ScheduledTaskDraft): Record<string, unknown> {
  return {
    name: draft.name.trim() || "予定済みタスク",
    schedule_type: draft.scheduleType,
    schedule_config: scheduleConfigFromDraft(draft),
    task: {
      message: draft.prompt,
    },
  };
}

export function scheduledTaskDraftHasChanges(task: ScheduledTask, draft: ScheduledTaskDraft): boolean {
  const original = draftFromScheduledTask(task);
  return JSON.stringify({
    ...original,
    name: original.name.trim(),
    prompt: original.prompt.trimEnd(),
  }) !== JSON.stringify({
    ...draft,
    name: draft.name.trim(),
    prompt: draft.prompt.trimEnd(),
  });
}

export function confirmCloseScheduledTaskEditor(
  hasUnsavedChanges: boolean,
  confirmFn: (message: string) => boolean = (message) => window.confirm(message),
): boolean {
  if (!hasUnsavedChanges) return true;
  return confirmFn("未保存の変更があります。閉じますか？");
}

export async function setScheduledTaskEnabled(
  task: ScheduledTask,
  enabled: boolean,
  apiClient: ScheduledTasksApiClient,
): Promise<ScheduledTask> {
  if (task.isEnabled === enabled) return task;
  const response = enabled
    ? await apiClient.resumeSchedule(task.id)
    : await apiClient.pauseSchedule(task.id);
  return normalizeScheduledTask(extractScheduleRecord(response));
}

export async function saveScheduledTaskEdit(
  task: ScheduledTask,
  draft: ScheduledTaskDraft,
  apiClient: ScheduledTasksApiClient,
): Promise<ScheduledTask> {
  const updated = normalizeScheduledTask(
    extractScheduleRecord(await apiClient.updateSchedule(task.id, scheduledTaskUpdatePayloadFromDraft(draft))),
  );
  if (updated.isEnabled === draft.enabled) return updated;
  return setScheduledTaskEnabled(updated, draft.enabled, apiClient);
}
