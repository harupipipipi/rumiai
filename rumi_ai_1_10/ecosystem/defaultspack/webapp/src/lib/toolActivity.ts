import type { ChatActivityEvent, ToolLogEntry } from "./api";

export type ToolActivityStatus = "running" | "completed" | "failed" | "approval";
export type ApprovalStatusById = Record<string, string>;

export type ToolActivityItem = {
  id: string;
  toolName: string;
  folder: string;
  folderLabel: string;
  input: string;
  title: string;
  detail: string;
  result?: unknown;
  status: ToolActivityStatus;
  timestamp?: number | string;
};

export type ToolActivityGroup = {
  id: string;
  label: string;
  items: ToolActivityItem[];
};

const FOLDER_RULES: Array<[RegExp, string, string]> = [
  [/calculator|calc|math/i, "calculation", "計算"],
  [/web|search/i, "web/search", "Web検索"],
  [/reddit/i, "web/reddit", "Reddit検索"],
  [/browser|computer/i, "browser", "ブラウザ"],
  [/todo|task/i, "planning/todo", "Todo"],
  [/subagent|agent/i, "agent/subagent", "Subagent"],
  [/terminal|shell|exec/i, "coding/terminal", "ターミナル"],
  [/file|read|write|list/i, "coding/files", "ファイル"],
  [/git|branch|commit|diff/i, "coding/git", "Git"],
];

function compact(value: unknown, maxLength = 96): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
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

function compactPath(value: string): string {
  const normalized = value.trim().replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).pop() || normalized;
}

function normalizeComputerAction(action: string, toolName = ""): string {
  const raw = action.trim().toLowerCase() || toolName.trim().toLowerCase();
  return raw.replace(/^computer[._-]/, "").replace(/^computer_use[._-]/, "");
}

function coordinateSummary(args: Record<string, unknown>): string {
  const x = pickString(args, ["x", "left"]);
  const y = pickString(args, ["y", "top"]);
  return x && y ? ` (${x}, ${y})` : "";
}

function summarizeComputerArguments(toolName: string, args: Record<string, unknown>): string {
  const action = normalizeComputerAction(pickString(args, ["action"]), toolName);
  if (action.includes("screenshot")) return "スクリーンショット";
  if (action.includes("zoom") || toolName.toLowerCase().includes("zoom")) return "ズーム";
  if (action.includes("click")) return `クリック${coordinateSummary(args)}`;
  if (action.includes("double")) return `ダブルクリック${coordinateSummary(args)}`;
  if (action.includes("move")) return `移動${coordinateSummary(args)}`;
  if (action.includes("type")) return "テキスト入力";
  if (action.includes("hotkey")) return `ホットキー ${pickString(args, ["keys", "key"])}`.trim();
  if (action.includes("key") || action.includes("press")) return `キー ${pickString(args, ["key", "keys"])}`.trim();
  if (action.includes("scroll")) return "スクロール";
  if (action.includes("clipboard")) return "クリップボード";
  if (action.includes("window")) return "ウィンドウ操作";
  if (action.includes("app")) return "アプリ操作";
  return pickString(args, ["action"]) || "操作";
}

function approvalStatusForRecord(data: Record<string, unknown>, approvalStatuses?: ApprovalStatusById): string {
  const approvalId = pickString(data, ["approval_id", "id"]);
  const centralStatus = approvalId ? approvalStatuses?.[approvalId] : "";
  if (centralStatus) return centralStatus.toLowerCase();
  const explicit = pickString(data, ["approval_status", "approval_state"]);
  if (explicit) return explicit.toLowerCase();
  const generic = pickString(data, ["status"]).toLowerCase();
  if (["pending", "approved", "consumed", "denied", "rejected", "expired"].includes(generic)) return generic;
  return "";
}

function summarizeComputerResult(
  toolName: string,
  data: Record<string, unknown>,
  visualPath: string,
  args?: Record<string, unknown>,
  approvalStatuses?: ApprovalStatusById,
): string {
  const action = normalizeComputerAction(pickString(data, ["action"]) || pickString(args ?? {}, ["action"]), toolName);
  const error = data.error;
  if (data.status === "error") {
    const message = error && typeof error === "object" ? pickString(error as Record<string, unknown>, ["message", "reason"]) : "";
    return message ? `失敗 · ${message}` : "失敗";
  }
  if (data.requires_approval === true || data.approval_required === true) {
    const approvalStatus = approvalStatusForRecord(data, approvalStatuses);
    if (approvalStatus === "approved") return "承認済み · 実行待ち";
    if (approvalStatus === "consumed") return "承認済み · 実行済み";
    if (approvalStatus === "denied" || approvalStatus === "rejected") return "拒否済み";
    if (approvalStatus === "expired") return "承認期限切れ";
    const reason = pickString(data, ["risk_reason", "reason"]);
    return reason ? `承認待ち · ${reason}` : "承認待ち";
  }
  const artifact = visualPath ? ` · ${compactPath(visualPath)}` : "";
  if (action.includes("screenshot")) return `画面を取得${artifact}`;
  if (action.includes("zoom") || toolName.toLowerCase().includes("zoom")) return `ズーム表示${artifact}`;
  if (action.includes("click")) return `クリック位置を記録${artifact}`;
  if (action.includes("double")) return `ダブルクリック位置を記録${artifact}`;
  if (action.includes("move")) return "ポインタを移動";
  if (action.includes("type")) return "テキストを入力";
  if (action.includes("hotkey")) return "ホットキーを送信";
  if (action.includes("key") || action.includes("press")) return "キーを送信";
  if (action.includes("scroll")) return "スクロール";
  if (action.includes("clipboard")) return "クリップボードを更新";
  if (action.includes("window")) return "ウィンドウ操作を実行";
  if (action.includes("app")) return "アプリ操作を実行";
  return "操作を実行";
}

export function toolFolderFor(toolName: string): { id: string; label: string } {
  for (const [pattern, id, label] of FOLDER_RULES) {
    if (pattern.test(toolName)) return { id, label };
  }
  return { id: "tools", label: "Tools" };
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
  if (lowerName.includes("subagent") || lowerName.includes("agent")) {
    return pickString(args, ["task", "title", "prompt"]);
  }
  if (lowerName.includes("browser")) {
    return pickString(args, ["url", "action"]);
  }
  if (lowerName.includes("computer") || lowerName.includes("zoom")) {
    return summarizeComputerArguments(toolName, args);
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

function summarizeToolResult(toolName: string, result: unknown, args?: Record<string, unknown>, approvalStatuses?: ApprovalStatusById): string {
  if (!result || typeof result !== "object") return compact(result, 120);
  const record = result as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : record;
  const widget = data.widget && typeof data.widget === "object" ? data.widget as Record<string, unknown> : data;
  const lowerToolName = toolName.toLowerCase();
  const visualPath = pickString(widget, [
    "click_history_visual_path",
    "visual_path",
    "path",
    "image_path",
    "model_image_path",
  ]) || pickString(data, [
    "click_history_visual_path",
    "visual_path",
    "path",
    "image_path",
    "model_image_path",
  ]);
  if (lowerToolName.includes("computer") || lowerToolName.includes("zoom")) {
    return summarizeComputerResult(toolName, widget, visualPath, args, approvalStatuses);
  }
  const direct = pickString(data, ["summary", "result", "message", "output", "title"]);
  if (direct) return lowerToolName.includes("calc") ? formatCalculatorResult(direct) : direct;
  if (Array.isArray(data.results)) return `${data.results.length} 件の結果`;
  if (Array.isArray(data.items)) return `${data.items.length} 件の項目`;
  if (Array.isArray(data.files)) return `${data.files.length} 件のファイル`;
  return compact(data, 120);
}

function statusForLog(log: ToolLogEntry, approvalStatuses?: ApprovalStatusById): ToolActivityStatus {
  const result = log.result;
  const record = result && typeof result === "object" ? result as Record<string, unknown> : {};
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : record;
  const widget = data.widget && typeof data.widget === "object" ? data.widget as Record<string, unknown> : data;
  if (widget.requires_approval === true || widget.approval_required === true) {
    const approvalStatus = approvalStatusForRecord(widget, approvalStatuses);
    if (approvalStatus === "approved" || approvalStatus === "consumed") return "completed";
    if (approvalStatus === "denied" || approvalStatus === "rejected" || approvalStatus === "expired") return "failed";
    return "approval";
  }
  if (record.status === "error" || data.status === "error" || widget.status === "error") {
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

export function buildToolActivityGroups(
  toolLogs: ToolLogEntry[] = [],
  events: ChatActivityEvent[] = [],
  approvalStatuses?: ApprovalStatusById,
): ToolActivityGroup[] {
  const fromLogs = toolLogs
    .filter((log) => typeof log.tool_name === "string" && log.tool_name.trim())
    .map((log, index): ToolActivityItem => {
      const toolName = String(log.tool_name);
      const args = log.arguments && typeof log.arguments === "object" ? log.arguments as Record<string, unknown> : {};
      const folder = toolFolderFor(toolName);
      const argumentSummary = summarizeToolArguments(toolName, args);
      const resultSummary = summarizeToolResult(toolName, log.result, args, approvalStatuses);
      return {
        id: `log-${index}-${toolName}`,
        toolName,
        folder: folder.id,
        folderLabel: folder.label,
        input: argumentSummary,
        title: argumentSummary ? `${folder.label} / ${toolName}: ${argumentSummary}` : `${folder.label} / ${toolName}`,
        detail: resultSummary,
        result: log.result,
        status: statusForLog(log, approvalStatuses),
        timestamp: log.timestamp,
      };
    });

  const logKeys = new Set(
    toolLogs.map((log) => {
      const id = typeof log.tool_call_id === "string" ? log.tool_call_id.trim() : "";
      return id || `${log.tool_name ?? "tool"}:${JSON.stringify(log.arguments ?? {})}`;
    }),
  );
  const runningEvents = events
    .filter((event) => (
      event.type === "tool_call" ||
      event.type === "tool_call_started" ||
      event.phase === "tool_call" ||
      event.phase === "tool_call_started"
    ) && typeof event.tool_name === "string")
    .filter((event) => !logKeys.has(eventKey(event)))
    .map((event, index): ToolActivityItem => {
      const toolName = String(event.tool_name);
      const args = event.arguments && typeof event.arguments === "object" ? event.arguments as Record<string, unknown> : {};
      const folder = toolFolderFor(toolName);
      const argumentSummary = summarizeToolArguments(toolName, args);
      return {
        id: `event-${index}-${toolName}`,
        toolName,
        folder: folder.id,
        folderLabel: folder.label,
        input: argumentSummary,
        title: argumentSummary ? `${folder.label} / ${toolName}: ${argumentSummary}` : `${folder.label} / ${toolName}`,
        detail: String(event.message ?? "使用中"),
        status: "running",
        timestamp: event.timestamp,
      };
    });

  const byFolder = new Map<string, ToolActivityGroup>();
  for (const item of [...fromLogs, ...runningEvents]) {
    const existing = byFolder.get(item.folder);
    if (existing) {
      existing.items.push(item);
    } else {
      byFolder.set(item.folder, { id: item.folder, label: item.folderLabel, items: [item] });
    }
  }
  return [...byFolder.values()];
}
