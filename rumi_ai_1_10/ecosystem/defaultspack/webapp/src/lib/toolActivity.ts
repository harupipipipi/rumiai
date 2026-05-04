import type { ChatActivityEvent, ToolLogEntry } from "./api";

export type ToolActivityStatus = "running" | "completed" | "failed";

export type ToolActivityItem = {
  id: string;
  toolName: string;
  folder: string;
  folderLabel: string;
  input: string;
  title: string;
  detail: string;
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
  if (lowerName.includes("computer")) {
    return pickString(args, ["action", "text", "key"]);
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

function summarizeToolResult(toolName: string, result: unknown): string {
  if (!result || typeof result !== "object") return compact(result, 120);
  const record = result as Record<string, unknown>;
  const data = record.data && typeof record.data === "object" ? record.data as Record<string, unknown> : record;
  const direct = pickString(data, ["summary", "result", "message", "output", "title"]);
  if (direct) return toolName.toLowerCase().includes("calc") ? formatCalculatorResult(direct) : direct;
  if (Array.isArray(data.results)) return `${data.results.length} 件の結果`;
  if (Array.isArray(data.items)) return `${data.items.length} 件の項目`;
  if (Array.isArray(data.files)) return `${data.files.length} 件のファイル`;
  return compact(data, 120);
}

function statusForLog(log: ToolLogEntry): ToolActivityStatus {
  const result = log.result;
  if (result && typeof result === "object" && (result as Record<string, unknown>).status === "error") {
    return "failed";
  }
  return "completed";
}

function eventKey(event: ChatActivityEvent): string {
  const args = event.arguments && typeof event.arguments === "object" ? event.arguments : {};
  return `${event.tool_name ?? "tool"}:${JSON.stringify(args)}`;
}

export function buildToolActivityGroups(
  toolLogs: ToolLogEntry[] = [],
  events: ChatActivityEvent[] = [],
): ToolActivityGroup[] {
  const fromLogs = toolLogs
    .filter((log) => typeof log.tool_name === "string" && log.tool_name.trim())
    .map((log, index): ToolActivityItem => {
      const toolName = String(log.tool_name);
      const args = log.arguments && typeof log.arguments === "object" ? log.arguments as Record<string, unknown> : {};
      const folder = toolFolderFor(toolName);
      const argumentSummary = summarizeToolArguments(toolName, args);
      const resultSummary = summarizeToolResult(toolName, log.result);
      return {
        id: `log-${index}-${toolName}`,
        toolName,
        folder: folder.id,
        folderLabel: folder.label,
        input: argumentSummary,
        title: argumentSummary ? `${folder.label} / ${toolName}: ${argumentSummary}` : `${folder.label} / ${toolName}`,
        detail: resultSummary,
        status: statusForLog(log),
        timestamp: log.timestamp,
      };
    });

  const logKeys = new Set(
    toolLogs.map((log) => `${log.tool_name ?? "tool"}:${JSON.stringify(log.arguments ?? {})}`),
  );
  const runningEvents = events
    .filter((event) => (event.type === "tool_call" || event.phase === "tool_call") && typeof event.tool_name === "string")
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
