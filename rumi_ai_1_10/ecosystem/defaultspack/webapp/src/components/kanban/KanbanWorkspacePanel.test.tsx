import test from "node:test";
import assert from "node:assert/strict";

import type { KanbanBoardResponse, KanbanBoardScope } from "../../lib/api";
import { filterKanbanScopeOptions, type KanbanScopeOption } from "./KanbanToolbar";
import { KANBAN_API_UNAVAILABLE_NOTICE, loadKanbanBoardWithFallback } from "./KanbanWorkspacePanel";

const scope: KanbanBoardScope = { type: "conversation", id: "conv-1" };

function remoteBoard(boardId = "board-1"): KanbanBoardResponse {
  return {
    board: {
      board_id: boardId,
      scope_type: scope.type,
      scope_id: scope.id,
      title: "Persisted board",
      metadata: {},
      created_at: 1,
      updated_at: 2,
    },
    columns: [
      {
        column_id: `${boardId}-backlog`,
        board_id: boardId,
        title: "Backlog",
        position: 1000,
        done: false,
        created_at: 1,
        updated_at: 2,
      },
    ],
    cards: [],
    events: [],
  };
}

function recorder() {
  const boards: KanbanBoardResponse[] = [];
  const backendStates: boolean[] = [];
  const notices: Array<string | null> = [];

  return {
    boards,
    backendStates,
    notices,
    setBoardData: (board: KanbanBoardResponse) => boards.push(board),
    setBackendAvailable: (available: boolean) => backendStates.push(available),
    setNotice: (notice: string | null) => notices.push(notice),
  };
}

test("initial Kanban load retries silently and restores backend persistence", async () => {
  const states = recorder();
  const delays: number[] = [];
  let calls = 0;

  const outcome = await loadKanbanBoardWithFallback({
    scope,
    title: "Current Chat",
    retryOnFirstFailure: true,
    retryDelayMs: 25,
    getOrCreateBoard: async () => {
      calls += 1;
      if (calls === 1) throw new Error("route not ready");
      return remoteBoard();
    },
    delay: async (ms) => {
      delays.push(ms);
    },
    setBoardData: states.setBoardData,
    setBackendAvailable: states.setBackendAvailable,
    setNotice: states.setNotice,
  });

  assert.equal(outcome, "remote-after-retry");
  assert.equal(calls, 2);
  assert.deepEqual(delays, [25]);
  assert.equal(states.boards[0]?.board.metadata?.local_fallback, true);
  assert.equal(states.boards[states.boards.length - 1]?.board.board_id, "board-1");
  assert.deepEqual(states.backendStates, [false, true]);
  assert.deepEqual(states.notices, [null]);
});

test("initial Kanban load shows fallback notice only after retry also fails", async () => {
  const states = recorder();
  let calls = 0;

  const outcome = await loadKanbanBoardWithFallback({
    scope,
    title: "Current Chat",
    retryOnFirstFailure: true,
    retryDelayMs: 10,
    getOrCreateBoard: async () => {
      calls += 1;
      throw new Error("route not ready");
    },
    delay: async () => undefined,
    setBoardData: states.setBoardData,
    setBackendAvailable: states.setBackendAvailable,
    setNotice: states.setNotice,
  });

  assert.equal(outcome, "local");
  assert.equal(calls, 2);
  assert.equal(states.boards[0]?.board.metadata?.local_fallback, true);
  assert.deepEqual(states.backendStates, [false, false]);
  assert.deepEqual(states.notices, [KANBAN_API_UNAVAILABLE_NOTICE]);
});

test("manual Kanban reload keeps immediate local fallback notice", async () => {
  const states = recorder();
  let calls = 0;

  const outcome = await loadKanbanBoardWithFallback({
    scope,
    title: "Current Chat",
    retryOnFirstFailure: false,
    getOrCreateBoard: async () => {
      calls += 1;
      throw new Error("route not ready");
    },
    delay: async () => {
      throw new Error("manual reload should not delay");
    },
    setBoardData: states.setBoardData,
    setBackendAvailable: states.setBackendAvailable,
    setNotice: states.setNotice,
  });

  assert.equal(outcome, "local");
  assert.equal(calls, 1);
  assert.equal(states.boards[0]?.board.metadata?.local_fallback, true);
  assert.deepEqual(states.backendStates, [false]);
  assert.deepEqual(states.notices, [KANBAN_API_UNAVAILABLE_NOTICE]);
});

test("Kanban scope selector filters by label, description, type, and id", () => {
  const options: KanbanScopeOption[] = [
    { scope: { type: "global", id: "default" }, label: "All Rumi Runs", description: "registered runs" },
    { scope: { type: "conversation", id: "conv-alpha" }, label: "Alpha Chat", description: "chat board" },
    { scope: { type: "group", id: "design-team" }, label: "Design Team", description: "group board" },
  ];

  assert.deepEqual(filterKanbanScopeOptions(options, "alpha").map((option) => option.label), ["Alpha Chat"]);
  assert.deepEqual(filterKanbanScopeOptions(options, "group").map((option) => option.label), ["Design Team"]);
  assert.deepEqual(filterKanbanScopeOptions(options, "registered").map((option) => option.label), ["All Rumi Runs"]);
  assert.equal(filterKanbanScopeOptions(options, "missing").length, 0);
});
