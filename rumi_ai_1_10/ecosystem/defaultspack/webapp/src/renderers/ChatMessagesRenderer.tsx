import { AlertTriangle, Check, CheckCircle2, ChevronDown, Clock, Copy, ExternalLink, Image as ImageIcon, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import { cn } from "../lib/cn";
import { buildToolActivityGroups, toolFolderFor, type ToolActivityItem } from "../lib/toolActivity";
import { api, type BrowserScreenshot, type ChatContentBlock } from "../lib/api";
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

function imageSizeLabel(size: BrowserScreenshot["image_size"]): string {
  const width = Number(size?.width ?? 0);
  const height = Number(size?.height ?? 0);
  return width > 0 && height > 0 ? `${width} x ${height}` : "";
}

function BrowserImagePreviewDialog({
  image,
  onClose,
}: {
  image: ImagePreviewRequest | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!image) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [image, onClose]);

  if (!image) return null;

  return (
    <div className="rumi-image-preview-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/72 px-4 py-5 backdrop-blur-md" role="dialog" aria-modal="true" aria-label={image.title}>
      <button type="button" className="absolute inset-0 cursor-default" aria-label="画像プレビューを閉じる" onClick={onClose} />
      <section className="rumi-image-preview-shell relative flex h-[min(88vh,980px)] w-[min(94vw,1180px)] flex-col overflow-hidden rounded-xl border border-zinc-800 bg-[#0b0b0d] shadow-[0_28px_90px_rgba(0,0,0,0.55)]">
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950/95 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <ImageIcon size={15} className="shrink-0 text-zinc-500" />
            <div className="min-w-0">
              <div className="truncate text-[12px] font-medium text-zinc-200">{image.title}</div>
              {image.subtitle && <div className="truncate text-[10px] text-zinc-600">{image.subtitle}</div>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {image.href && (
              <a
                href={image.href}
                target="_blank"
                rel="noreferrer"
                aria-label="元画像を開く"
                title="元画像を開く"
                className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200 focus-visible:bg-zinc-900 focus-visible:text-zinc-200 focus-visible:outline-none"
              >
                <ExternalLink size={15} />
              </a>
            )}
            <button
              type="button"
              aria-label="閉じる"
              title="閉じる"
              className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200 focus-visible:bg-zinc-900 focus-visible:text-zinc-200 focus-visible:outline-none"
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto bg-black">
          <div className="rumi-image-preview-media flex min-h-full items-center justify-center p-4">
            <img src={image.src} alt={image.alt} className="max-h-full max-w-full rounded-lg border border-zinc-800/80 object-contain shadow-[0_18px_70px_rgba(0,0,0,0.45)]" />
          </div>
        </div>
        {image.details && image.details.length > 0 && (
          <dl className="grid max-h-36 shrink-0 grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1.5 overflow-auto border-t border-zinc-800 bg-zinc-950/95 px-3 py-2 font-mono text-[10px] leading-5">
            {image.details.map((detail) => (
              <div key={`${detail.label}-${detail.value}`} className="contents">
                <dt className="text-zinc-600">{detail.label}</dt>
                <dd className="min-w-0 break-words text-zinc-400">{detail.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
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
    return <ReactMarkdown>{String(block.text ?? "")}</ReactMarkdown>;
  }

  if (blockType === "code") {
    return (
      <pre className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 overflow-x-auto text-[12px] text-zinc-200 font-mono">
        <code>{String(block.text ?? "")}</code>
      </pre>
    );
  }

  if (blockType === "image" || blockType === "image_url") {
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
    <pre className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 overflow-x-auto text-[11px] text-zinc-400 font-mono">
      {JSON.stringify(block, null, 2)}
    </pre>
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

  await api.writeClipboard(text);
}

function MessageActionBar({
  message,
}: {
  message: ChatMessagesRendererProps["messages"][number];
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const text = messageCopyText(message);
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
    </div>
  );
}

function WidgetCard({ widget }: { widget: Record<string, unknown> }) {
  return (
    <details className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3">
      <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-blue-300">
        Widget details
      </summary>
      <pre className="mt-2 overflow-x-auto text-[11px] font-mono text-zinc-200">{JSON.stringify(widget, null, 2)}</pre>
    </details>
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
  return toolName === "browser_computer" || toolName === "browser_use" || toolName === "computer_use";
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

function streamedBrowserScreenshots(message: ChatMessagesRendererProps["messages"][number]): BrowserScreenshot[] {
  const screenshots: BrowserScreenshot[] = [];
  const seen = new Set<string>();
  for (const event of message.events ?? []) {
    if (!isBrowserToolName(event.tool_name)) continue;
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
  return (message.events ?? []).some((event) => isBrowserToolName(event.tool_name));
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
    void api.getBrowserScreenshots(message.conversationId, message.id)
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

function ToolStatusIcon({ item }: { item: ToolActivityItem }) {
  if (item.status === "running") return <Loader2 size={12} className="shrink-0 animate-spin text-blue-300" />;
  if (item.status === "failed") return <AlertTriangle size={12} className="shrink-0 text-red-300" />;
  return <CheckCircle2 size={12} className="shrink-0 text-zinc-400" />;
}

function toolStatusLabel(item: ToolActivityItem): string {
  if (item.status === "running") return "実行中";
  if (item.status === "failed") return "失敗";
  return "完了";
}

function isJsonLikeDetail(value: string): boolean {
  const trimmed = value.trim();
  return (
    (trimmed.startsWith("{") && trimmed.endsWith("}"))
    || (trimmed.startsWith("[") && trimmed.endsWith("]"))
  );
}

function ToolResultDetail({ detail }: { detail: string }) {
  if (isJsonLikeDetail(detail)) {
    return (
      <details className="min-w-0 flex-1 text-[12px] leading-relaxed">
        <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">
          詳細データ
        </summary>
        <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/30 p-2 font-mono text-[11px] text-zinc-500">
          {detail}
        </pre>
      </details>
    );
  }

  return <span className="min-w-0 break-words text-[12px] leading-relaxed">{detail}</span>;
}

function ToolActivityTray({
  message,
  onOpenImagePreview,
}: {
  message: ChatMessagesRendererProps["messages"][number];
  onOpenImagePreview?: (image: ImagePreviewRequest) => void;
}) {
  const [screenshots, setScreenshots] = useState<BrowserScreenshot[]>([]);
  const liveScreenshots = streamedBrowserScreenshots(message);
  const canFetchStoredScreenshots = Boolean(message.conversationId) && hasBrowserToolLog(message) && !message.id.startsWith("optimistic-");

  useEffect(() => {
    let cancelled = false;
    setScreenshots([]);
    if (!message.conversationId || !canFetchStoredScreenshots) return () => {
      cancelled = true;
    };
    void api.getBrowserScreenshots(message.conversationId, message.id)
      .then((result) => {
        if (!cancelled) setScreenshots(result.screenshots ?? []);
      })
      .catch(() => {
        if (!cancelled) setScreenshots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [message.conversationId, message.id, canFetchStoredScreenshots]);

  const groups = buildToolActivityGroups(message.toolLogs ?? [], message.events ?? [], { conversationId: message.conversationId });
  if (groups.length === 0) return null;
  const items = groups.flatMap((group) => group.items);
  const total = items.length;
  const visibleScreenshots = canFetchStoredScreenshots ? screenshots : liveScreenshots;

  return (
    <details className="rumi-tool-activity mb-4 w-full rounded-xl border border-zinc-800/90 bg-zinc-950/70 px-4 py-3 text-zinc-300 shadow-[0_16px_44px_rgba(0,0,0,0.22)]" open>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[13px] text-zinc-300">
        <span className="flex min-w-0 items-center gap-2 font-medium">
          <span className="truncate">使用した tool</span>
          <span className="rounded-full border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">{total}</span>
        </span>
        <ChevronDown size={16} className="rumi-tool-caret shrink-0 text-zinc-500" />
      </summary>
      <div className="mt-3 grid gap-2">
        {items.map((item) => (
          <div key={item.id} className="rumi-tool-card rounded-lg border border-zinc-800/80 bg-zinc-900/55 px-3.5 py-3">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-2.5">
                <span className="mt-0.5">
                  <ToolStatusIcon item={item} />
                </span>
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded-md border border-zinc-800 bg-zinc-950/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
                      {item.folderLabel}
                    </span>
                    <span className="min-w-0 truncate font-mono text-[12px] text-zinc-200">{item.toolName}</span>
                  </div>
                  {item.input && (
                    <div className="mt-1 flex min-w-0 items-center gap-1.5 text-[10px] leading-4 text-zinc-600">
                      <span className="shrink-0 text-zinc-700">入力</span>
                      <span className="min-w-0 truncate font-mono">{item.input}</span>
                    </div>
                  )}
                </div>
              </div>
              <span className="shrink-0 rounded-full border border-zinc-800 bg-zinc-950/70 px-2 py-0.5 text-[10px] text-zinc-500">
                {toolStatusLabel(item)}
              </span>
            </div>
            {item.detail && (
              <div className="mt-2 flex min-w-0 items-start gap-2 rounded-md border border-zinc-800/70 bg-black/20 px-3 py-2 text-zinc-300">
                <span className="shrink-0 text-[10px] font-medium text-zinc-600">結果</span>
                <ToolResultDetail detail={item.detail} />
              </div>
            )}
            {visibleScreenshots
              .filter((screenshot) => !item.toolCallId || screenshot.tool_call_id === item.toolCallId)
              .map((screenshot) => (
                <div key={screenshot.id} className="mt-3">
                  <BrowserScreenshotPreview screenshot={screenshot} compact onOpenImagePreview={onOpenImagePreview} />
                </div>
              ))}
            {!visibleScreenshots.some((screenshot) => !item.toolCallId || screenshot.tool_call_id === item.toolCallId) && item.artifacts?.filter((artifact) => artifact.kind === "image" && artifact.url).map((artifact) => (
              <div key={artifact.path} className="mt-3">
                <figure className="max-w-full overflow-hidden rounded-lg border border-zinc-800 bg-black/30">
                  <button
                    type="button"
                    className="block w-full cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
                    onClick={() => onOpenImagePreview?.({
                      src: String(artifact.url ?? ""),
                      href: String(artifact.url ?? ""),
                      title: artifact.name,
                      alt: artifact.name,
                      subtitle: item.toolName,
                      details: [
                        { label: "tool", value: item.toolName },
                        { label: "path", value: artifact.path },
                      ],
                    })}
                  >
                    <img src={artifact.url} alt={artifact.name} className="block h-auto w-full object-contain" style={{ maxHeight: "min(220px, 30vh)" }} />
                  </button>
                  <figcaption className="flex items-center gap-2 border-t border-zinc-800 px-3 py-2 text-[11px] text-zinc-500">
                    <ImageIcon size={12} />
                    <span className="truncate">{artifact.name}</span>
                  </figcaption>
                </figure>
              </div>
            ))}
            {item.artifacts && item.artifacts.filter((artifact) => artifact.kind !== "image").length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {item.artifacts.filter((artifact) => artifact.kind !== "image").map((artifact) => (
                  <a
                    key={artifact.path}
                    href={artifact.url}
                    download={artifact.name}
                    className="rounded-md border border-zinc-800 bg-zinc-950/70 px-2 py-1 font-mono text-[10px] text-zinc-500 hover:border-zinc-700 hover:text-zinc-200"
                  >
                    {artifact.name}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function PendingToolTray({ toolNames }: { toolNames: string[] }) {
  if (toolNames.length === 0) return null;
  const groups = new Map<string, { label: string; names: string[] }>();
  for (const name of toolNames) {
    const folder = toolFolderFor(name);
    const existing = groups.get(folder.id);
    if (existing) {
      existing.names.push(name);
    } else {
      groups.set(folder.id, { label: folder.label, names: [name] });
    }
  }

  return (
    <div className="mt-2 ml-5 w-[min(820px,calc(100vw-64px))] rounded-xl border border-zinc-800 bg-zinc-950/70 px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-zinc-400">
        <Loader2 size={12} className="animate-spin text-blue-300" />
        <span>実行中の tool</span>
      </div>
      <div className="space-y-2">
        {[...groups.entries()].map(([id, group]) => (
          <div key={id} className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
              <ChevronDown size={11} className="rotate-180" />
              <span>{group.label}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {group.names.map((name) => (
                <span key={name} className="max-w-[220px] truncate rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-[11px] text-zinc-300">
                  {name}
                </span>
              ))}
            </div>
          </div>
        ))}
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
  messages,
  messagesEndRef,
  unknownBlockStrategy,
  showActivityInMessages,
  showWidgets,
}: ChatMessagesRendererProps) {
  const [imagePreview, setImagePreview] = useState<ImagePreviewRequest | null>(null);

  return (
    <>
      {error && <div className="mx-4 mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">{error}</div>}

      {!isMessagesRegionVisible ? null : isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={18} className="animate-spin text-zinc-500" />
        </div>
      ) : isNewConversation ? (
        <div className="flex-1" />
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <div className="w-full max-w-5xl mx-auto space-y-4">
            {messages.map((message) => (
              <div key={message.id} className={cn("rumi-message-row group/message flex gap-3 select-text", message.role === "user" ? "flex-row-reverse" : "")}>
                <div className={cn("flex flex-col min-w-0 pt-1", message.role === "user" ? "items-end max-w-[80%]" : "items-start flex-1")}>
                  {message.role === "agent" && (
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-semibold text-zinc-300 tracking-wide">Rumi</span>
                      {message.metadata?.executionTime && (
                        <span className="text-[10px] text-zinc-500 font-mono flex items-center gap-1">
                          <Clock size={10} /> {message.metadata.executionTime}
                        </span>
                      )}
                    </div>
                  )}

                  <div className={cn("flex max-w-full flex-col", message.role === "user" ? "items-start" : "w-full items-start")}>
                    {(() => {
                      const hasToolActivity = buildToolActivityGroups(message.toolLogs ?? [], message.events ?? []).length > 0;
                      return (
                    <div
                      className={cn(
                        "rumi-message-bubble relative rounded-2xl max-w-full sm:px-4 px-3 py-3 text-[14px] outline-none select-text",
                        message.role === "user"
                          ? "bg-zinc-800/80 text-zinc-100 rounded-tr-sm shadow-sm border border-zinc-700/50"
                          : "w-full text-zinc-200 bg-transparent",
                      )}
                    >
                      {showActivityInMessages && message.role === "agent" && <ToolActivityTray message={message} onOpenImagePreview={setImagePreview} />}
                      {message.role === "agent" && !showActivityInMessages && <BrowserScreenshotStrip message={message} onOpenImagePreview={setImagePreview} />}

                      {message.role === "agent" && message.metadata?.thinkingTranscript && (
                        <details className="mb-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-xs text-zinc-400">
                          <summary className="cursor-pointer select-none text-[11px] font-medium text-zinc-300">
                            Thinking
                          </summary>
                          <pre className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-zinc-400">
                            {message.metadata.thinkingTranscript}
                          </pre>
                        </details>
                      )}

                      <div className="rumi-message-content markdown-body select-text leading-relaxed break-words space-y-4">
                        {message.content.length > 0 && (messageVisibleText(message) || message.content.some((block) => String(block.type ?? "text") !== "text"))
                          ? message.content.map((block, index) => (
                              <MessageBlock key={`${message.id}-${index}`} block={block} unknownStrategy={unknownBlockStrategy} onOpenImagePreview={setImagePreview} />
                            ))
                          : message.role === "agent" && !messageVisibleText(message) && !hasToolActivity
                            ? (
                                <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[12px] leading-relaxed text-amber-100">
                                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-300" />
                                  <span>レスポンス本文が空でした。stream が途中で閉じたか、thinking のみで終了した可能性があります。</span>
                                </div>
                              )
                            : <ReactMarkdown>{message.rawText}</ReactMarkdown>}
                      </div>

                      {showWidgets && message.widget && <WidgetCard widget={message.widget} />}
                    </div>
                      );
                    })()}

                    <MessageActionBar message={message} />
                  </div>
                </div>
              </div>
            ))}

            {isGenerating && (
              <div className="flex gap-3">
                <div className="text-zinc-400 text-[13px] flex flex-col gap-1 mt-1.5">
                  <div className="flex items-center gap-2">
                    <Loader2 size={14} className="text-zinc-400 animate-spin" />
                    <span className="animate-pulse">{pendingStatus || "Processing..."}</span>
                  </div>
                  {pendingToolNames.length > 0 && (
                    <PendingToolTray toolNames={pendingToolNames} />
                  )}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} className="h-1" />
          </div>
        </div>
      )}
      <BrowserImagePreviewDialog image={imagePreview} onClose={() => setImagePreview(null)} />
    </>
  );
}
