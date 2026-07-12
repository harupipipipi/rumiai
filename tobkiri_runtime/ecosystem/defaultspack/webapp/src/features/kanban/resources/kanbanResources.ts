import { api } from "../../../lib/api";

export const kanbanResources = {
  getOrCreateBoard: api.kanbanGetOrCreateBoard,
  getBoard: api.kanbanGetBoard,
  createCard: api.kanbanCreateCard,
  updateCard: api.kanbanUpdateCard,
  moveCard: api.kanbanMoveCard,
  deleteCard: api.kanbanDeleteCard,
  createColumn: api.kanbanCreateColumn,
  updateColumn: api.kanbanUpdateColumn,
  deleteColumn: api.kanbanDeleteColumn,
  startAgent: api.kanbanStartAgent,
  getAgentStatus: api.kanbanGetAgentStatus,
  markAgentReady: api.kanbanMarkAgentReady,
  applyAgent: api.kanbanApplyAgent,
  dismissAgent: api.kanbanDismissAgent,
  syncRuns: api.kanbanSyncRuns,
  importConversation: api.kanbanImportConversation,
};

export type {
  KanbanBoard,
  KanbanBoardResponse,
  KanbanBoardScope,
  KanbanBoardScopeType,
  KanbanCard,
  KanbanChecklistItem,
  KanbanColumn,
  KanbanImportConversationPayload,
  KanbanMovePayload,
  KanbanPriority,
} from "../../../lib/api";
