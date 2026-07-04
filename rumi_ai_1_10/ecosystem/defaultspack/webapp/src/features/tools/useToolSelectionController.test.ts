import test from "node:test";
import assert from "node:assert/strict";

import {
  approvedToolSelectionReviewRequest,
  buildToolSelectionRequest,
  continueWithoutToolSelectionReviewRequest,
} from "./useToolSelectionController";
import type { PendingToolReview, ToolSelectionRequest } from "./types";

test("auto and review modes can carry turn tool includes without becoming manual", () => {
  const request = buildToolSelectionRequest({
    effectiveMode: "auto",
    conversationInclude: [{ kind: "service", id: "github" }],
    conversationExclude: [],
    turnTargets: [{ kind: "tool", id: "web_search" }],
    turnExclude: [],
    turnModeOverride: null,
  });

  assert.deepEqual(request, {
    mode: "auto",
    include: [
      { kind: "service", id: "github" },
      { kind: "tool", id: "web_search" },
    ],
    exclude: [],
    scope: "turn",
    must_use: false,
  });
});

test("review approval reuses only the authorized preview snapshot", () => {
  const pending = pendingReview({
    mode: "review",
    include: [{ kind: "tool", id: "tampered_client_tool" }],
    exclude: [{ kind: "tool", id: "blocked_tool" }],
    scope: "turn",
    must_use: true,
    preview_id: "client-preview",
  });

  assert.deepEqual(approvedToolSelectionReviewRequest(pending), {
    mode: "review",
    include: [],
    exclude: [{ kind: "tool", id: "blocked_tool" }],
    scope: "turn",
    must_use: false,
    preview_id: "server-preview",
  });
});

test("continue without tools does not send a preview id that would rehydrate tools", () => {
  const pending = pendingReview({
    mode: "review",
    include: [{ kind: "tool", id: "web_search" }],
    exclude: [],
    scope: "conversation",
    must_use: false,
    preview_id: "client-preview",
  });

  assert.deepEqual(continueWithoutToolSelectionReviewRequest(pending), {
    mode: "none",
    include: [],
    exclude: [],
    scope: "conversation",
    must_use: false,
  });
});

function pendingReview(request: ToolSelectionRequest): PendingToolReview {
  return {
    previewId: "server-preview",
    expiresAt: "2099-01-01T00:00:00Z",
    userText: "search",
    request,
    decision: {
      selected_tools: ["web_search"],
      selected_services: [],
      recommendations: [],
      permission_summary: { auto: 1, confirm: 0, block: 0 },
      metadata: {
        selection_id: "selection-1",
        mode: "review",
        strategy: "vector",
        stage: "vector",
      },
    },
    draft: { input: "search", attachments: [], droppedWidgets: [] },
    createdAt: 1,
  };
}
