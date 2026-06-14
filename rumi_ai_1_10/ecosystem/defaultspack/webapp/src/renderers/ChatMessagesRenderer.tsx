import { AlertTriangle, Check, ChevronRight, Clock, Copy, ExternalLink, Image as ImageIcon, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ArtifactPreviewDialog, type ArtifactPreviewDialogItem } from "../components/ArtifactPreviewDialog";
import { cn } from "../lib/cn";
import { elapsedDurationLabel, formatCompactDuration, timestampMs } from "../lib/duration";
import { buildToolActivityGroups, toolFolderFor, type ToolActivityGroup } from "../lib/toolActivity";
import type { ChatContentBlock } from "../lib/api";
import { chatMessageResources, type BrowserScreenshot } from "../features/chat/resources/chatMessageResources";
import type { ChatMessagesRendererProps } from "./types";

type ImagePreviewDetail = {
  label: string;
  value: string;
};

type ImagePreviewRequest = {
  src: string;
  title: string;
  alt: string;
  subtitle?: string;
  href?: string;
  details?: ImagePreviewDetail[];
};

const LOG_PREVIEW_MIN_CHARS = 1200;
const LOG_PREVIEW_MAX_CHARS = 2200;
const LOG_PREVIEW_HEAD_CHARS = 1300;
const LOG_PREVIEW_TAIL_CHARS = 620;
const AUTHORITY_WAITING_TEXT = "モデル/API の使用許可が必要です。承認後に続行します。";
const AUTHORITY_FOLLOWUP_TEXT = "ユーザーがモデル/API の使用を許可しました。承認済みのリクエストとして続行してください。";
const AUTHORITY_PENDING_TITLE = "承認待ち";
const AUTHORITY_PENDING_DETAIL = "別ウィンドウで承認してください";
const markdownPlugins = [remarkGfm];
const LOG_LIKE_TOKENS = [
  "\\n",
  "\"stdout\"",
  "\"stderr\"",
  "\"exit_code\"",
  "\"classification\"",
  "\"risk_reasons\"",
  "\"cwd\"",
  "approval_required",
  "coding_terminal_exec",
  "subprocess.run",
  "rootdir:",
  "pytest",
  "Traceback",
  "platform ",
];

type CompactLogPreview = {
  omitted: boolean;
  omittedChars: number;
  text: string;
};

type ToolActivityTraySummary = {
  failedCount: number;
  itemCount: number;
  label: string;
  runningCount: number;
};

type MessageToolActivityState = {
  groups: ToolActivityGroup[];
  hasRunningItems: boolean;
  summary: ToolActivityTraySummary;
};

function shortDetail(value: unknown, limit = 420): string {
  let text = "";
  if (typeof value === "string") {
    text = value;
  } else if (typeof value === "number" || typeof value === "boolean") {
    text = String(value);
  } else if (value !== null && value !== undefined) {
    try {
      text = JSON.stringify(value);
    } catch {
      text = String(value);
    }
  }
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > limit ? `${compact.slice(0, limit - 3)}...` : compact;
}

function countNeedle(text: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let index = text.indexOf(needle);
  while (index !== -1) {
    count += 1;
    index = text.indexOf(needle, index + needle.length);
  }
  return count;
}

export function isCompactLogLikeMessageText(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length < LOG_PREVIEW_MIN_CHARS) return false;

  const escapedNewlineCount = countNeedle(trimmed, "\\n");
  const hasVeryLongLine = trimmed.split(/\r?\n/).some((line) => line.length > 260);
  const tokenHits = LOG_LIKE_TOKENS.reduce((count, token) => (
    trimmed.includes(token) ? count + 1 : count
  ), 0);
  const hasToolJsonKeys = /[{,]\s*"(stdout|stderr|exit_code|command|classification|risk_reasons|cwd)"\s*:/.test(trimmed);

  return (
    (escapedNewlineCount >= 4 && tokenHits >= 2)
    || (hasVeryLongLine && tokenHits >= 2)
    || (hasToolJsonKeys && tokenHits >= 2)
  );
}

function normalizeLogPreviewText(text: string): string {
  return text
    .replace(/\\r\\n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "  ")
    .replace(/\\"/g, "\"");
}

export function compactLogPreviewText(text: string, maxChars = LOG_PREVIEW_MAX_CHARS): CompactLogPreview {
  const normalized = normalizeLogPreviewText(text).trim();
  if (normalized.length <= maxChars) {
    return { omitted: false, omittedChars: 0, text: normalized };
  }

  const head = normalized.slice(0, LOG_PREVIEW_HEAD_CHARS).trimEnd();
  const tail = normalized.slice(-LOG_PREVIEW_TAIL_CHARS).trimStart();
  const omittedChars = Math.max(0, normalized.length - head.length - tail.length);
  return {
    omitted: true,
    omittedChars,
    text: `${head}\n\n... ${omittedChars.toLocaleString()} chars omitted from chat view ...\n\n${tail}`,
  };
}

function CompactLogBlock({ text }: { text: string }) {
  const preview = compactLogPreviewText(text);
  return (
    <section className="rumi-log-card" aria-label="省略されたログ">
      <div className="rumi-log-card-header">
        <span className="rumi-log-card-kicker">Terminal log</span>
        <span className="rumi-log-card-meta">
          {preview.omitted ? `${preview.omittedChars.toLocaleString()} chars omitted` : "wrapped"}
        </span>
      </div>
      <pre className="rumi-log-card-body">{preview.text}</pre>
      <div className="rumi-log-card-footer">全文はメッセージのコピーから取得できます。</div>
    </section>
  );
}

function MessageMarkdown({ text }: { text: string }) {
  return isCompactLogLikeMessageText(text)
    ? <CompactLogBlock text={text} />
    : <ReactMarkdown remarkPlugins={markdownPlugins}>{text}</ReactMarkdown>;
}

function imageSizeLabel(size: BrowserScreenshot["image_size"]): string {
  const width = Number(size?.width ?? 0);
  const height = Number(size?.height ?? 0);
  return width > 0 && height > 0 ? `${width} x ${height}` : "";
}

function artifactDialogItemFromImagePreview(image: ImagePreviewRequest | null): ArtifactPreviewDialogItem | null {
  if (!image) return null;
  return {
    kind: "image",
    title: image.title,
    subtitle: image.subtitle,
    href: image.href,
    imageUrl: image.src,
    imageAlt: image.alt,
    details: image.details,
  };
}

function MessageBlock({
  block,
  unknownStrategy,
  onOpenImagePreview,
}: {
  block: ChatContentBlock;
  unknownStrategy: string;
  onOpenImagePreview?: (image: ImagePreviewRequest) => void;
}) {
  const blockType = String(block.type ?? "text");

  if (blockType === "text" || blockType === "markdown") {
    return <MessageMarkdown text={String(block.text ?? "")} />;
  }

  if (blockType === "code") {
    return (
      <pre className="max-w-full overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-900 p-3 font-mono text-[12px] text-zinc-200">
        <code>{String(block.text ?? "")}</code>
      </pre>
    );
  }

  if (blockType === "image" || blockType === "image_url") {
    if (!shouldRenderImageBlockInChat(block)) return null;
    const imageUrl = block.image_url;
    const url = String(
      block.url
      ?? (typeof imageUrl === "object" && imageUrl !== null && "url" in imageUrl ? imageUrl.url : "")
      ?? "",
    );
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-2">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <ImageIcon size={12} />
          <span>{String(block.alt ?? "image")}</span>
        </div>
        {url ? (
          <button
            type="button"
            className="block max-w-full cursor-zoom-in rounded-lg border border-zinc-800 bg-black/30 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
            onClick={() => onOpenImagePreview?.({
              src: url,
              href: url,
              title: String(block.alt ?? "image"),
              alt: String(block.alt ?? "image"),
              details: [
                { label: "type", value: blockType },
                { label: "source", value: shortDetail(url, 180) },
              ],
            })}
          >
            <img src={url} alt={String(block.alt ?? "image")} className="max-h-72 rounded-lg" />
          </button>
        ) : null}
      </div>
    );
  }

  if (unknownStrategy === "hidden") return null;
  if (unknownStrategy === "text") return <p>{JSON.stringify(block)}</p>;
  return (
    <pre className="max-w-full overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-900 p-3 font-mono text-[11px] text-zinc-400">
      {JSON.stringify(block, null, 2)}
    </pre>
  );
}

export function shouldRenderImageBlockInChat(block: ChatContentBlock): boolean {
  return (
    block.show_in_chat === true
    || block.display_in_chat === true
    || block.presentation === "chat"
    || block.intent === "show_to_user"
  );
}

function messageVisibleText(message: ChatMessagesRendererProps["messages"][number]): string {
  const blockText = message.content
    .map((block) => {
      if (String(block.type ?? "text") === "text" || String(block.type ?? "") === "markdown") {
        return String(block.text ?? "");
      }
      return "";
    })
    .join("")
    .trim();
  return blockText || String(message.rawText ?? "").trim();
}

function messageMetadataRecord(message: ChatMessagesRendererProps["messages"][number]): Record<string, unknown> {
  return isRecord(message.metadata) ? message.metadata as Record<string, unknown> : {};
}

function metadataChildRecord(message: ChatMessagesRendererProps["messages"][number], ...keys: string[]): Record<string, unknown> | null {
  const metadata = messageMetadataRecord(message);
  for (const key of keys) {
    const value = metadata[key];
    if (isRecord(value)) return value;
  }
  return null;
}

function isAuthorityPermissionId(value: unknown): boolean {
  return value === "model.invoke" || value === "api_key.use";
}

function authorityWaitingRequestId(message: ChatMessagesRendererProps["messages"][number]): string {
  const pending = metadataChildRecord(message, "pendingAuthorityApproval", "pending_authority_approval");
  const metadataRequestId = String(pending?.request_id ?? pending?.approval_request_id ?? "").trim();
  if (metadataRequestId) return metadataRequestId;

  for (const event of message.events ?? []) {
    if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
    const requestId = String(event.request_id ?? event.approval_request_id ?? "").trim();
    const isAuthority = Boolean(
      event.authority
      || event.approval_kind === "authority"
      || isAuthorityPermissionId(event.permission_id),
    );
    if (isAuthority && requestId) return requestId;
  }
  return "";
}

export function isHiddenAuthorityFollowupMessage(message: ChatMessagesRendererProps["messages"][number]): boolean {
  if (message.role !== "user") return false;
  const followup = metadataChildRecord(message, "authorityFollowup", "authority_followup");
  const chatDisplay = metadataChildRecord(message, "chatDisplay", "chat_display");
  const requestId = String(followup?.request_id ?? followup?.approval_request_id ?? "").trim();
  const hasAuthorityMarker = Boolean(requestId && isAuthorityPermissionId(followup?.permission_id));
  const text = messageVisibleText(message);
  if (chatDisplay?.hidden === true && chatDisplay.reason === "authority_followup" && hasAuthorityMarker) return true;
  return text === AUTHORITY_FOLLOWUP_TEXT && hasAuthorityMarker;
}

export function isAuthorityWaitingMessage(message: ChatMessagesRendererProps["messages"][number]): boolean {
  return (
    message.role === "agent"
    && messageVisibleText(message) === AUTHORITY_WAITING_TEXT
    && Boolean(authorityWaitingRequestId(message) || metadataChildRecord(message, "pendingAuthorityApproval", "pending_authority_approval"))
  );
}

export function isAwaitingStreamFinalMessage(message: ChatMessagesRendererProps["messages"][number]): boolean {
  const thinkingLabel = String(message.metadata?.thinkingLabel ?? "").trim().toLowerCase();
  return thinkingLabel === "streaming" || thinkingLabel === "running";
}

export function visibleChatMessages(messages: ChatMessagesRendererProps["messages"]): ChatMessagesRendererProps["messages"] {
  return messages.filter((message) => !isHiddenAuthorityFollowupMessage(message));
}

export function shouldShowEmptyResponseWarning(
  message: ChatMessagesRendererProps["messages"][number],
  hasToolActivity: boolean,
): boolean {
  return (
    message.role === "agent"
    && !messageVisibleText(message)
    && !hasToolActivity
    && !isAwaitingStreamFinalMessage(message)
  );
}

export function messageCopyText(message: ChatMessagesRendererProps["messages"][number]): string {
  const blockText = message.content
    .map((block) => {
      const blockType = String(block.type ?? "text");
      if (blockType === "text" || blockType === "markdown" || blockType === "code") {
        return String(block.text ?? "");
      }
      if (blockType === "image" || blockType === "image_url") {
        const imageUrl = block.image_url;
        const url = String(
          block.url
          ?? (typeof imageUrl === "object" && imageUrl !== null && "url" in imageUrl ? imageUrl.url : "")
          ?? "",
        );
        return url;
      }
      return "";
    })
    .filter((text) => text.trim().length > 0)
    .join("\n\n")
    .trim();
  return blockText || String(message.rawText ?? "").trim();
}

export function formatMessageTimestamp(value: unknown): string {
  const timestamp = timestampMs(value);
  if (timestamp === null) return "";
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

async function writeClipboardText(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to the textarea fallback for in-app browsers that expose but deny Clipboard API.
  }

  if (typeof document !== "undefined" && document.body) {
    const textarea = document.createElement("textarea");
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    textarea.value = text;
    textarea.setAttribute("readonly", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    activeElement?.focus({ preventScroll: true });
    if (copied) {
      return;
    }
  }

  await chatMessageResources.writeClipboard(text);
}

function MessageActionBar({
  message,
}: {
  message: ChatMessagesRendererProps["messages"][number];
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const text = messageCopyText(message);
  const timestampLabel = formatMessageTimestamp(message.createdAt);
  const actions: Array<{
    id: string;
    label: string;
    icon: typeof Copy;
    run: () => Promise<void> | void;
  }> = [
    {
      id: "copy",
      label: copyState === "failed" ? "コピー失敗" : copyState === "copied" ? "コピー済み" : "コピー",
      icon: copyState === "failed" ? AlertTriangle : copyState === "copied" ? Check : Copy,
      run: async () => {
        if (!text) return;
        try {
          await writeClipboardText(text);
          setCopyState("copied");
        } catch {
          setCopyState("failed");
        }
        window.setTimeout(() => setCopyState("idle"), 1800);
      },
    },
  ];

  return (
    <div className="rumi-message-actions mt-1.5 flex min-h-6 items-center justify-start gap-1 opacity-80 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100">
      {actions.map((action) => {
        const Icon = action.icon;
        return (
          <button
            key={action.id}
            type="button"
            aria-label={action.label}
            title={action.label}
            onClick={() => {
              void action.run();
            }}
            className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-400 transition-colors hover:bg-zinc-800/85 hover:text-zinc-100 focus-visible:bg-zinc-800/85 focus-visible:text-zinc-100 focus-visible:outline-none"
          >
            <Icon
              size={14}
              className={cn(
                copyState === "copied" && "rumi-copy-icon-pop text-emerald-300",
                copyState === "failed" && "rumi-copy-icon-pop text-red-300",
              )}
            />
          </button>
        );
      })}
      {timestampLabel && (
        <span className="ml-1 shrink-0 font-mono text-[10px] leading-none text-zinc-600 opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100">
          {timestampLabel}
        </span>
      )}
    </div>
  );
}

function WidgetCard({ widget }: { widget: Record<string, unknown> }) {
  if (String(widget.kind ?? "") === "conversation_handoff") {
    const title = String(widget.title ?? "移動先");
    const conversationId = String(widget.conversation_id ?? "");
    const urlPath = String(widget.url_path ?? "");
    const deepLink = String(widget.deep_link ?? "");
    const model = typeof widget.model === "string" ? widget.model : "";
    const href = urlPath || deepLink || "#";
    return (
      <div className="mt-2 w-[min(420px,100%)] rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-emerald-300">{title}</div>
            <div className="mt-1 truncate font-mono text-[12px] text-zinc-200">{conversationId}</div>
            {model && <div className="mt-1 truncate text-[11px] text-zinc-500">{model}</div>}
          </div>
          <a
            href={href}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-emerald-400/30 text-emerald-200 transition-colors hover:bg-emerald-400/10 focus-visible:bg-emerald-400/10 focus-visible:outline-none"
            aria-label="移動先を開く"
            title="移動先を開く"
          >
            <ExternalLink size={15} />
          </a>
        </div>
      </div>
    );
  }
  return (
    <details className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3">
      <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-blue-300">
        Widget details
      </summary>
      <pre className="mt-2 max-w-full overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words text-[11px] font-mono text-zinc-200">{JSON.stringify(widget, null, 2)}</pre>
    </details>
  );
}

export function summarizePendingToolNames(toolNames: string[], visibleLimit = 2): { hiddenCount: number; summary: string; totalCount: number; visibleNames: string[] } {
  const uniqueNames = Array.from(new Set(toolNames.map((name) => name.trim()).filter(Boolean)));
  const visibleNames = uniqueNames.slice(0, visibleLimit);
  const hiddenCount = Math.max(0, uniqueNames.length - visibleNames.length);
  const listed = visibleNames.join("、");
  const summary = hiddenCount > 0
    ? `${listed}、その他 ${hiddenCount} 個が見込まれました`
    : listed
      ? `${listed} が見込まれました`
      : "";
  return {
    hiddenCount,
    summary,
    totalCount: uniqueNames.length,
    visibleNames,
  };
}

function compactDurationMs(label: string | undefined): number | null {
  const text = String(label ?? "").trim();
  if (!text) return null;
  const units: Record<string, number> = {
    d: 86_400_000,
    h: 3_600_000,
    m: 60_000,
    s: 1000,
  };
  let total = 0;
  let matched = false;
  for (const match of text.matchAll(/(\d+)\s*([dhms])/g)) {
    matched = true;
    total += Number(match[1]) * units[match[2]];
  }
  return matched ? total : null;
}

export function hasRunningToolActivityGroups(groups: ToolActivityGroup[]): boolean {
  return groups.some((group) => group.items.some((item) => item.status === "running"));
}

function toolActivityDurationLabel(groups: ToolActivityGroup[]): string {
  let firstStart: number | null = null;
  let lastEnd: number | null = null;
  let longestDurationMs = 0;

  for (const item of groups.flatMap((group) => group.items)) {
    const durationMs = compactDurationMs(item.durationLabel);
    if (durationMs !== null) {
      longestDurationMs = Math.max(longestDurationMs, durationMs);
    }
    const end = timestampMs(item.timestamp);
    if (end === null) continue;
    const start = durationMs !== null ? end - durationMs : end;
    firstStart = firstStart === null ? start : Math.min(firstStart, start);
    lastEnd = lastEnd === null ? end : Math.max(lastEnd, end);
  }

  if (firstStart !== null && lastEnd !== null && lastEnd >= firstStart) {
    return formatCompactDuration(lastEnd - firstStart);
  }
  return longestDurationMs > 0 ? formatCompactDuration(longestDurationMs) : "";
}

export function summarizeToolActivityGroups(groups: ToolActivityGroup[]): ToolActivityTraySummary {
  const items = groups.flatMap((group) => group.items);
  const itemCount = items.length;
  const failedCount = items.filter((item) => item.status === "failed").length;
  const runningCount = items.filter((item) => item.status === "running").length;
  const duration = toolActivityDurationLabel(groups);
  const label = duration
    ? `${duration}${runningCount > 0 ? "作業中" : "作業しました"}`
    : runningCount > 0
      ? "toolを実行中"
      : `${itemCount}件のtoolを実行しました`;
  return {
    failedCount,
    itemCount,
    label: failedCount > 0 ? `${label}・${failedCount}件失敗` : label,
    runningCount,
  };
}

function toolActivityStateForMessage(
  message: ChatMessagesRendererProps["messages"][number],
  now?: number,
): MessageToolActivityState | null {
  const staticGroups = buildToolActivityGroups(message.toolLogs ?? [], message.events ?? [], { conversationId: message.conversationId });
  const hasRunningItems = hasRunningToolActivityGroups(staticGroups);
  const groups = hasRunningItems && now !== undefined
    ? buildToolActivityGroups(message.toolLogs ?? [], message.events ?? [], { conversationId: message.conversationId, now })
    : staticGroups;
  if (groups.length === 0) return null;
  return {
    groups,
    hasRunningItems: hasRunningToolActivityGroups(groups),
    summary: summarizeToolActivityGroups(groups),
  };
}

function hasRunningToolActivityMessage(message: ChatMessagesRendererProps["messages"][number]): boolean {
  return hasRunningToolActivityGroups(buildToolActivityGroups(message.toolLogs ?? [], message.events ?? [], { conversationId: message.conversationId }));
}

function activityPhase(status: string | null | undefined, toolNames: string[]): { label: string; detail: string } {
  const text = String(status ?? "").toLowerCase();
  if (text.includes("scheduler") || text.includes("待機")) {
    return { label: "待機中", detail: status || "予定時刻まで待機しています" };
  }
  if (text.includes("handoff") || text.includes("移動")) {
    return { label: "移動準備中", detail: status || "新しい会話を準備しています" };
  }
  if (text.includes("許可しました") || text.includes("承認済み")) {
    return { label: "再開しています", detail: status || "承認済みのリクエストを続行しています" };
  }
  if (toolNames.length > 0 || text.includes("tool") || text.includes("実行")) {
    const summary = summarizePendingToolNames(toolNames).summary;
    return { label: "tool 準備中", detail: summary || status || "tool を確認しています" };
  }
  return { label: "考えています", detail: status || "応答を組み立てています" };
}

function useActivityNow(enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return undefined;
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [enabled]);
  return now;
}

function RumiActivityLoading({
  status,
  toolNames,
  startedAt,
  compact = false,
}: {
  status?: string | null;
  toolNames: string[];
  startedAt?: number | null;
  compact?: boolean;
}) {
  const phase = activityPhase(status, toolNames);
  const now = useActivityNow(Boolean(startedAt));
  const elapsed = startedAt ? elapsedDurationLabel(startedAt, now) : "";
  return (
    <div className={cn("rumi-activity-loading flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/72 px-3 py-2 text-zinc-300", compact ? "w-fit" : "w-[min(440px,calc(100vw-48px))]")}>
      <div className="rumi-loading-bars flex h-5 w-6 items-end gap-1" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-[12px] font-medium text-zinc-200">{phase.label}</span>
          {elapsed && <span className="shrink-0 font-mono text-[10px] leading-none text-zinc-600">{elapsed}</span>}
        </div>
        <div className="truncate text-[11px] text-zinc-500">{phase.detail}</div>
      </div>
    </div>
  );
}

function screenshotPreviewDetails(screenshot: BrowserScreenshot): ImagePreviewDetail[] {
  const details: ImagePreviewDetail[] = [];
  const size = imageSizeLabel(screenshot.image_size);
  if (screenshot.action) details.push({ label: "action", value: screenshot.action });
  if (size) details.push({ label: "image", value: size });
  if (screenshot.tool_name) details.push({ label: "tool", value: screenshot.tool_name });
  if (screenshot.tool_call_id) details.push({ label: "tool_call", value: screenshot.tool_call_id });
  if (screenshot.click_marker || screenshot.marker) details.push({ label: "marker", value: shortDetail(screenshot.click_marker ?? screenshot.marker) });
  if (screenshot.drag_marker) details.push({ label: "drag", value: shortDetail(screenshot.drag_marker) });
  if (screenshot.target_window) details.push({ label: "target", value: shortDetail(screenshot.target_window) });
  return details;
}

function BrowserScreenshotPreview({
  screenshot,
  compact = false,
  onOpenImagePreview,
}: {
  screenshot: BrowserScreenshot;
  compact?: boolean;
  onOpenImagePreview?: (image: ImagePreviewRequest) => void;
}) {
  const marker = screenshot.click_marker ?? screenshot.marker;
  const dragMarker = screenshot.drag_marker;
  const imageWidth = Number(screenshot.image_size?.width ?? 0);
  const imageHeight = Number(screenshot.image_size?.height ?? 0);
  const markerX = Number(marker?.x ?? NaN);
  const markerY = Number(marker?.y ?? NaN);
  const dragFromX = Number(dragMarker?.from?.x ?? NaN);
  const dragFromY = Number(dragMarker?.from?.y ?? NaN);
  const dragToX = Number(dragMarker?.to?.x ?? NaN);
  const dragToY = Number(dragMarker?.to?.y ?? NaN);
  const canPlaceMarker = Number.isFinite(markerX) && Number.isFinite(markerY) && imageWidth > 0 && imageHeight > 0;
  const canPlaceDrag =
    Number.isFinite(dragFromX) &&
    Number.isFinite(dragFromY) &&
    Number.isFinite(dragToX) &&
    Number.isFinite(dragToY) &&
    imageWidth > 0 &&
    imageHeight > 0;
  const screenshotLabel =
    screenshot.action === "computer.drag"
      ? "ドラッグ位置つきスクリーンショット"
      : screenshot.action === "computer.click"
        ? "クリック位置つきスクリーンショット"
        : "スクリーンショット";
  const openPreview = () => onOpenImagePreview?.({
    src: screenshot.data_url,
    href: screenshot.data_url,
    title: screenshotLabel,
    alt: screenshot.action === "computer.drag" ? "Dragged screen" : screenshot.action === "computer.click" ? "Clicked screen" : "Screen capture",
    subtitle: screenshot.action,
    details: screenshotPreviewDetails(screenshot),
  });

  return (
    <figure className={cn("max-w-full overflow-hidden rounded-lg border border-zinc-800 bg-black/30", compact ? "w-[min(34rem,100%)]" : "w-[min(48rem,100%)]")}>
      <button
        type="button"
        className="relative block max-w-full cursor-zoom-in align-top focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
        onClick={openPreview}
      >
        <img
          src={screenshot.data_url}
          alt={screenshot.action === "computer.drag" ? "Dragged screen" : screenshot.action === "computer.click" ? "Clicked screen" : "Screen capture"}
          className="block h-auto w-full object-contain"
          style={{ maxHeight: compact ? "min(220px, 30vh)" : "min(360px, 45vh)" }}
        />
        {canPlaceDrag && (
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox={`0 0 ${imageWidth} ${imageHeight}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <line
              x1={dragFromX}
              y1={dragFromY}
              x2={dragToX}
              y2={dragToY}
              stroke="rgba(248, 113, 113, 0.95)"
              strokeWidth={Math.max(3, imageWidth / 180)}
              strokeLinecap="round"
            />
            <circle cx={dragFromX} cy={dragFromY} r={Math.max(6, imageWidth / 120)} fill="rgba(251, 191, 36, 0.85)" />
            <circle cx={dragToX} cy={dragToY} r={Math.max(7, imageWidth / 110)} fill="rgba(248, 113, 113, 0.9)" />
          </svg>
        )}
        {canPlaceMarker && !canPlaceDrag && (
          <span
            className="pointer-events-none absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-red-300 bg-red-500/25 shadow-[0_0_0_4px_rgba(239,68,68,0.22)]"
            style={{ left: `${(markerX / imageWidth) * 100}%`, top: `${(markerY / imageHeight) * 100}%` }}
          >
            <span className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-200" />
          </span>
        )}
      </button>
      <figcaption className="flex items-center gap-2 border-t border-zinc-800 px-3 py-2 text-[11px] text-zinc-500">
        <ImageIcon size={12} />
        <span>{screenshotLabel}</span>
      </figcaption>
    </figure>
  );
}

function isBrowserToolName(toolName: unknown): boolean {
  return toolName === "browser_companion" || toolName === "browser_computer" || toolName === "browser_use" || toolName === "computer_use";
}

function isBrowserActivityEvent(event: NonNullable<ChatMessagesRendererProps["messages"][number]["events"]>[number]): boolean {
  return (
    isBrowserToolName(event.tool_name)
    || event.type === "browser_screenshot"
    || event.type === "browser_state_invalidated"
    || event.type === "browser_state_snapshot"
    || event.type === "browser_dom_snapshot"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isImageDataUrl(value: string): boolean {
  return /^data:image\/[a-z0-9.+-]+;base64,/i.test(value);
}

function browserActionForEvent(event: NonNullable<ChatMessagesRendererProps["messages"][number]["events"]>[number]): string | undefined {
  if (typeof event.action === "string") return event.action;
  const args = isRecord(event.arguments) ? event.arguments : {};
  return typeof args.action === "string" ? args.action : undefined;
}

function collectBrowserScreenshots(
  value: unknown,
  event: NonNullable<ChatMessagesRendererProps["messages"][number]["events"]>[number],
  screenshots: BrowserScreenshot[],
  seen: Set<string>,
): BrowserScreenshot[] {
  if (Array.isArray(value)) {
    value.forEach((item) => collectBrowserScreenshots(item, event, screenshots, seen));
    return screenshots;
  }
  if (!isRecord(value)) return screenshots;

  const dataUrl = stringValue(value.data_url) || stringValue(value.dataUrl);
  if (dataUrl && isImageDataUrl(dataUrl) && !seen.has(dataUrl)) {
    seen.add(dataUrl);
    screenshots.push({
      id: `stream-${String(event.tool_call_id ?? event.timestamp ?? screenshots.length)}-${screenshots.length}`,
      run_id: "stream",
      tool_call_id: typeof event.tool_call_id === "string" ? event.tool_call_id : null,
      tool_name: typeof event.tool_name === "string" ? event.tool_name : undefined,
      mime_type: stringValue(value.mime_type) || "image/png",
      data_url: dataUrl,
      action: stringValue(value.action) || browserActionForEvent(event),
      image_size: isRecord(value.image_size) ? value.image_size : undefined,
      click_marker: isRecord(value.click_marker) ? value.click_marker : undefined,
      marker: isRecord(value.marker) ? value.marker : undefined,
      drag_marker: isRecord(value.drag_marker) ? value.drag_marker : undefined,
      target_window: isRecord(value.target_window) ? value.target_window : undefined,
    });
  }

  for (const [key, item] of Object.entries(value)) {
    if (key === "data_url" || key === "dataUrl") continue;
    if (isRecord(item) || Array.isArray(item)) collectBrowserScreenshots(item, event, screenshots, seen);
  }
  return screenshots;
}

export function streamedBrowserScreenshots(message: ChatMessagesRendererProps["messages"][number]): BrowserScreenshot[] {
  const screenshots: BrowserScreenshot[] = [];
  const seen = new Set<string>();
  for (const event of message.events ?? []) {
    if (!isBrowserActivityEvent(event)) continue;
    collectBrowserScreenshots(event, event, screenshots, seen);
    collectBrowserScreenshots(event.result, event, screenshots, seen);
    collectBrowserScreenshots(event.artifact, event, screenshots, seen);
    collectBrowserScreenshots(event.artifacts, event, screenshots, seen);
    collectBrowserScreenshots(event.output, event, screenshots, seen);
  }
  return screenshots;
}

function hasBrowserToolLog(message: ChatMessagesRendererProps["messages"][number]): boolean {
  return (message.toolLogs ?? []).some((log) => isBrowserToolName(log.tool_name));
}

function hasBrowserToolEvent(message: ChatMessagesRendererProps["messages"][number]): boolean {
  return (message.events ?? []).some((event) => isBrowserActivityEvent(event));
}

function hasRunningBrowserToolEvent(message: ChatMessagesRendererProps["messages"][number]): boolean {
  return (message.events ?? []).some((event) => (
    isBrowserToolName(event.tool_name)
    && (
      event.type === "tool_call" ||
      event.type === "tool_call_started" ||
      event.phase === "tool_call" ||
      event.phase === "tool_call_started"
    )
  ));
}

function BrowserScreenshotStrip({
  message,
  onOpenImagePreview,
}: {
  message: ChatMessagesRendererProps["messages"][number];
  onOpenImagePreview?: (image: ImagePreviewRequest) => void;
}) {
  const [screenshots, setScreenshots] = useState<BrowserScreenshot[]>([]);
  const [omittedCount, setOmittedCount] = useState(0);
  const [failed, setFailed] = useState(false);
  const liveScreenshots = streamedBrowserScreenshots(message);
  const hasBrowserLog = hasBrowserToolLog(message);
  const hasBrowserActivity = hasBrowserLog || hasBrowserToolEvent(message);
  const hasRunningBrowserActivity = hasRunningBrowserToolEvent(message);
  const canFetchStoredScreenshots = hasBrowserLog && !message.id.startsWith("optimistic-");

  useEffect(() => {
    let cancelled = false;
    setScreenshots([]);
    setOmittedCount(0);
    setFailed(false);
    if (!message.conversationId || !canFetchStoredScreenshots) return () => {
      cancelled = true;
    };
    void chatMessageResources.getBrowserScreenshots(message.conversationId, message.id)
      .then((result) => {
        if (!cancelled) {
          setScreenshots(result.screenshots ?? []);
          setOmittedCount(Number(result.omitted_count ?? 0));
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [message.conversationId, message.id, canFetchStoredScreenshots]);

  if (!hasBrowserActivity) return null;

  if (liveScreenshots.length > 0 && !canFetchStoredScreenshots) {
    return (
      <div className="mb-4 grid gap-3">
        {liveScreenshots.map((screenshot) => (
          <BrowserScreenshotPreview key={screenshot.id} screenshot={screenshot} onOpenImagePreview={onOpenImagePreview} />
        ))}
      </div>
    );
  }

  if (!canFetchStoredScreenshots && hasRunningBrowserActivity) {
    return (
      <div className="mb-3 flex w-fit items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-[11px] text-zinc-400">
        <Loader2 size={12} className="animate-spin text-blue-300" />
        <span>画面操作を実行中</span>
      </div>
    );
  }

  if (screenshots.length === 0) {
    return failed ? (
      <div className="mb-3 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-[11px] text-zinc-500">
        スクリーンショットを読み込めませんでした。
      </div>
    ) : null;
  }

  return (
    <div className="mb-4 grid gap-3">
      {omittedCount > 0 && (
        <div className="w-fit rounded-md border border-zinc-800 bg-zinc-950/70 px-2.5 py-1.5 text-[11px] text-zinc-500">
          古いスクリーンショット {omittedCount} 件を省略しています。
        </div>
      )}
      {screenshots.map((screenshot) => (
        <BrowserScreenshotPreview key={screenshot.id} screenshot={screenshot} onOpenImagePreview={onOpenImagePreview} />
      ))}
    </div>
  );
}

function AuthorityPendingNotice() {
  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[12px] leading-relaxed text-amber-100">
      <Clock size={14} className="shrink-0 text-amber-300" />
      <span className="shrink-0 font-semibold">{AUTHORITY_PENDING_TITLE}</span>
      <span className="min-w-0 text-amber-100/80">{AUTHORITY_PENDING_DETAIL}</span>
    </div>
  );
}

function ToolActivityToggle({
  isOpen,
  onToggle,
  summary,
}: {
  isOpen: boolean;
  onToggle: () => void;
  summary: ToolActivityTraySummary;
}) {
  return (
    <button
      type="button"
      aria-expanded={isOpen}
      aria-label={`toolログを${isOpen ? "閉じる" : "開く"}: ${summary.label}`}
      className="inline-flex min-w-0 max-w-[min(260px,46vw)] shrink items-center gap-1.5 whitespace-nowrap text-[11px] font-medium text-zinc-500 transition-colors hover:text-zinc-300 focus-visible:text-zinc-200 focus-visible:outline-none"
      onClick={onToggle}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", summary.failedCount > 0 ? "bg-red-400" : summary.runningCount > 0 ? "animate-pulse bg-blue-300" : "bg-zinc-600")} />
      <span className="min-w-0 truncate">{summary.label}</span>
      {!isOpen && <span className="shrink-0 text-zinc-500">開く</span>}
      <ChevronRight size={13} className={cn("shrink-0 transition-transform", isOpen && "rotate-90")} />
    </button>
  );
}

function ToolActivityTray({
  groups,
  isOpen,
  message,
  onOpenToolPreview,
}: {
  groups: ToolActivityGroup[];
  isOpen: boolean;
  message: ChatMessagesRendererProps["messages"][number];
  onOpenToolPreview?: (previewId: string) => void;
}) {
  if (!isOpen || groups.length === 0) return null;
  const previewableCallIds = new Set(
    (message.events ?? [])
      .filter((event) => (
        event.type === "browser_screenshot"
        || event.type === "browser_state_snapshot"
        || event.type === "browser_dom_snapshot"
        || event.type === "tool_call_completed"
      ))
      .map((event) => String(event.tool_call_id ?? "").trim())
      .filter(Boolean),
  );
  return (
    <div className="rumi-tool-activity mb-4 grid w-full gap-3 text-zinc-300">
      {groups.map((group) => (
        <div key={group.id} className="grid min-w-0 gap-1.5">
          <div className="flex min-w-0 items-center gap-2 text-[12px] font-medium text-zinc-400">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" />
            <span className="min-w-0 truncate">{group.label}</span>
          </div>
          <div className="ml-1.5 grid min-w-0 gap-1.5 border-l border-zinc-800/70 pl-4">
            {group.items.map((item) => {
              const artifactPreviewId = item.artifacts?.find((artifact) => artifact.url)?.path;
              const previewId = item.toolCallId && previewableCallIds.has(item.toolCallId) ? item.toolCallId : artifactPreviewId;
              const hasPreview = Boolean(previewId);
              const statusLabel = item.status === "failed" ? "エラー" : "";
              const statusLine = [statusLabel, item.detail].filter(Boolean).join(" · ");
              const body = (
                <>
                  <span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", item.status === "failed" ? "bg-red-400" : item.status === "running" ? "animate-pulse bg-blue-300" : "bg-zinc-700")} />
                  <span className="min-w-0 max-w-full flex-1 overflow-hidden">
                    <span className="flex min-w-0 max-w-full items-baseline gap-2 text-[13px] leading-5 text-zinc-300">
                      <span className="min-w-0 flex-1 truncate">{item.input || item.detail || item.toolName}</span>
                      {item.durationLabel && <span className="shrink-0 font-mono text-[10px] text-zinc-600">{item.durationLabel}</span>}
                    </span>
                    {statusLine && (
                      <span className={cn("block max-w-full truncate text-[11px] leading-5", item.status === "failed" ? "text-red-300" : "text-zinc-500")}>
                        {statusLine}
                      </span>
                    )}
                    {item.nextStep && (
                      <span className="block max-w-full truncate text-[11px] leading-5 text-zinc-600">{item.nextStep}</span>
                    )}
                    {!item.supported && item.rawJson && (
                      <code className="mt-1 block max-h-28 max-w-full overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-zinc-950/70 px-2 py-1.5 font-mono text-[10px] leading-4 text-zinc-500">
                        {item.rawJson}
                      </code>
                    )}
                  </span>
                </>
              );
              return hasPreview ? (
                <button
                  key={item.id}
                  type="button"
                  className="group/tool -ml-[5px] flex w-full min-w-0 max-w-full items-start gap-3 overflow-hidden rounded-lg px-1 py-1.5 text-left transition-colors hover:bg-zinc-900/55 focus-visible:bg-zinc-900/55 focus-visible:outline-none"
                  onClick={() => {
                    if (previewId) onOpenToolPreview?.(previewId);
                  }}
                >
                  {body}
                </button>
              ) : (
                <div key={item.id} className="-ml-[5px] flex w-full min-w-0 max-w-full items-start gap-3 overflow-hidden px-1 py-1.5">
                  {body}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function PendingToolTray({ toolNames, toolStartedAt = {} }: { toolNames: string[]; toolStartedAt?: Record<string, number> }) {
  const now = useActivityNow(toolNames.some((name) => Boolean(toolStartedAt[name])));
  const summary = summarizePendingToolNames(toolNames);
  if (summary.totalCount === 0) return null;

  return (
    <div className="mt-2 ml-5 w-[min(820px,calc(100vw-64px))] px-1 py-2">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-zinc-400">
        <Loader2 size={12} className="animate-spin text-blue-300" />
        <span>見込まれた tool</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {summary.visibleNames.map((name) => {
          const folder = toolFolderFor(name);
          return (
            <span key={name} className="inline-flex max-w-[220px] items-baseline gap-1.5 rounded-md bg-zinc-900/50 px-2 py-1 text-[11px] text-zinc-300" title={folder.label}>
              <span className="truncate">{name}</span>
              {toolStartedAt[name] && <span className="font-mono text-[10px] text-zinc-600">{elapsedDurationLabel(toolStartedAt[name], now)}</span>}
            </span>
          );
        })}
        {summary.hiddenCount > 0 && (
          <span className="inline-flex items-center rounded-md bg-zinc-900/40 px-2 py-1 text-[11px] text-zinc-500">
            その他 {summary.hiddenCount} 個が見込まれました
          </span>
        )}
      </div>
    </div>
  );
}

export function ChatMessagesRenderer({
  error,
  isMessagesRegionVisible,
  isLoading,
  isNewConversation,
  isGenerating,
  pendingStatus,
  pendingToolNames = [],
  pendingStartedAt,
  pendingToolStartedAt = {},
  messages,
  messagesEndRef,
  unknownBlockStrategy,
  showActivityInMessages,
  showWidgets,
  onOpenToolPreview,
}: ChatMessagesRendererProps) {
  const [imagePreview, setImagePreview] = useState<ImagePreviewRequest | null>(null);
  const [openToolActivityByMessageId, setOpenToolActivityByMessageId] = useState<Record<string, boolean | undefined>>({});
  const hasRunningToolActivity = showActivityInMessages && messages.some((message) => message.role === "agent" && hasRunningToolActivityMessage(message));
  const visibleMessages = useMemo(() => visibleChatMessages(messages), [messages]);
  const hasAuthorityPendingMessage = useMemo(() => visibleMessages.some(isAuthorityWaitingMessage), [visibleMessages]);
  const activityNow = useActivityNow(hasRunningToolActivity);

  return (
    <>
      {error && <div className="mx-4 mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</div>}

      {!isMessagesRegionVisible ? null : isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <RumiActivityLoading status={pendingStatus} toolNames={pendingToolNames} startedAt={pendingStartedAt} />
        </div>
      ) : isNewConversation ? (
        <div className="flex-1" />
      ) : (
        <div className="flex-1 overflow-x-hidden overflow-y-auto px-5 py-3 md:px-8 lg:px-10 xl:px-12">
          <div className="mx-auto w-full max-w-6xl min-w-0 space-y-4">
            {visibleMessages.map((message) => {
              const toolActivity = showActivityInMessages && message.role === "agent"
                ? toolActivityStateForMessage(message, activityNow)
                : null;
              const isToolActivityOpen = toolActivity
                ? openToolActivityByMessageId[message.id] ?? toolActivity.hasRunningItems
                : false;
              const isAuthorityPending = isAuthorityWaitingMessage(message);
              const toggleToolActivity = () => {
                if (!toolActivity) return;
                setOpenToolActivityByMessageId((current) => {
                  const currentOpen = current[message.id] ?? toolActivity.hasRunningItems;
                  return { ...current, [message.id]: !currentOpen };
                });
              };

              return (
              <div key={message.id} className={cn("rumi-message-row group/message flex min-w-0 gap-3 select-text", message.role === "user" ? "flex-row-reverse lg:pr-6 xl:pr-8 2xl:pr-10" : "lg:pl-8 xl:pl-12 2xl:pl-16")}>
                <div className={cn("flex min-w-0 flex-col pt-1", message.role === "user" ? "max-w-[82%] items-end lg:max-w-[70%] 2xl:max-w-[64%]" : "flex-1 items-start")}>
                  {message.role === "agent" && (
                    <div className="mb-1.5 flex max-w-full min-w-0 flex-nowrap items-center gap-2 overflow-hidden">
                      <span className="shrink-0 text-xs font-semibold tracking-wide text-zinc-300">Assistant</span>
                      {message.metadata?.executionTime && (
                        <span className="flex shrink-0 items-center gap-1 font-mono text-[10px] text-zinc-500">
                          <Clock size={10} /> {message.metadata.executionTime}
                        </span>
                      )}
                      {message.metadata?.thinkingDuration && (
                        <span className="shrink-0 font-mono text-[10px] text-zinc-600">thinking {message.metadata.thinkingDuration}</span>
                      )}
                      {toolActivity && (
                        <ToolActivityToggle
                          isOpen={isToolActivityOpen}
                          onToggle={toggleToolActivity}
                          summary={toolActivity.summary}
                        />
                      )}
                    </div>
                  )}

                  <div className={cn("flex min-w-0 max-w-full flex-col", message.role === "user" ? "items-start" : "w-full items-start")}>
                    {(() => {
                      const hasToolActivity = Boolean(toolActivity);
                      return (
                    <div
                      className={cn(
                        "rumi-message-bubble relative max-w-full overflow-x-hidden rounded-2xl px-3 py-3 text-[14px] outline-none select-text sm:px-4",
                        message.role === "user"
                          ? "bg-zinc-800/80 text-zinc-100 rounded-tr-sm shadow-sm border border-zinc-700/50"
                          : "w-full text-zinc-200 bg-transparent",
                      )}
                    >
                      {toolActivity && (
                        <ToolActivityTray
                          groups={toolActivity.groups}
                          isOpen={isToolActivityOpen}
                          message={message}
                          onOpenToolPreview={onOpenToolPreview}
                        />
                      )}

                      {message.role === "agent" && message.metadata?.thinkingTranscript && (
                        <details className="mb-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-400">
                          <summary className="cursor-pointer select-none text-[11px] font-medium text-zinc-300">
                            Trace
                          </summary>
                          <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-zinc-400">
                            {message.metadata.thinkingTranscript}
                          </pre>
                        </details>
                      )}

                      <div className="rumi-message-content markdown-body min-w-0 max-w-full select-text space-y-4 overflow-x-hidden break-words leading-relaxed">
                        {isAuthorityPending
                          ? (
                              <AuthorityPendingNotice />
                            )
                          : message.content.length > 0 && (messageVisibleText(message) || message.content.some((block) => String(block.type ?? "text") !== "text"))
                          ? message.content.map((block, index) => (
                              <MessageBlock key={`${message.id}-${index}`} block={block} unknownStrategy={unknownBlockStrategy} onOpenImagePreview={setImagePreview} />
                            ))
                          : shouldShowEmptyResponseWarning(message, hasToolActivity)
                            ? (
                                <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[12px] leading-relaxed text-amber-100">
                                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-300" />
                                  <span>レスポンス本文が空でした。stream が途中で閉じたか、thinking のみで終了した可能性があります。</span>
                                </div>
                              )
                            : <MessageMarkdown text={message.rawText} />}
                      </div>

                      {showWidgets && message.widget && <WidgetCard widget={message.widget} />}
                    </div>
                      );
                    })()}

                    <MessageActionBar message={message} />
                  </div>
                </div>
              </div>
              );
            })}

            {isGenerating && !hasAuthorityPendingMessage && (
              <div className="flex gap-3">
                <div className="text-zinc-400 text-[13px] flex flex-col gap-1 mt-1.5">
                  <RumiActivityLoading status={pendingStatus} toolNames={pendingToolNames} startedAt={pendingStartedAt} compact />
                  {pendingToolNames.length > 0 && (
                    <PendingToolTray toolNames={pendingToolNames} toolStartedAt={pendingToolStartedAt} />
                  )}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} className="h-1" />
          </div>
        </div>
      )}
      <ArtifactPreviewDialog item={artifactDialogItemFromImagePreview(imagePreview)} onClose={() => setImagePreview(null)} />
    </>
  );
}
