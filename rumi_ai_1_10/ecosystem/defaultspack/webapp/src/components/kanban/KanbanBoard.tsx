import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  defaultDropAnimationSideEffects,
  pointerWithin,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { useState } from "react";

import type { KanbanCard, KanbanColumn as KanbanColumnRecord } from "../../lib/api";
import { KanbanCardPreview } from "./KanbanCard";
import { KanbanColumn } from "./KanbanColumn";

function sortedColumns(columns: KanbanColumnRecord[]): KanbanColumnRecord[] {
  return [...columns].sort((a, b) => a.position - b.position || a.title.localeCompare(b.title));
}

function sortedCards(cards: KanbanCard[]): KanbanCard[] {
  return [...cards].sort((a, b) => a.position - b.position || (a.created_at ?? 0) - (b.created_at ?? 0) || a.card_id.localeCompare(b.card_id));
}

const kanbanCollisionDetection: CollisionDetection = (args) => {
  const pointerCollisions = pointerWithin(args);
  return pointerCollisions.length > 0 ? pointerCollisions : closestCorners(args);
};

export function KanbanBoard({
  columns,
  cards,
  onCreateCard,
  onEditCard,
  onMoveCard,
  onDeleteCard,
  onHistoryChatDrop,
  onOpenChat,
}: {
  columns: KanbanColumnRecord[];
  cards: KanbanCard[];
  onCreateCard: (columnId: string) => void;
  onEditCard: (card: KanbanCard) => void;
  onMoveCard: (cardId: string, columnId: string, targetIndex?: number) => void;
  onDeleteCard?: (cardId: string) => void;
  onHistoryChatDrop?: (columnId: string, rawPayload: string) => void;
  onOpenChat?: (conversationId: string) => void;
}) {
  const orderedColumns = sortedColumns(columns);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const activeCard = activeCardId ? cards.find((card) => card.card_id === activeCardId) ?? null : null;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragStart = (event: DragStartEvent) => {
    const activeId = String(event.active.id);
    setActiveCardId(cards.some((card) => card.card_id === activeId) ? activeId : null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveCardId(null);
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
    <DndContext
      sensors={sensors}
      collisionDetection={kanbanCollisionDetection}
      onDragStart={handleDragStart}
      onDragCancel={() => setActiveCardId(null)}
      onDragEnd={handleDragEnd}
    >
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
            onDeleteCard={onDeleteCard}
            onHistoryChatDrop={onHistoryChatDrop}
            onOpenChat={onOpenChat}
          />
        ))}
      </div>
      <DragOverlay
        zIndex={80}
        dropAnimation={{
          sideEffects: defaultDropAnimationSideEffects({
            styles: {
              active: {
                opacity: "0.25",
              },
            },
          }),
        }}
      >
        {activeCard ? <KanbanCardPreview card={activeCard} /> : null}
      </DragOverlay>
    </DndContext>
  );
}
