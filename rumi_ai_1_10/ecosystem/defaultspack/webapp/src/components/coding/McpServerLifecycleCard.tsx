import { ChevronDown, PlugZap, RotateCcw, Trash2, Unplug, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { McpServerRecord } from "../../lib/api";
import type { McpLifecycleAction } from "../../features/coding/resources/mcpLifecycleApi";

const SENSITIVE_KEY = /(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key|private[_-]?key|headers?|env)/i;
const SENSITIVE_VALUE = /(?:bearer\s+\S+|\b(?:sk|ghp|github_pat|xox[baprs]|ya29)[-_][A-Za-z0-9_-]{8,}\b|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b)/i;

type McpServerWithConfig = McpServerRecord & {
  config?: Record<string, unknown>;
  transport?: string;
  status?: string;
  tools?: unknown[];
};

export function mcpServerId(server: McpServerRecord): string {
  return String(server.server_id || server.server_name || server.name || "").trim();
}

function sanitizedUrl(value: unknown): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return "";
  try {
    const parsed = new URL(text);
    parsed.username = "";
    parsed.password = "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return SENSITIVE_VALUE.test(text) ? "[redacted]" : text.slice(0, 240);
  }
}

function safeScalar(key: string, value: unknown): string {
  if (SENSITIVE_KEY.test(key)) return "[redacted]";
  if (typeof value === "string") {
    if (SENSITIVE_VALUE.test(value)) return "[redacted]";
    return value.slice(0, 240);
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function safeArgs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 20).map((item) => {
    const text = typeof item === "string" ? item : String(item ?? "");
    return SENSITIVE_VALUE.test(text) ? "[redacted]" : text.slice(0, 160);
  });
}

export type McpServerConfigSummary = {
  transport: string;
  command?: string;
  args?: string[];
  endpoint?: string;
  toolPrefix?: string;
  toolCount: number;
};

export function mcpServerConfigSummary(server: McpServerRecord): McpServerConfigSummary {
  const record = server as McpServerWithConfig;
  const config = record.config && typeof record.config === "object" ? record.config : {};
  const transport = safeScalar("transport", config.transport ?? record.transport) || "stdio";
  const command = safeScalar("command", config.command);
  const args = safeArgs(config.args);
  const endpoint = sanitizedUrl(config.url);
  const toolPrefix = safeScalar("tool_prefix", config.tool_prefix);
  return {
    transport,
    ...(command ? { command } : {}),
    ...(args.length ? { args } : {}),
    ...(endpoint ? { endpoint } : {}),
    ...(toolPrefix ? { toolPrefix } : {}),
    toolCount: Array.isArray(record.tools) ? record.tools.length : 0,
  };
}

function serverState(server: McpServerRecord): string {
  const record = server as McpServerWithConfig;
  if (record.connected) return "connected";
  return String(record.status || "registered");
}

export function McpServerLifecycleCard({
  server,
  busyAction = null,
  onAction,
}: {
  server: McpServerRecord;
  busyAction?: McpLifecycleAction | null;
  onAction: (action: McpLifecycleAction, serverId: string) => void;
}) {
  const [removeConfirmationOpen, setRemoveConfirmationOpen] = useState(false);
  const serverId = mcpServerId(server);
  const summary = useMemo(() => mcpServerConfigSummary(server), [server]);
  const state = serverState(server);
  const busy = busyAction !== null;

  return (
    <article className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <PlugZap size={12} className="shrink-0 text-violet-300" />
            <span className="truncate font-mono text-[11px] text-zinc-200">{serverId || "unnamed MCP server"}</span>
          </div>
          <p className="mt-1 text-[10px] text-zinc-600">
            {state} · {summary.transport} · {summary.toolCount} tools
          </p>
        </div>
        {busyAction && (
          <span role="status" className="shrink-0 text-[10px] text-amber-300">{busyAction}…</span>
        )}
      </div>

      <details className="mt-2 rounded border border-zinc-800/80 bg-black/20 px-2 py-1.5">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-[10px] text-zinc-400">
          <ChevronDown size={10} />
          Inspect sanitized configuration
        </summary>
        <dl className="mt-2 grid grid-cols-[64px_minmax(0,1fr)] gap-x-2 gap-y-1 text-[10px]">
          <dt className="text-zinc-600">Transport</dt><dd className="break-all text-zinc-300">{summary.transport}</dd>
          {summary.command && <><dt className="text-zinc-600">Command</dt><dd className="break-all font-mono text-zinc-300">{summary.command}</dd></>}
          {summary.args && <><dt className="text-zinc-600">Args</dt><dd className="break-all font-mono text-zinc-300">{summary.args.join(" ")}</dd></>}
          {summary.endpoint && <><dt className="text-zinc-600">Endpoint</dt><dd className="break-all font-mono text-zinc-300">{summary.endpoint}</dd></>}
          {summary.toolPrefix && <><dt className="text-zinc-600">Prefix</dt><dd className="break-all font-mono text-zinc-300">{summary.toolPrefix}</dd></>}
        </dl>
        <p className="mt-2 text-[10px] leading-4 text-zinc-600">Environment variables, headers, tokens, cookies, passwords, URL credentials, query strings, and fragments are never shown here.</p>
      </details>

      <div className="mt-2 flex flex-wrap justify-end gap-1">
        <button
          type="button"
          disabled={busy || !serverId}
          onClick={() => onAction("connect", serverId)}
          className="flex h-7 items-center gap-1 rounded border border-violet-500/30 px-2 text-[10px] text-violet-200 hover:bg-violet-500/10 disabled:opacity-40"
          aria-label={`Reconnect ${serverId}`}
        >
          <RotateCcw size={10} />
          Reconnect
        </button>
        {state === "connected" && (
          <button
            type="button"
            disabled={busy || !serverId}
            onClick={() => onAction("disconnect", serverId)}
            className="flex h-7 items-center gap-1 rounded border border-zinc-700 px-2 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
            aria-label={`Disconnect ${serverId}`}
          >
            <Unplug size={10} />
            Disconnect
          </button>
        )}
        {!removeConfirmationOpen ? (
          <button
            type="button"
            disabled={busy || !serverId}
            onClick={() => setRemoveConfirmationOpen(true)}
            className="flex h-7 items-center gap-1 rounded border border-red-500/30 px-2 text-[10px] text-red-200 hover:bg-red-500/10 disabled:opacity-40"
            aria-label={`Remove ${serverId}`}
          >
            <Trash2 size={10} />
            Remove
          </button>
        ) : (
          <div role="group" aria-label={`Confirm removal of ${serverId}`} className="flex flex-wrap items-center justify-end gap-1 rounded border border-red-500/30 bg-red-500/10 p-1">
            <span className="px-1 text-[10px] text-red-100">Remove configuration and tools?</span>
            <button
              type="button"
              disabled={busy}
              onClick={() => setRemoveConfirmationOpen(false)}
              className="flex h-7 items-center gap-1 rounded border border-zinc-700 px-2 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
            >
              <X size={10} />
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setRemoveConfirmationOpen(false);
                onAction("remove", serverId);
              }}
              className="flex h-7 items-center gap-1 rounded border border-red-400/40 bg-red-500/15 px-2 text-[10px] font-medium text-red-100 hover:bg-red-500/25 disabled:opacity-40"
            >
              <Trash2 size={10} />
              Confirm remove
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
