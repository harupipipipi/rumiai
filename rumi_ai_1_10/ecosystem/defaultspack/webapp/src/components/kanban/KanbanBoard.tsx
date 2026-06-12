import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import type { KanbanCard, KanbanColumn as KanbanColumnRecord } from "../../lib/api";
import { KanbanColumn } from "./KanbanColumn";

function sortedColumns(columns: KanbanColumnRecord[]): KanbanColumnRecord[] {
  return [...columns].sort((a, b) => a.position - b.position || a.title.localeCompare(b.title));
}

function sortedCards(cards: KanbanCard[]): KanbanCard[] {
  return [...cards].sort((a, b) => a.position - b.position || (a.created_at ?? 0) - (b.created_at ?? 0) || a.card_id.localeCompare(b.card_id));
}

export function KanbanBoard({
  columns,
  cards,
  onCreateCard,
  onEditCard,
  onMoveCard,
}: {
  columns: KanbanColumnRecord[];
  cards: KanbanCard[];
  onCreateCard: (columnId: string) => void;
  onEditCard: (card: KanbanCard) => void;
  onMoveCard: (cardId: string, columnId: string, targetIndex?: number) => void;
}) {
  const orderedColumns = sortedColumns(columns);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const activeId = String(event.active.id);
    const overId = event.over ? String(event.over.id) : "";
    if (!overId || activeId === overId) return;

    const activeCard = cards.find((card) => card.card_id === activeId);
    if (!activeCard) return;
    const overCard = cards.find((card) => card.card_id === overId);
    const overColumn = columns.find((column) => column.column_id === overId);
    const targetColumnId = overColumn?.column_id ?? overCard?.column_id ?? activeCard.column_id;
    const targetCards = sortedCards(cards.filter((card) => card.column_id === targetColumnId && card.card_id !== activeId));
    const targetIndex = overCard
      ? Math.max(0, targetCards.findIndex((card) => card.card_id === overCard.card_id))
      : targetCards.length;

    onMoveCard(activeId, targetColumnId, targetIndex);
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={handleDragEnd}>
      <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto overflow-y-hidden px-3 pb-3">
        {orderedColumns.map((column) => (
          <KanbanColumn
            key={column.column_id}
            column={column}
            cards={sortedCards(cards.filter((card) => card.column_id === column.column_id))}
            columns={orderedColumns}
            onCreateCard={onCreateCard}
            onEditCard={onEditCard}
            onMoveToColumn={(cardId, columnId) => onMoveCard(cardId, columnId)}
          />
        ))}
      </div>
    </DndContext>
  );
}
