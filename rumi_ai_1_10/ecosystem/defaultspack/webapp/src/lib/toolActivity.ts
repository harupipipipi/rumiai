import { conversationArtifactFileUrl, type ChatActivityEvent, type ToolLogEntry } from "./api";
import { boundedDurationLabel, elapsedDurationLabel, formatCompactDuration } from "./duration";

export type ToolActivityStatus = "running" | "completed" | "failed";

export type ToolActivityItem = {
  id: string;
  toolName: string;
  toolCallId?: string;
  folder: string;
  folderLabel: string;
  input: string;
  title: string;
  detail: string;
  durationLabel?: string;
  nextStep?: string;
  status: ToolActivityStatus;
  timestamp?: number | string;
  artifacts?: ToolActivityArtifact[];
  supported: boolean;
  rawJson?: string;
};

export type ToolActivityGroup = {
  id: string;
  label: string;
  items: ToolActivityItem[];
};

export type ToolActivityArtifact = {
  name: string;
  path: string;
  url?: string;
  kind: "image" | "file";
};

const FOLDER_RULES: Array<[RegExp, string, string]> = [
  [/calculator|calc|math/i, "calculation", "計算"],
  [/web|search/i, "web/search", "Web検索"],
  [/reddit/i, "web/reddit", "Reddit検索"],
  [/browser|computer/i, "browser", "ブラウザ"],
  [/todo|task/i, "planning/todo", "Todo"],
  [/delegate|subagent|agent/i, "agent/delegation", "委任"],
  [/terminal|shell|exec/i, "coding/terminal", "ターミナル"],
  [/file|read|write|list/i, "coding/files", "ファイル"],
  [/git|branch|commit|diff/i, "coding/git", "Git"],
];

function compact(value: unknown, maxLength = 96): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function jsonBlock(value: unknown, maxLength = 1600): string {
  let text = "";
  try {
    text = JSON.stringify(value, null, 2);
  } catch {
    text = String(value ?? "");
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function pickString(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return "";
}

export function toolFolderFor(toolName: string): { id: string; label: string } {
  for (const [pattern, id, label] of FOLDER_RULES) {
    if (pattern.test(toolName)) return { id, label };
  }
  return { id: "tools", label: "Tools" };
}

function isSupportedToolActivity(toolName: string, explicitSummary = ""): boolean {
  return toolFolderFor(toolName).id !== "tools" || Boolean(explicitSummary.trim());
}

export function summarizeToolArguments(toolName: string, args?: Record<string, unknown>): string {
  if (!args) return "";
  const lowerName = toolName.toLowerCase();
  if (lowerName.includes("calculator") || lowerName.includes("calc")) {
    const expression = pickString(args, ["expression", "expr", "input", "query"]);
    if (expression) return expression;
    const left = pickString(args, ["a", "left", "x"]);
    const right = pickString(args, ["b", "right", "y"]);
    const op = pickString(args, ["operator", "operation", "op"]);
    if (left && right) return [left, op, right].filter(Boolean).join(" ");
  }
  if (lowerName.includes("search") || lowerName.includes("web") || lowerName.includes("reddit")) {
    return pickString(args, ["query", "q", "search_query", "text", "url"]);
  }
  if (lowerName.includes("file")) {
    return pickString(args, ["path", "filename", "directory", "glob"]);
  }
  if (lowerName.includes("todo")) {
    return pickString(args, ["title", "task", "action", "todo_id"]);
  }
  if (lowerName.includes("subagent") || lowerName.includes("agent") || lowerName.includes("delegate")) {
    return pickString(args, ["task", "title", "prompt"]);
  }
  if (lowerName.includes("browser") || lowerName.includes("computer")) {
    const action = pickString(args, ["action"]);
    const target = pickString(args, ["url", "app", "application", "browser", "name", "title"]);
    const text = pickString(args, ["text", "key"]);
    const x = pickString(args, ["x"]);
    const y = pickString(args, ["y"]);
    const x1 = pickString(args, ["x1", "from_x"]);
    const y1 = pickString(args, ["y1", "from_y"]);
    const x2 = pickString(args, ["x2", "to_x"]);
    const y2 = pickString(args, ["y2", "to_y"]);
    const coords = x && y ? `(${x}, ${y})` : "";
    const dragCoords = x1 && y1 && x2 && y2 ? `(${x1}, ${y1}) -> (${x2}, ${y2})` : "";
    return [action, target, text, dragCoords || coords].filter(Boolean).join(" ");
  }
  if (lowerName.includes("terminal") || lowerName.includes("exec") || lowerName.includes("shell")) {
    return pickString(args, ["command", "cmd"]);
  }
  return compact(args);
}

function formatCalculatorResult(summary: string): string {
  const calculatedMatch = summary.match(/=\s*([-+]?[\d.,]+(?:\.\d+)?)\s*$/);
  if (calculatedMatch) return calculatedMatch[1];
  return summary;
}

function isGenericCompletionSummary(summary: string, toolName: string): boolean {
  const normalized = summary.trim().toLowerCase();
  if (!normalized) return true;
  if (normalized === "completed" || normalized === "complete" || normalized === "done" || normalized === "完了") return true;
  const lowerToolName = toolName.trim().toLowerCase();
  return Boolean(lowerToolName && normalized.startsWith(lowerToolName) && /\b(completed|complete|done)\b/.test(normalized));
}

function summarizeToolResult(toolName: string, result: unknown): string {
  if (!result || typeof result !== "object") {
    const summary = compact(result, 120);
    return isGenericCompletionSummary(summary, toolName) ? "" : summary;
  }
  const record = result as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : record;
  const direct = pickString(data, ["summary", "result", "message", "output", "title"]);
  if (direct) {
    const formatted = toolName.toLowerCase().includes("calc") ? formatCalculatorResult(direct) : direct;
    return isGenericCompletionSummary(formatted, toolName) ? "" : formatted;
  }
  if (Array.isArray(data.results)) return `${data.results.length} 件の結果`;
  if (Array.isArray(data.items)) return `${data.items.length} 件の項目`;
  if (Array.isArray(data.files)) return `${data.files.length} 件のファイル`;
  return compact(data, 120);
}

function explicitToolText(value: Record<string, unknown>): string {
  return pickString(value, ["display_text", "display_summary", "summary", "result_summary"]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).pop() || "artifact";
}

function isImagePath(path: string): boolean {
  return /\.(png|jpe?g|gif|webp|svg)$/i.test(path);
}

function isImageDataUrl(value: string): boolean {
  return /^data:image\/[a-z0-9.+-]+;base64,/i.test(value);
}

function dataUrlName(value: string): string {
  const match = value.match(/^data:image\/([a-z0-9.+-]+);/i);
  const extension = match?.[1]?.replace("jpeg", "jpg").split("+")[0] || "png";
  return `screenshot.${extension}`;
}

function collectArtifacts(value: unknown, conversationId?: string, artifacts: ToolActivityArtifact[] = [], seen = new Set<string>()): ToolActivityArtifact[] {
  if (!isRecord(value)) {
    if (Array.isArray(value)) {
      for (const item of value) collectArtifacts(item, conversationId, artifacts, seen);
    }
    return artifacts;
  }

  const inlineUrl = stringValue(value.data_url) || stringValue(value.dataUrl);
  if (inlineUrl && isImageDataUrl(inlineUrl)) {
    const key = `inline:${inlineUrl.length}:${inlineUrl.slice(0, 96)}`;
    if (!seen.has(key)) {
      seen.add(key);
      artifacts.push({
        name: pickString(value, ["name", "filename", "title"]) || dataUrlName(inlineUrl),
        path: key,
        kind: "image",
        url: inlineUrl,
      });
    }
  }

  const preferredPath = stringValue(value.model_image_path) || stringValue(value.screenshot_path) || stringValue(value.path);
  if (preferredPath) {
    const key = preferredPath;
    if (!seen.has(key)) {
      seen.add(key);
      const kind = isImagePath(preferredPath) ? "image" : "file";
      artifacts.push({
        name: basename(preferredPath),
        path: preferredPath,
        kind,
        url: conversationId ? conversationArtifactFileUrl(conversationId, preferredPath) : undefined,
      });
    }
  }

  for (const [key, item] of Object.entries(value)) {
    if (key === "path" || key === "screenshot_path" || key === "model_image_path" || key === "data_url" || key === "dataUrl") continue;
    if (isRecord(item) || Array.isArray(item)) collectArtifacts(item, conversationId, artifacts, seen);
  }
  return artifacts;
}

function statusForLog(log: ToolLogEntry): ToolActivityStatus {
  const result = log.result;
  if (!isRecord(result)) return "completed";
  const data = isRecord(result.data) ? result.data : result;
  const widget = isRecord(data.widget) ? data.widget : {};
  if (
    result.status === "error" ||
    data.status === "error" ||
    data.is_error === true ||
    widget.is_error === true
  ) {
    return "failed";
  }
  return "completed";
}

function eventKey(event: ChatActivityEvent): string {
  if (typeof event.tool_call_id === "string" && event.tool_call_id.trim()) {
    return event.tool_call_id.trim();
  }
  const args = event.arguments && typeof event.arguments === "object" ? event.arguments : {};
  return `${event.tool_name ?? "tool"}:${JSON.stringify(args)}`;
}

function isToolActivityEvent(event: ChatActivityEvent): boolean {
  return (
    event.type === "tool_call" ||
    event.type === "tool_call_started" ||
    event.type === "tool_call_completed" ||
    event.type === "tool_result" ||
    event.type === "approval_requested" ||
    event.phase === "tool_call" ||
    event.phase === "tool_call_started" ||
    event.phase === "tool_call_completed" ||
    event.phase === "tool_result" ||
    event.phase === "approval_requested"
  );
}

function eventRank(event: ChatActivityEvent): number {
  if (
    event.type === "tool_call_completed" ||
    event.type === "tool_result" ||
    event.phase === "tool_call_completed" ||
    event.phase === "tool_result"
  ) {
    return 2;
  }
  if (event.type === "approval_requested" || event.phase === "approval_requested") return 1;
  return 0;
}

function statusForEvent(event: ChatActivityEvent): ToolActivityStatus {
  if (
    event.type === "tool_call_completed" ||
    event.type === "tool_result" ||
    event.phase === "tool_call_completed" ||
    event.phase === "tool_result"
  ) {
    const result = event.result;
    if (event.is_error === true || (isRecord(result) && statusForLog({ result }) === "failed")) return "failed";
    return "completed";
  }
  return "running";
}

function isStartEvent(event: ChatActivityEvent): boolean {
  return (
    event.type === "tool_call" ||
    event.type === "tool_call_started" ||
    event.phase === "tool_call" ||
    event.phase === "tool_call_started"
  );
}

function isEndEvent(event: ChatActivityEvent): boolean {
  return (
    event.type === "tool_call_completed" ||
    event.type === "tool_result" ||
    event.phase === "tool_call_completed" ||
    event.phase === "tool_result"
  );
}

function mergeActivityEvents(base: ChatActivityEvent, update: ChatActivityEvent): ChatActivityEvent {
  const merged: ChatActivityEvent = { ...base, ...update };
  const baseStartedAt = base.started_at ?? base.startedAt ?? (isStartEvent(base) ? base.timestamp : undefined);
  const updateStartedAt = update.started_at ?? update.startedAt ?? (isStartEvent(update) ? update.timestamp : undefined);
  const baseCompletedAt = base.completed_at ?? base.completedAt ?? (isEndEvent(base) ? base.timestamp : undefined);
  const updateCompletedAt = update.completed_at ?? update.completedAt ?? (isEndEvent(update) ? update.timestamp : undefined);
  const startedAt = baseStartedAt ?? updateStartedAt;
  const completedAt = updateCompletedAt ?? baseCompletedAt;
  if (startedAt !== undefined) merged.started_at = startedAt;
  if (completedAt !== undefined) merged.completed_at = completedAt;
  for (const key of ["arguments", "result", "artifact", "artifacts", "output", "message", "timestamp"]) {
    if (merged[key] === undefined && base[key] !== undefined) {
      merged[key] = base[key];
    }
  }
  return merged;
}

function resultValueForEvent(event: ChatActivityEvent): unknown {
  return event.result ?? event.output ?? event.artifact ?? event.artifacts;
}

function durationLabelFromLog(log: ToolLogEntry): string {
  const result = isRecord(log.result) ? log.result : {};
  const data = isRecord(result.data) ? result.data : result;
  const directMs = Number(data.duration_ms ?? data.elapsed_ms ?? result.duration_ms ?? result.elapsed_ms);
  if (Number.isFinite(directMs) && directMs >= 0) return formatCompactDuration(directMs);
  const seconds = Number(data.duration_seconds ?? data.elapsed_seconds ?? result.duration_seconds ?? result.elapsed_seconds);
  if (Number.isFinite(seconds) && seconds >= 0) return formatCompactDuration(seconds * 1000);
  return boundedDurationLabel(data.started_at ?? result.started_at, data.completed_at ?? data.finished_at ?? result.completed_at ?? result.finished_at);
}

function durationLabelFromEvent(event: ChatActivityEvent, status: ToolActivityStatus, now = Date.now()): string {
  const startedAt = event.started_at ?? event.startedAt ?? (isStartEvent(event) ? event.timestamp : undefined);
  const completedAt = event.completed_at ?? event.completedAt ?? (isEndEvent(event) ? event.timestamp : undefined);
  if (status === "running") return elapsedDurationLabel(startedAt, now);
  return boundedDurationLabel(startedAt, completedAt);
}

function collectEventArtifacts(event: ChatActivityEvent, conversationId?: string): ToolActivityArtifact[] {
  const artifacts: ToolActivityArtifact[] = [];
  const seen = new Set<string>();
  collectArtifacts(event.result, conversationId, artifacts, seen);
  collectArtifacts(event.artifact, conversationId, artifacts, seen);
  collectArtifacts(event.artifacts, conversationId, artifacts, seen);
  collectArtifacts(event.output, conversationId, artifacts, seen);
  return artifacts;
}

export function buildToolActivityGroups(
  toolLogs: ToolLogEntry[] = [],
  events: ChatActivityEvent[] = [],
  options: { conversationId?: string; now?: number } = {},
): ToolActivityGroup[] {
  const items = buildToolActivityItems(toolLogs, events, options);
  const byFolder = new Map<string, ToolActivityGroup>();
  for (const item of items) {
    const existing = byFolder.get(item.folder);
    if (existing) {
      existing.items.push(item);
    } else {
      byFolder.set(item.folder, { id: item.folder, label: item.folderLabel, items: [item] });
    }
  }
  return [...byFolder.values()];
}

export function buildToolActivityItems(
  toolLogs: ToolLogEntry[] = [],
  events: ChatActivityEvent[] = [],
  options: { conversationId?: string; now?: number } = {},
): ToolActivityItem[] {
  const fromLogs = toolLogs
    .filter((log) => typeof log.tool_name === "string" && log.tool_name.trim())
    .map((log, index): ToolActivityItem => {
      const toolName = String(log.tool_name);
      const args = log.arguments && typeof log.arguments === "object" ? log.arguments as Record<string, unknown> : {};
      const folder = toolFolderFor(toolName);
      const argumentSummary = summarizeToolArguments(toolName, args);
      const resultSummary = summarizeToolResult(toolName, log.result);
      const explicitSummary = isRecord(log.result) ? explicitToolText(log.result) : "";
      const supported = isSupportedToolActivity(toolName, explicitSummary);
      return {
        id: `log-${index}-${toolName}`,
        toolName,
        toolCallId: typeof log.tool_call_id === "string" ? log.tool_call_id : undefined,
        folder: folder.id,
        folderLabel: folder.label,
        input: argumentSummary,
        title: argumentSummary ? `${folder.label} / ${toolName}: ${argumentSummary}` : `${folder.label} / ${toolName}`,
        detail: resultSummary,
        durationLabel: durationLabelFromLog(log),
        nextStep: undefined,
        status: statusForLog(log),
        timestamp: log.timestamp,
        artifacts: collectArtifacts(log.result, options.conversationId),
        supported,
        rawJson: supported ? undefined : jsonBlock({ arguments: args, result: log.result }),
      };
    });

  const logKeys = new Set(
    toolLogs.map((log) => {
      const id = typeof log.tool_call_id === "string" ? log.tool_call_id.trim() : "";
      return id || `${log.tool_name ?? "tool"}:${JSON.stringify(log.arguments ?? {})}`;
    }),
  );
  const eventsByKey = new Map<string, ChatActivityEvent>();
  for (const event of events) {
    if (!isToolActivityEvent(event) || typeof event.tool_name !== "string") continue;
    const key = eventKey(event);
    if (logKeys.has(key)) continue;
    const existing = eventsByKey.get(key);
    if (!existing || eventRank(event) >= eventRank(existing)) {
      eventsByKey.set(key, existing ? mergeActivityEvents(existing, event) : event);
    } else {
      eventsByKey.set(key, mergeActivityEvents(event, existing));
    }
  }
  const eventItems = [...eventsByKey.values()]
    .map((event, index): ToolActivityItem => {
      const toolName = String(event.tool_name);
      const args = event.arguments && typeof event.arguments === "object" ? event.arguments as Record<string, unknown> : {};
      const folder = toolFolderFor(toolName);
      const argumentSummary = summarizeToolArguments(toolName, args);
      const status = statusForEvent(event);
      const defaultDetail = status === "running" ? "使用中" : status === "failed" ? "失敗" : "";
      const resultSummary = summarizeToolResult(toolName, resultValueForEvent(event));
      const explicitSummary = explicitToolText(event);
      const eventMessage = pickString(event, ["message"]);
      const fallbackDetail = status === "completed" && isGenericCompletionSummary(eventMessage || defaultDetail, toolName)
        ? ""
        : eventMessage || defaultDetail;
      const supported = isSupportedToolActivity(toolName, explicitSummary);
      return {
        id: `event-${index}-${toolName}`,
        toolName,
        toolCallId: typeof event.tool_call_id === "string" ? event.tool_call_id : undefined,
        folder: folder.id,
        folderLabel: folder.label,
        input: argumentSummary,
        title: argumentSummary ? `${folder.label} / ${toolName}: ${argumentSummary}` : `${folder.label} / ${toolName}`,
        detail: explicitSummary || resultSummary || fallbackDetail,
        durationLabel: durationLabelFromEvent(event, status, options.now),
        nextStep: pickString(event, ["next_step", "nextStep"]),
        status,
        timestamp: event.timestamp,
        artifacts: collectEventArtifacts(event, options.conversationId),
        supported,
        rawJson: supported ? undefined : jsonBlock({ arguments: args, event }),
      };
    });

  return [...fromLogs, ...eventItems].sort((left, right) => {
    const leftTime = Number(left.timestamp ?? 0);
    const rightTime = Number(right.timestamp ?? 0);
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    return 0;
  });
}
