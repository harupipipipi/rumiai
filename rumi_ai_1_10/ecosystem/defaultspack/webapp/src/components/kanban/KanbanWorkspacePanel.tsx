import { AlertCircle, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { kanbanResources } from "../../features/kanban/resources/kanbanResources";
import type { KanbanBoardResponse, KanbanBoardScope, KanbanCard, KanbanColumn, KanbanMovePayload, ModelProfile } from "../../lib/api";
import { cn } from "../../lib/cn";
import { HISTORY_CHAT_KANBAN_DROP_EVENT, parseHistoryChatDragPayload } from "../../lib/historyComposer";
import { KanbanBoard } from "./KanbanBoard";
import { KanbanCardDrawer, type KanbanAgentAction } from "./KanbanCardDrawer";
import { KanbanToolbar, type KanbanScopeOption } from "./KanbanToolbar";

type DrawerState =
  | { mode: "create"; columnId: string }
  | { mode: "edit"; cardId: string }
  | null;

export type KanbanWorkspacePanelProps = {
  activeConversationId: string | null;
  activeConversationTitle: string;
  initialScope?: KanbanBoardScope | null;
  initialScopeLabel?: string | null;
  conversationOptions?: KanbanConversationOption[];
  groupOptions?: KanbanGroupOption[];
  workspaceId?: string | null;
  workspaceLabel?: string | null;
  workspaceRoot?: string | null;
  companyId?: string | null;
  modelId: string;
  modelProfiles: ModelProfile[];
  onOpenChat?: (conversationId: string) => void;
  onScopeChange?: (scope: KanbanBoardScope, label?: string | null) => void;
  onOpenSettings?: () => void;
};

export type KanbanConversationOption = {
  id: string;
  title: string;
  groupId?: string | null;
};

export type KanbanGroupOption = {
  id: string;
  title: string;
  description?: string | null;
};

const DEFAULT_COLUMN_DEFS = [
  { key: "backlog", title: "Backlog", done: false },
  { key: "doing", title: "Doing", done: false, wip_limit: 4 },
  { key: "review", title: "Review", done: false, wip_limit: 6 },
  { key: "done", title: "Done", done: true },
] as const;

export const KANBAN_API_UNAVAILABLE_NOTICE = "Kanban API is not available yet; using local draft persistence.";
const INITIAL_BOARD_RETRY_DELAY_MS = 650;

type BoardLoadOutcome = "remote" | "remote-after-retry" | "local";

type LoadKanbanBoardOptions = {
  scope: KanbanBoardScope;
  title: string;
  workspaceLabel?: string | null;
  retryOnFirstFailure?: boolean;
  retryDelayMs?: number;
  getOrCreateBoard?: (scope: KanbanBoardScope) => Promise<KanbanBoardResponse>;
  delay?: (ms: number) => Promise<void>;
  setBoardData: (board: KanbanBoardResponse) => void;
  setBackendAvailable: (available: boolean) => void;
  setNotice: (notice: string | null) => void;
};

function cleanId(value: string): string {
  return value.trim().replace(/[^a-zA-Z0-9_.:-]+/g, "-").slice(0, 96) || "default";
}

function scopeKey(scope: KanbanBoardScope): string {
  return `${scope.type}:${scope.id}`;
}

function storageKey(scope: KanbanBoardScope): string {
  return `defaultspack.kanban.${scope.type}.${cleanId(scope.id)}.v1`;
}

function now(): number {
  return Date.now();
}

function titleForScope(scope: KanbanBoardScope, title: string, workspaceLabel?: string | null): string {
  if (scope.type === "conversation") return `${title || "Current Chat"} board`;
  if (scope.type === "workspace") return `${workspaceLabel || scope.id} board`;
  if (scope.type === "company") return "Company board";
  if (scope.type === "group") return `${title || scope.id} group board`;
  return "All Rumi Runs";
}

function defaultScopeFor({
  activeConversationId,
  workspaceId,
  companyId,
}: Pick<KanbanWorkspacePanelProps, "activeConversationId" | "workspaceId" | "companyId">): KanbanBoardScope {
  if (workspaceId) return { type: "workspace", id: workspaceId };
  if (activeConversationId) return { type: "conversation", id: activeConversationId };
  if (companyId) return { type: "company", id: companyId };
  return { type: "global", id: "default" };
}

function createLocalBoard(scope: KanbanBoardScope, title: string, workspaceLabel?: string | null): KanbanBoardResponse {
  const boardId = `local-${scope.type}-${cleanId(scope.id)}`;
  const created = now();
  return {
    board: {
      board_id: boardId,
      scope_type: scope.type,
      scope_id: scope.id,
      title: titleForScope(scope, title, workspaceLabel),
      metadata: { local_fallback: true },
      created_at: created,
      updated_at: created,
    },
    columns: DEFAULT_COLUMN_DEFS.map((column, index) => ({
      column_id: `${boardId}-${column.key}`,
      board_id: boardId,
      title: column.title,
      position: (index + 1) * 1000,
      done: column.done,
      wip_limit: "wip_limit" in column ? column.wip_limit : null,
      created_at: created,
      updated_at: created,
    })),
    cards: [],
    events: [],
  };
}

function isBoardResponse(value: unknown): value is KanbanBoardResponse {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<KanbanBoardResponse>;
  return Boolean(record.board && Array.isArray(record.columns) && Array.isArray(record.cards));
}

function loadLocalBoard(scope: KanbanBoardScope, title: string, workspaceLabel?: string | null): KanbanBoardResponse {
  try {
    const raw = localStorage.getItem(storageKey(scope));
    const parsed = raw ? JSON.parse(raw) : null;
    if (isBoardResponse(parsed)) return normalizeBoard(parsed, scope, title, workspaceLabel);
  } catch {
    // Local fallback is best-effort.
  }
  return createLocalBoard(scope, title, workspaceLabel);
}

function saveLocalBoard(scope: KanbanBoardScope, board: KanbanBoardResponse) {
  try {
    localStorage.setItem(storageKey(scope), JSON.stringify(board));
  } catch {
    // Local fallback is best-effort.
  }
}

function normalizeBoard(
  board: KanbanBoardResponse,
  scope: KanbanBoardScope,
  title: string,
  workspaceLabel?: string | null,
): KanbanBoardResponse {
  if (board.columns.length > 0) {
    return {
      ...board,
      board: {
        ...board.board,
        title: board.board.title || titleForScope(scope, title, workspaceLabel),
      },
      columns: [...board.columns].sort((a, b) => a.position - b.position),
      cards: normalizeCardPositions(board.cards, board.columns),
    };
  }
  const fallback = createLocalBoard(scope, title, workspaceLabel);
  return {
    ...board,
    board: { ...board.board, title: board.board.title || fallback.board.title },
    columns: fallback.columns.map((column) => ({ ...column, board_id: board.board.board_id, column_id: `${board.board.board_id}-${column.title.toLowerCase()}` })),
    cards: [],
  };
}

function sortCards(cards: KanbanCard[]): KanbanCard[] {
  return [...cards].sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || (a.created_at ?? 0) - (b.created_at ?? 0) || a.card_id.localeCompare(b.card_id));
}

function normalizeCardPositions(cards: KanbanCard[], columns: KanbanColumn[]): KanbanCard[] {
  const normalized: KanbanCard[] = [];
  for (const column of columns) {
    sortCards(cards.filter((card) => card.column_id === column.column_id)).forEach((card, index) => {
      normalized.push({ ...card, position: (index + 1) * 1000 });
    });
  }
  const knownColumnIds = new Set(columns.map((column) => column.column_id));
  normalized.push(...cards.filter((card) => !knownColumnIds.has(card.column_id)));
  return normalized;
}

function insertCard(board: KanbanBoardResponse, card: KanbanCard): KanbanBoardResponse {
  const cards = board.cards.some((item) => item.card_id === card.card_id)
    ? board.cards.map((item) => item.card_id === card.card_id ? { ...item, ...card } : item)
    : [...board.cards, card];
  return { ...board, cards: normalizeCardPositions(cards, board.columns) };
}

function removeCard(board: KanbanBoardResponse, cardId: string): KanbanBoardResponse {
  return { ...board, cards: normalizeCardPositions(board.cards.filter((card) => card.card_id !== cardId), board.columns) };
}

function columnIdForTitle(board: KanbanBoardResponse, title: string): string {
  const normalized = title.toLowerCase();
  return board.columns.find((column) => column.title.toLowerCase() === normalized)?.column_id
    ?? board.columns[0]?.column_id
    ?? "";
}

function moveCardLocally(
  board: KanbanBoardResponse,
  cardId: string,
  targetColumnId: string,
  targetIndex?: number,
): KanbanBoardResponse {
  const moving = board.cards.find((card) => card.card_id === cardId);
  if (!moving) return board;
  const otherTargetCards = sortCards(board.cards.filter((card) => card.card_id !== cardId && card.column_id === targetColumnId));
  const clampedIndex = Math.max(0, Math.min(targetIndex ?? otherTargetCards.length, otherTargetCards.length));
  const nextTargetCards = [...otherTargetCards];
  nextTargetCards.splice(clampedIndex, 0, { ...moving, column_id: targetColumnId, updated_at: now() });
  const otherCards = board.cards.filter((card) => card.card_id !== cardId && card.column_id !== targetColumnId);
  return {
    ...board,
    cards: normalizeCardPositions([...otherCards, ...nextTargetCards], board.columns),
  };
}

function movePayloadFor(board: KanbanBoardResponse, cardId: string): KanbanMovePayload {
  const movedCard = board.cards.find((card) => card.card_id === cardId);
  if (!movedCard) return { column_id: "" };
  const columnCards = sortCards(board.cards.filter((card) => card.column_id === movedCard.column_id));
  const index = columnCards.findIndex((card) => card.card_id === cardId);
  return {
    column_id: movedCard.column_id,
    position: movedCard.position,
    after_card_id: index > 0 ? columnCards[index - 1]?.card_id ?? null : null,
    before_card_id: index >= 0 && index < columnCards.length - 1 ? columnCards[index + 1]?.card_id ?? null : null,
  };
}

function cardMatchesSearch(card: KanbanCard, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  const haystack = [
    card.title,
    card.description ?? "",
    card.priority ?? "",
    card.assignee ?? "",
    card.agent_status ?? "",
    card.branch ?? "",
    card.source_type ?? "",
    String(card.metadata?.conversation_title ?? ""),
    String(card.metadata?.conversation_group_id ?? ""),
    String((card.metadata?.conversation_import as Record<string, unknown> | undefined)?.conversation_title ?? ""),
    String((card.metadata?.conversation_import as Record<string, unknown> | undefined)?.conversation_group_id ?? ""),
    ...(card.labels ?? []),
  ].join(" ").toLowerCase();
  return haystack.includes(normalized);
}

function scopeOptionMatchesSearch(option: KanbanScopeOption, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [
    option.label,
    option.description,
    option.scope.type,
    option.scope.id,
  ].join(" ").toLowerCase().includes(normalized);
}

function runningAgentStatus(status: string | null | undefined): boolean {
  const normalized = String(status || "").toLowerCase();
  return ["queued", "running", "in_progress", "waiting_approval", "ready"].includes(normalized);
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

function boardLoadFallbackNotice(error: unknown): string {
  return error instanceof Error ? KANBAN_API_UNAVAILABLE_NOTICE : "Using local draft persistence.";
}

export async function loadKanbanBoardWithFallback({
  scope,
  title,
  workspaceLabel,
  retryOnFirstFailure = false,
  retryDelayMs = INITIAL_BOARD_RETRY_DELAY_MS,
  getOrCreateBoard = kanbanResources.getOrCreateBoard,
  delay = wait,
  setBoardData,
  setBackendAvailable,
  setNotice,
}: LoadKanbanBoardOptions): Promise<BoardLoadOutcome> {
  const loadRemoteBoard = async (outcome: BoardLoadOutcome): Promise<BoardLoadOutcome> => {
    const result = await getOrCreateBoard(scope);
    setBoardData(normalizeBoard(result, scope, title, workspaceLabel));
    setBackendAvailable(true);
    setNotice(null);
    return outcome;
  };

  try {
    return await loadRemoteBoard("remote");
  } catch (error) {
    setBackendAvailable(false);
    setBoardData(loadLocalBoard(scope, title, workspaceLabel));
    if (!retryOnFirstFailure) {
      setNotice(boardLoadFallbackNotice(error));
      return "local";
    }
  }

  await delay(retryDelayMs);

  try {
    return await loadRemoteBoard("remote-after-retry");
  } catch (error) {
    setBackendAvailable(false);
    setNotice(boardLoadFallbackNotice(error));
    return "local";
  }
}

export function KanbanWorkspacePanel({
  activeConversationId,
  activeConversationTitle,
  initialScope,
  initialScopeLabel,
  conversationOptions = [],
  groupOptions = [],
  workspaceId,
  workspaceLabel,
  workspaceRoot,
  companyId,
  modelId,
  modelProfiles,
  onOpenChat,
  onScopeChange,
  onOpenSettings,
}: KanbanWorkspacePanelProps) {
  const [scope, setScope] = useState<KanbanBoardScope>(() => initialScope ?? defaultScopeFor({ activeConversationId, workspaceId, companyId }));
  const [boardData, setBoardData] = useState<KanbanBoardResponse | null>(null);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [drawer, setDrawer] = useState<DrawerState>(null);
  const loadRequestIdRef = useRef(0);

  const defaultScope = useMemo(
    () => defaultScopeFor({ activeConversationId, workspaceId, companyId }),
    [activeConversationId, companyId, workspaceId],
  );

  useEffect(() => {
    if (!initialScope) return;
    setScope((current) => scopeKey(current) === scopeKey(initialScope) ? current : initialScope);
  }, [initialScope]);

  useEffect(() => {
    setScope((current) => {
      if (current.type === "conversation" && activeConversationId && current.id !== activeConversationId) {
        return { type: "conversation", id: activeConversationId };
      }
      if (current.type === "workspace" && workspaceId && current.id !== workspaceId) {
        return { type: "workspace", id: workspaceId };
      }
      if (current.type === "company" && companyId && current.id !== companyId) {
        return { type: "company", id: companyId };
      }
      if ((current.type === "conversation" && !activeConversationId) || (current.type === "workspace" && !workspaceId) || (current.type === "company" && !companyId)) {
        return defaultScope;
      }
      return current;
    });
  }, [activeConversationId, companyId, defaultScope, workspaceId]);

  const scopeOptions = useMemo<KanbanScopeOption[]>(() => {
    const activeScopeOption: KanbanScopeOption = {
      scope,
      label: initialScopeLabel || (scope.type === "group" ? "Group" : scope.type === "conversation" ? "Chat" : scope.type),
      description: scope.id,
    };
    const baseOptions: KanbanScopeOption[] = [
      {
        scope: { type: "global", id: "default" },
        label: "All Rumi Runs",
        description: "registered runs",
      },
      {
      scope: { type: "conversation", id: activeConversationId ?? "missing" },
      label: "Current Chat",
      description: activeConversationTitle || "conversation",
      disabled: !activeConversationId,
    },
    ...groupOptions.map((group) => ({
      scope: { type: "group" as const, id: group.id },
      label: group.title || group.id,
      description: group.description || "group board",
    })),
    ...conversationOptions.map((conversation) => ({
      scope: { type: "conversation" as const, id: conversation.id },
      label: conversation.title || conversation.id,
      description: conversation.groupId ? `chat in ${conversation.groupId}` : "chat board",
    })),
    {
      scope: { type: "workspace", id: workspaceId ?? "missing" },
      label: "Workspace",
      description: workspaceLabel || workspaceRoot || "workspace",
      disabled: !workspaceId,
    },
    {
      scope: { type: "company", id: companyId ?? "missing" },
      label: "Company",
      description: companyId || "company",
      disabled: !companyId,
    },
    ];
    const byKey = new Map<string, KanbanScopeOption>();
    for (const option of [activeScopeOption, ...baseOptions]) {
      byKey.set(scopeKey(option.scope), option);
    }
    return [...byKey.values()].filter((option) => scopeKey(option.scope) === scopeKey(scope) || scopeOptionMatchesSearch(option, search));
  }, [activeConversationId, activeConversationTitle, companyId, conversationOptions, groupOptions, initialScopeLabel, scope, search, workspaceId, workspaceLabel, workspaceRoot]);

  const loadBoard = useCallback(async (options?: { retryOnFirstFailure?: boolean }) => {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    const isCurrentRequest = () => loadRequestIdRef.current === requestId;

    setLoading(true);
    setNotice(null);
    try {
      await loadKanbanBoardWithFallback({
        scope,
        title: activeConversationTitle,
        workspaceLabel,
        retryOnFirstFailure: options?.retryOnFirstFailure,
        setBoardData: (board) => {
          if (isCurrentRequest()) setBoardData(board);
        },
        setBackendAvailable: (available) => {
          if (isCurrentRequest()) setBackendAvailable(available);
        },
        setNotice: (nextNotice) => {
          if (isCurrentRequest()) setNotice(nextNotice);
        },
      });
    } finally {
      if (isCurrentRequest()) setLoading(false);
    }
  }, [activeConversationTitle, scope, workspaceLabel]);

  useEffect(() => {
    void loadBoard({ retryOnFirstFailure: true });
  }, [loadBoard]);

  useEffect(() => {
    if (!boardData || backendAvailable) return;
    saveLocalBoard(scope, boardData);
  }, [backendAvailable, boardData, scope]);

  const filteredBoardData = useMemo<KanbanBoardResponse | null>(() => {
    if (!boardData) return null;
    return {
      ...boardData,
      cards: boardData.cards.filter((card) => cardMatchesSearch(card, search)),
    };
  }, [boardData, search]);

  const activeDrawerCard = drawer?.mode === "edit"
    ? boardData?.cards.find((card) => card.card_id === drawer.cardId) ?? null
    : null;
  const defaultColumnId = drawer?.mode === "create"
    ? drawer.columnId
    : boardData?.columns[0]?.column_id ?? "";

  const openCreateCard = (columnId?: string) => {
    const targetColumnId = columnId ?? boardData?.columns[0]?.column_id ?? "";
    if (!targetColumnId) return;
    setDrawer({ mode: "create", columnId: targetColumnId });
  };

  const commitScopeChange = (nextScope: KanbanBoardScope) => {
    const option = scopeOptions.find((candidate) => scopeKey(candidate.scope) === scopeKey(nextScope));
    setScope(nextScope);
    setDrawer(null);
    onScopeChange?.(nextScope, option?.label ?? null);
  };

  const handleCreateCard = async (updates: Partial<KanbanCard>) => {
    if (!boardData) return;
    const targetColumnId = updates.column_id || defaultColumnId || boardData.columns[0]?.column_id;
    if (!targetColumnId) return;
    const created = now();
    const localCard: KanbanCard = {
      card_id: `local-card-${created}-${Math.random().toString(36).slice(2)}`,
      board_id: boardData.board.board_id,
      column_id: targetColumnId,
      position: boardData.cards.filter((card) => card.column_id === targetColumnId).length * 1000 + 1000,
      title: updates.title || "Untitled card",
      description: updates.description ?? null,
      priority: updates.priority ?? "normal",
      assignee: updates.assignee ?? null,
      due_at: updates.due_at ?? null,
      labels: updates.labels ?? [],
      checklist: updates.checklist ?? [],
      source_type: "manual",
      conversation_id: activeConversationId,
      workspace_id: workspaceId ?? null,
      company_id: companyId ?? null,
      metadata: { model_id: modelId },
      created_at: created,
      updated_at: created,
    };

    setBusy(true);
    try {
      if (backendAvailable) {
        const saved = await kanbanResources.createCard(boardData.board.board_id, {
          ...localCard,
          card_id: undefined,
        });
        setBoardData((current) => current ? insertCard(current, saved) : current);
      } else {
        setBoardData((current) => current ? insertCard(current, localCard) : current);
      }
      setDrawer(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Failed to create Kanban card.");
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateCard = async (card: KanbanCard, updates: Partial<KanbanCard>) => {
    if (!boardData) return;
    const targetColumnId = updates.column_id ?? card.column_id;
    const columnChanged = targetColumnId !== card.column_id;
    const { column_id: _columnId, ...cardUpdates } = updates;
    const optimisticCard: KanbanCard = { ...card, ...updates, column_id: targetColumnId, updated_at: now() };
    const optimisticBoard = columnChanged
      ? moveCardLocally(insertCard(boardData, optimisticCard), card.card_id, targetColumnId)
      : insertCard(boardData, optimisticCard);

    setBusy(true);
    setBoardData(optimisticBoard);
    try {
      if (backendAvailable) {
        const saved = await kanbanResources.updateCard(card.card_id, cardUpdates);
        if (columnChanged) {
          const moved = await kanbanResources.moveCard(card.card_id, { column_id: targetColumnId });
          setBoardData(normalizeBoard(moved, scope, activeConversationTitle, workspaceLabel));
        } else {
          setBoardData((current) => current ? insertCard(current, saved) : current);
        }
      }
      setDrawer(null);
    } catch (error) {
      setBoardData(boardData);
      setNotice(error instanceof Error ? error.message : "Failed to update Kanban card.");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = (updates: Partial<KanbanCard>) => {
    if (drawer?.mode === "edit" && activeDrawerCard) {
      void handleUpdateCard(activeDrawerCard, updates);
      return;
    }
    void handleCreateCard(updates);
  };

  const handleMoveCard = async (cardId: string, columnId: string, targetIndex?: number) => {
    if (!boardData) return;
    const nextBoard = moveCardLocally(boardData, cardId, columnId, targetIndex);
    const payload = movePayloadFor(nextBoard, cardId);
    setBoardData(nextBoard);
    try {
      if (backendAvailable) {
        const moved = await kanbanResources.moveCard(cardId, payload);
        setBoardData(normalizeBoard(moved, scope, activeConversationTitle, workspaceLabel));
      }
    } catch (error) {
      setBoardData(boardData);
      setNotice(error instanceof Error ? error.message : "Failed to move Kanban card.");
    }
  };

  const handleDeleteCard = async (cardId: string) => {
    if (!boardData) return;
    const previous = boardData;
    setBusy(true);
    setBoardData(removeCard(boardData, cardId));
    try {
      if (backendAvailable) {
        await kanbanResources.deleteCard(cardId);
      }
      setDrawer(null);
    } catch (error) {
      setBoardData(previous);
      setNotice(error instanceof Error ? error.message : "Failed to delete Kanban card.");
    } finally {
      setBusy(false);
    }
  };

  const localAgentUpdate = (card: KanbanCard, action: KanbanAgentAction): KanbanCard => {
    const statusByAction: Record<KanbanAgentAction, string> = {
      start: "running",
      refresh: card.agent_status || "idle",
      ready: "ready",
      apply: "applied",
      dismiss: "dismissed",
    };
    const columnByAction: Partial<Record<KanbanAgentAction, string>> = {
      start: "Doing",
      ready: "Review",
      apply: "Done",
      dismiss: "Backlog",
    };
    const nextColumn = boardData && columnByAction[action] ? columnIdForTitle(boardData, columnByAction[action]) : card.column_id;
    return {
      ...card,
      column_id: nextColumn || card.column_id,
      agent_status: statusByAction[action],
      agent_session_id: action === "start" ? card.agent_session_id ?? `local-session-${now()}` : card.agent_session_id,
      updated_at: now(),
    };
  };

  const handleAgentAction = async (card: KanbanCard, action: KanbanAgentAction) => {
    if (!boardData) return;
    setBusy(true);
    try {
      if (backendAvailable) {
        const payload = {
          task: card.title,
          model: modelId,
          conversation_id: activeConversationId,
          workspace_id: workspaceId,
          company_id: companyId,
        };
        const saved = action === "start"
          ? await kanbanResources.startAgent(card.card_id, payload)
          : action === "refresh"
            ? await kanbanResources.getAgentStatus(card.card_id)
            : action === "ready"
              ? await kanbanResources.markAgentReady(card.card_id)
              : action === "apply"
                ? await kanbanResources.applyAgent(card.card_id)
                : await kanbanResources.dismissAgent(card.card_id);
        setBoardData((current) => current ? insertCard(current, saved) : current);
      } else {
        const updated = localAgentUpdate(card, action);
        setBoardData((current) => {
          if (!current) return current;
          const withCard = insertCard(current, updated);
          return updated.column_id !== card.column_id ? moveCardLocally(withCard, card.card_id, updated.column_id) : withCard;
        });
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Kanban agent action failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleHistoryChatDrop = useCallback(async (columnId: string, rawPayload: string) => {
    if (!boardData) return;
    const payload = parseHistoryChatDragPayload(rawPayload);
    if (!payload?.conversationId) {
      setNotice("Dropped history item could not be read.");
      return;
    }
    setBusy(true);
    try {
      if (backendAvailable) {
        const imported = await kanbanResources.importConversation(boardData.board.board_id, {
          conversation_id: payload.conversationId,
          column_id: columnId,
          title: payload.title,
          model: modelId,
          workspace_id: workspaceId ?? null,
          company_id: companyId ?? null,
          use_ai: true,
        });
        setBoardData(normalizeBoard(imported, scope, activeConversationTitle, workspaceLabel));
        setNotice(`Imported "${payload.title || payload.conversationId}" into Kanban.`);
        return;
      }
      const created = now();
      const localCard: KanbanCard = {
        card_id: `local-history-${created}-${Math.random().toString(36).slice(2)}`,
        board_id: boardData.board.board_id,
        column_id: columnId,
        position: boardData.cards.filter((card) => card.column_id === columnId).length * 1000 + 1000,
        title: payload.title || "Imported conversation",
        description: "History conversation linked to this Kanban board.",
        priority: "normal",
        assignee: null,
        due_at: null,
        labels: ["conversation"],
        checklist: [],
        source_type: "conversation",
        source_id: payload.conversationId,
        conversation_id: payload.conversationId,
        workspace_id: workspaceId ?? null,
        company_id: companyId ?? null,
        metadata: {
          conversation_title: payload.title,
          conversation_group_id: payload.groupId,
          model_id: modelId,
          local_fallback: true,
        },
        created_at: created,
        updated_at: created,
      };
      setBoardData((current) => current ? insertCard(current, localCard) : current);
      setNotice("Kanban API is unavailable, so the dropped chat was saved as a local draft card.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Failed to import history chat into Kanban.");
    } finally {
      setBusy(false);
    }
  }, [activeConversationTitle, backendAvailable, boardData, companyId, modelId, scope, workspaceId, workspaceLabel]);

  useEffect(() => {
    const handleGlobalHistoryChatDrop = (event: Event) => {
      const detail = (event as CustomEvent<{ columnId?: string; rawPayload?: string }>).detail;
      if (!detail?.columnId || !detail.rawPayload) return;
      void handleHistoryChatDrop(detail.columnId, detail.rawPayload);
    };
    window.addEventListener(HISTORY_CHAT_KANBAN_DROP_EVENT, handleGlobalHistoryChatDrop);
    return () => window.removeEventListener(HISTORY_CHAT_KANBAN_DROP_EVENT, handleGlobalHistoryChatDrop);
  }, [handleHistoryChatDrop]);

  const agentPollIds = useMemo(
    () => (boardData?.cards ?? []).filter((card) => runningAgentStatus(card.agent_status)).map((card) => card.card_id).sort().join("|"),
    [boardData?.cards],
  );

  useEffect(() => {
    if (!backendAvailable || !agentPollIds) return;
    const ids = agentPollIds.split("|").filter(Boolean);
    const interval = window.setInterval(() => {
      void Promise.all(ids.map((cardId) => kanbanResources.getAgentStatus(cardId).catch(() => null))).then((cards) => {
        setBoardData((current) => {
          if (!current) return current;
          return cards.reduce((next, card) => card ? insertCard(next, card) : next, current);
        });
      });
    }, 12_000);
    return () => window.clearInterval(interval);
  }, [agentPollIds, backendAvailable]);

  return (
    <section className="relative flex min-h-0 flex-1 overflow-hidden rounded-lg border border-zinc-800/70 bg-[#09090b]">
      <div className="flex min-w-0 flex-1 flex-col">
        <KanbanToolbar
          board={boardData?.board ?? null}
          scope={scope}
          scopeOptions={scopeOptions}
          loading={loading}
          backendAvailable={backendAvailable}
          search={search}
          onSearchChange={setSearch}
          onScopeChange={commitScopeChange}
          onCreateCard={() => openCreateCard()}
          onReload={() => void loadBoard()}
          onOpenSettings={() => onOpenSettings?.()}
        />

        {notice && (
          <div className="mx-3 mt-3 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <p className="min-w-0 flex-1 whitespace-pre-wrap leading-5">{notice}</p>
            <button
              type="button"
              onClick={() => setNotice(null)}
              className="shrink-0 text-amber-200/70 hover:text-amber-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {loading && !boardData ? (
          <div className="flex flex-1 items-center justify-center text-zinc-500">
            <Loader2 size={18} className="mr-2 animate-spin" />
            <span className="text-[12px]">Loading Kanban</span>
          </div>
        ) : filteredBoardData ? (
          <KanbanBoard
            columns={filteredBoardData.columns}
            cards={filteredBoardData.cards}
            onCreateCard={openCreateCard}
            onEditCard={(card) => setDrawer({ mode: "edit", cardId: card.card_id })}
            onMoveCard={(cardId, columnId, targetIndex) => void handleMoveCard(cardId, columnId, targetIndex)}
            onHistoryChatDrop={(columnId, rawPayload) => void handleHistoryChatDrop(columnId, rawPayload)}
            onOpenChat={onOpenChat}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-[12px] text-zinc-600">No board loaded.</div>
        )}
      </div>

      {drawer && boardData && (
        <KanbanCardDrawer
          card={activeDrawerCard}
          columns={boardData.columns}
          defaultColumnId={defaultColumnId}
          modelId={modelId}
          modelProfiles={modelProfiles}
          busy={busy}
          onClose={() => setDrawer(null)}
          onSave={handleSave}
          onDelete={(cardId) => void handleDeleteCard(cardId)}
          onAgentAction={(card, action) => void handleAgentAction(card, action)}
          onOpenChat={onOpenChat}
        />
      )}

      {busy && (
        <div className={cn("pointer-events-none absolute right-3 top-3 rounded-full border border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[10px] text-zinc-400 shadow-lg")}>
          Saving
        </div>
      )}
    </section>
  );
}
