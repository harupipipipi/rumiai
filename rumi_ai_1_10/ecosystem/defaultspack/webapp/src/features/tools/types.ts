import type { ToolSelectionMode, ToolSelectionPreviewResponse, ToolSelectionRequest, ToolTarget } from "../../lib/api";

export type { ToolSelectionMode, ToolSelectionRequest, ToolTarget };

export type ConversationToolPreferences = {
  mode?: ToolSelectionMode;
  include?: ToolTarget[];
  exclude?: ToolTarget[];
};

export type ToolSelectionUiState = {
  effectiveMode: ToolSelectionMode;
  turnModeOverride: ToolSelectionMode | null;
  turnInclude: ToolTarget[];
  turnExclude: ToolTarget[];
  conversationPreferences: ConversationToolPreferences;
  pendingReview: PendingToolReview | null;
  latestDecision: ToolSelectionPreviewResponse["decision"] | null;
};

export type ToolReviewDraft = {
  input: string;
  attachments: unknown[];
  droppedWidgets: unknown[];
};

export type PendingToolReview = {
  previewId: string;
  expiresAt: string;
  userText: string;
  request: ToolSelectionRequest;
  decision: ToolSelectionPreviewResponse["decision"];
  draft: ToolReviewDraft;
  createdAt: number;
};
