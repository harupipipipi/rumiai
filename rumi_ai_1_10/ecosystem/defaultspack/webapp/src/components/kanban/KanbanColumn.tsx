import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useDroppable } from "@dnd-kit/core";
import { CircleCheck, Plus } from "lucide-react";

import type { KanbanCard as KanbanCardRecord, KanbanColumn as KanbanColumnRecord } from "../../lib/api";
import { cn } from "../../lib/cn";
import { KanbanCard } from "./KanbanCard";

export function KanbanColumn({
  column,
  cards,
  columns,
  onCreateCard,
  onEditCard,
  onMoveToColumn,
}: {
  column: KanbanColumnRecord;
  cards: KanbanCardRecord[];
  columns: KanbanColumnRecord[];
  onCreateCard: (columnId: string) => void;
  onEditCard: (card: KanbanCardRecord) => void;
  onMoveToColumn: (cardId: string, columnId: string) => void;
}) {
  const droppable = useDroppable({ id: column.column_id });
  const done = column.done === true || column.done === 1;
  const wipLimit = typeof column.wip_limit === "number" ? column.wip_limit : null;
  const isOverLimit = wipLimit !== null && cards.length > wipLimit;

  return (
    <section
      ref={droppable.setNodeRef}
      className={cn(
        "flex h-full min-h-0 w-[min(312px,78vw)] shrink-0 flex-col rounded-lg border bg-[#0d0d10]",
        droppable.isOver ? "border-zinc-500 bg-zinc-900/70" : "border-zinc-800/70",
      )}
    >
      <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-zinc-800/70 px-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            {done && <CircleCheck size={13} className="shrink-0 text-emerald-300" />}
            <h3 className="truncate text-[13px] font-semibold text-zinc-100">{column.title}</h3>
            <span className={cn(
              "shrink-0 rounded-full border px-1.5 py-0.5 text-[10px]",
              isOverLimit ? "border-amber-500/30 bg-amber-500/10 text-amber-200" : "border-zinc-800 text-zinc-500",
            )}>
              {cards.length}{wipLimit !== null ? `/${wipLimit}` : ""}
            </span>
          </div>
          {isOverLimit && <p className="mt-0.5 text-[10px] text-amber-300">WIP limit exceeded</p>}
        </div>
        <button
          type="button"
          onClick={() => onCreateCard(column.column_id)}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-100"
          title={`New card in ${column.title}`}
          aria-label={`New card in ${column.title}`}
        >
          <Plus size={13} />
        </button>
      </header>

      <SortableContext items={cards.map((card) => card.card_id)} strategy={verticalListSortingStrategy}>
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
          {cards.map((card) => (
            <KanbanCard
              key={card.card_id}
              card={card}
              columns={columns}
              onEdit={onEditCard}
              onMoveToColumn={onMoveToColumn}
            />
          ))}
          {cards.length === 0 && (
            <button
              type="button"
              onClick={() => onCreateCard(column.column_id)}
              className="flex min-h-28 items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-950/35 px-3 text-center text-[11px] text-zinc-600 transition hover:border-zinc-700 hover:text-zinc-400"
            >
              New card
            </button>
          )}
        </div>
      </SortableContext>
    </section>
  );
}
