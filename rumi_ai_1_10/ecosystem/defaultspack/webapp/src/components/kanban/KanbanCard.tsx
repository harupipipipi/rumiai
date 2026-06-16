import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowLeft, ArrowRight, CalendarDays, CheckSquare, ExternalLink, GripVertical, MessageSquareText, Pencil, Trash2 } from "lucide-react";
import { useEffect, useRef, type MouseEvent, type PointerEvent } from "react";

import type { KanbanCard as KanbanCardRecord, KanbanColumn } from "../../lib/api";
import { cn } from "../../lib/cn";

function priorityClassName(priority: string | undefined): string {
  const normalized = String(priority || "normal").toLowerCase();
  if (normalized === "urgent") return "border-red-500/30 bg-red-500/10 text-red-200";
  if (normalized === "high") return "border-orange-500/30 bg-orange-500/10 text-orange-200";
  if (normalized === "low") return "border-zinc-800 bg-zinc-950/70 text-zinc-500";
  return "border-zinc-700/70 bg-zinc-900/80 text-zinc-300";
}

function checklistLabel(card: KanbanCardRecord): string | null {
  const checklist = card.checklist ?? [];
  if (!checklist.length) return null;
  const done = checklist.filter((item) => item.done).length;
  return `${done}/${checklist.length}`;
}

function visibleRunStatus(status: string | null | undefined): string | null {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized || normalized === "idle") return null;
  return normalized.replace(/_/g, " ");
}

function visibleLabels(card: KanbanCardRecord): string[] {
  const sourceType = String(card.source_type || "").trim().toLowerCase();
  return (card.labels ?? []).filter((label) => {
    const normalized = String(label || "").trim().toLowerCase();
    return normalized && normalized !== "conversation" && normalized !== "idle" && normalized !== sourceType;
  });
}

function isCardControlTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("button,a,input,textarea,select,[data-kanban-card-control='true']"));
}

function stopDragActivation(event: PointerEvent<HTMLElement>) {
  event.stopPropagation();
}

function stopCardClick(event: MouseEvent<HTMLElement>) {
  event.stopPropagation();
}

export function KanbanCard({
  card,
  columns,
  onEdit,
  onMoveToColumn,
  onDelete,
  onOpenChat,
}: {
  card: KanbanCardRecord;
  columns: KanbanColumn[];
  onEdit: (card: KanbanCardRecord) => void;
  onMoveToColumn: (cardId: string, columnId: string) => void;
  onDelete?: (cardId: string) => void;
  onOpenChat?: (conversationId: string) => void;
}) {
  const sortable = useSortable({ id: card.card_id });
  const wasDraggingRef = useRef(false);
  const style = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
  };
  useEffect(() => {
    let clearDragGuard: number | undefined;
    if (sortable.isDragging) {
      wasDraggingRef.current = true;
    } else if (wasDraggingRef.current) {
      clearDragGuard = window.setTimeout(() => {
        wasDraggingRef.current = false;
      }, 120);
    }
    return () => {
      if (clearDragGuard) window.clearTimeout(clearDragGuard);
    };
  }, [sortable.isDragging]);
  const columnIndex = columns.findIndex((column) => column.column_id === card.column_id);
  const previousColumn = columnIndex > 0 ? columns[columnIndex - 1] : null;
  const nextColumn = columnIndex >= 0 && columnIndex < columns.length - 1 ? columns[columnIndex + 1] : null;
  const checklist = checklistLabel(card);
  const runStatus = visibleRunStatus(card.agent_status);
  const labels = visibleLabels(card);
  const isBlocked = Boolean(card.blocked_by?.length || String(card.agent_status || "").toLowerCase() === "blocked");
  const handleCardClick = (event: MouseEvent<HTMLElement>) => {
    if (wasDraggingRef.current || sortable.isDragging || isCardControlTarget(event.target)) {
      wasDraggingRef.current = false;
      return;
    }
    onEdit(card);
  };

  return (
    <article
      ref={sortable.setNodeRef}
      style={style}
      data-kanban-card-id={card.card_id}
      onClick={handleCardClick}
      className={cn(
        "group/card relative cursor-pointer select-none rounded-lg border bg-[#111116] p-2.5 shadow-sm outline-none transition-[background-color,border-color,box-shadow,opacity,transform] duration-150 will-change-transform focus-visible:border-sky-400/70 focus-visible:ring-2 focus-visible:ring-sky-400/25",
        sortable.isDragging
          ? "border-sky-400/70 bg-sky-950/20 opacity-30 shadow-none"
          : isBlocked
            ? "border-red-500/30 hover:border-red-400/50"
            : "border-zinc-800/80 hover:border-zinc-700 hover:shadow-lg hover:shadow-black/20",
      )}
    >
      <div className="flex items-start gap-2.5">
        <button
          type="button"
          ref={sortable.setActivatorNodeRef}
          {...sortable.attributes}
          {...sortable.listeners}
          data-kanban-card-control="true"
          data-kanban-drag-handle="true"
          onClick={stopCardClick}
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 touch-none items-center justify-center rounded-md border text-zinc-500 transition focus-visible:border-sky-400/70 focus-visible:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/25",
            sortable.isDragging
              ? "cursor-grabbing border-sky-400/70 bg-sky-400/10 text-sky-100"
              : "cursor-grab border-zinc-800/80 bg-zinc-950/55 hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-100",
          )}
          title="Hold and drag card"
          aria-label={`Hold and drag ${card.title}`}
        >
          <GripVertical size={13} />
        </button>
        <div className="min-w-0 flex-1 text-left">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <h4 className="min-w-0 flex-1 break-words text-[13px] font-semibold leading-snug text-zinc-100">{card.title}</h4>
            <span className={cn("shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-medium", priorityClassName(card.priority))}>
              {card.priority || "normal"}
            </span>
          </div>
          {card.description && (
            <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-zinc-500">{card.description}</p>
          )}
          <div className="mt-2 flex min-w-0 items-center gap-2 text-[10px] leading-none text-zinc-500">
            {card.assignee && <span className="min-w-0 truncate">{card.assignee}</span>}
            {card.due_at && (
              <span className="inline-flex min-w-0 items-center gap-1">
                <CalendarDays size={10} className="shrink-0" />
                <span className="truncate">{card.due_at}</span>
              </span>
            )}
            {checklist && (
              <span className="inline-flex shrink-0 items-center gap-1">
                <CheckSquare size={10} />
                {checklist}
              </span>
            )}
            {runStatus && (
              <span className={cn("inline-flex min-w-0 items-center gap-1 truncate", isBlocked ? "text-red-300/80" : "text-sky-300/80")}>
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                <span className="truncate">{runStatus}</span>
              </span>
            )}
          </div>
        </div>
      </div>

      {labels.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {labels.slice(0, 3).map((label) => (
            <span key={label} className="rounded-full border border-zinc-800 bg-zinc-950/70 px-1.5 py-0.5 text-[9px] text-zinc-500">
              {label}
            </span>
          ))}
          {labels.length > 3 && <span className="text-[9px] text-zinc-600">+{labels.length - 3}</span>}
        </div>
      )}

      {card.pr_url && (
        <div className="mt-2">
          <a
            href={card.pr_url}
            target="_blank"
            rel="noreferrer"
            data-kanban-card-control="true"
            onPointerDown={stopDragActivation}
            onClick={stopCardClick}
            className="inline-flex items-center gap-1 rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-sky-300 hover:bg-sky-500/10"
          >
            <ExternalLink size={10} />
            PR
          </a>
        </div>
      )}

      <div className="mt-2 flex items-center justify-end gap-2 border-t border-zinc-900 pt-2">
        <div
          data-kanban-card-control="true"
          onPointerDown={stopDragActivation}
          onClick={stopCardClick}
          className="flex shrink-0 items-center gap-1"
        >
          {card.conversation_id && onOpenChat && (
            <button
              type="button"
              onClick={() => onOpenChat(card.conversation_id || "")}
              className="flex h-6 w-6 items-center justify-center rounded border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200"
              title="Open linked chat"
              aria-label="Open linked chat"
            >
              <MessageSquareText size={11} />
            </button>
          )}
          <button
            type="button"
            disabled={!previousColumn}
            onClick={() => previousColumn && onMoveToColumn(card.card_id, previousColumn.column_id)}
            className="flex h-6 w-6 items-center justify-center rounded border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"
            title="Move left"
            aria-label="Move left"
          >
            <ArrowLeft size={11} />
          </button>
          <button
            type="button"
            onClick={() => onEdit(card)}
            className="flex h-6 w-6 items-center justify-center rounded border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200"
            title="Edit card"
            aria-label="Edit card"
          >
            <Pencil size={11} />
          </button>
          <button
            type="button"
            disabled={!nextColumn}
            onClick={() => nextColumn && onMoveToColumn(card.card_id, nextColumn.column_id)}
            className="flex h-6 w-6 items-center justify-center rounded border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-30"
            title="Move right"
            aria-label="Move right"
          >
            <ArrowRight size={11} />
          </button>
          {onDelete && (
            <button
              type="button"
              onClick={() => onDelete(card.card_id)}
              className="flex h-6 w-6 items-center justify-center rounded border border-red-500/20 text-red-300/80 transition hover:bg-red-500/10 hover:text-red-200"
              title="Delete card"
              aria-label="Delete card"
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export function KanbanCardPreview({ card }: { card: KanbanCardRecord }) {
  const checklist = checklistLabel(card);
  const runStatus = visibleRunStatus(card.agent_status);
  const labels = visibleLabels(card);
  const isBlocked = Boolean(card.blocked_by?.length || String(card.agent_status || "").toLowerCase() === "blocked");

  return (
    <article
      className={cn(
        "w-[256px] rounded-lg border bg-[#14141a] p-2.5 shadow-2xl shadow-black/50 ring-1 ring-sky-400/25",
        isBlocked ? "border-red-400/60" : "border-sky-400/70",
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-sky-400/20 bg-sky-400/10 text-sky-200">
          <GripVertical size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <h4 className="min-w-0 flex-1 break-words text-[13px] font-semibold leading-snug text-zinc-100">{card.title}</h4>
            <span className={cn("shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-medium", priorityClassName(card.priority))}>
              {card.priority || "normal"}
            </span>
          </div>
          {card.description && (
            <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-zinc-400">{card.description}</p>
          )}
          <div className="mt-2 flex min-w-0 items-center gap-2 text-[10px] leading-none text-zinc-400">
            {card.assignee && <span className="min-w-0 truncate">{card.assignee}</span>}
            {card.due_at && (
              <span className="inline-flex min-w-0 items-center gap-1">
                <CalendarDays size={10} className="shrink-0" />
                <span className="truncate">{card.due_at}</span>
              </span>
            )}
            {checklist && (
              <span className="inline-flex shrink-0 items-center gap-1">
                <CheckSquare size={10} />
                {checklist}
              </span>
            )}
            {runStatus && (
              <span className={cn("inline-flex min-w-0 items-center gap-1 truncate", isBlocked ? "text-red-200" : "text-sky-200")}>
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                <span className="truncate">{runStatus}</span>
              </span>
            )}
          </div>
        </div>
      </div>

      {labels.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {labels.slice(0, 3).map((label) => (
            <span key={label} className="rounded-full border border-zinc-700 bg-zinc-950/70 px-1.5 py-0.5 text-[9px] text-zinc-400">
              {label}
            </span>
          ))}
          {labels.length > 3 && <span className="text-[9px] text-zinc-500">+{labels.length - 3}</span>}
        </div>
      )}
    </article>
  );
}
