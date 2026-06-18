import { useMemo, useState } from "react";

import { api } from "../../lib/api";
import type { PendingToolReview, ToolReviewDraft, ToolSelectionMode, ToolSelectionRequest, ToolTarget } from "./types";

type ControllerInput = {
  settingsValues: Record<string, Record<string, unknown>>;
  selectedToolIds: string[];
  setSelectedToolIds: (toolIds: string[]) => void;
};

type BuildRequestInput = {
  toolIds: string[];
  mentionedToolIds?: string[];
};

type PreviewReviewInput = {
  conversationId?: string | null;
  userText: string;
  attachmentMetadata?: unknown[];
  toolSelection: ToolSelectionRequest;
  draft: ToolReviewDraft;
  model?: string | null;
};

const MODES = new Set<ToolSelectionMode>(["auto", "review", "manual", "none"]);

export function useToolSelectionController({
  settingsValues,
  selectedToolIds,
  setSelectedToolIds,
}: ControllerInput) {
  const [turnModeOverride, setTurnModeOverride] = useState<ToolSelectionMode | null>(null);
  const [turnExclude, setTurnExclude] = useState<ToolTarget[]>([]);
  const [pendingReview, setPendingReview] = useState<PendingToolReview | null>(null);
  const [latestDecision, setLatestDecision] = useState<PendingToolReview["decision"] | null>(null);

  const defaultMode = useMemo<ToolSelectionMode>(() => {
    const raw = String(settingsValues.tools?.default_mode ?? "auto").trim().toLowerCase() as ToolSelectionMode;
    return MODES.has(raw) ? raw : "auto";
  }, [settingsValues.tools?.default_mode]);

  const effectiveMode = turnModeOverride ?? defaultMode;
  const turnInclude = useMemo<ToolTarget[]>(
    () => selectedToolIds.map((id) => ({ kind: "tool", id })),
    [selectedToolIds],
  );

  const setTurnMode = (mode: ToolSelectionMode | null) => {
    setTurnModeOverride(mode);
  };

  const toggleTurnTarget = (target: ToolTarget) => {
    if (target.kind !== "tool") return;
    setSelectedToolIds(
      selectedToolIds.includes(target.id)
        ? selectedToolIds.filter((id) => id !== target.id)
        : [...selectedToolIds, target.id],
    );
    if (effectiveMode === "auto") setTurnModeOverride("manual");
  };

  const removeTarget = (target: ToolTarget) => {
    if (target.kind === "tool") {
      setSelectedToolIds(selectedToolIds.filter((id) => id !== target.id));
      return;
    }
    setTurnExclude((current) => current.filter((item) => !(item.kind === target.kind && item.id === target.id)));
  };

  const buildRequest = ({ toolIds, mentionedToolIds = [] }: BuildRequestInput): ToolSelectionRequest => {
    const uniqueToolIds = [...new Set([...toolIds, ...mentionedToolIds].filter(Boolean))];
    if (effectiveMode === "none") {
      return {
        mode: "none",
        include: [],
        exclude: [],
        scope: "turn",
        must_use: false,
      };
    }
    if (effectiveMode === "manual" || uniqueToolIds.length > 0) {
      return {
        mode: "manual",
        include: uniqueToolIds.map((id) => ({ kind: "tool", id })),
        exclude: turnExclude,
        scope: "turn",
        must_use: false,
      };
    }
    return {
      mode: effectiveMode,
      include: [],
      exclude: turnExclude,
      scope: "turn",
      must_use: false,
    };
  };

  const previewReview = async ({
    conversationId,
    userText,
    attachmentMetadata = [],
    toolSelection,
    draft,
    model,
  }: PreviewReviewInput): Promise<PendingToolReview> => {
    const response = await api.previewToolSelection({
      conversation_id: conversationId ?? null,
      user_text: userText,
      attachment_metadata: attachmentMetadata,
      tool_selection: toolSelection,
      model: model ?? null,
    });
    const pending: PendingToolReview = {
      previewId: response.preview_id,
      expiresAt: response.expires_at,
      userText,
      request: toolSelection,
      decision: response.decision,
      draft,
      createdAt: Date.now(),
    };
    setPendingReview(pending);
    setLatestDecision(response.decision);
    return pending;
  };

  const approveReview = (): ToolSelectionRequest | null => {
    if (!pendingReview) return null;
    const reviewedToolIds = selectedToolIds.length ? selectedToolIds : pendingReview.decision.selected_tools;
    const include = reviewedToolIds.map((id) => ({ kind: "tool" as const, id }));
    const request: ToolSelectionRequest = {
      mode: include.length ? "manual" : "none",
      include,
      exclude: pendingReview.request.exclude ?? [],
      scope: "turn",
      must_use: false,
      preview_id: pendingReview.previewId,
    };
    setPendingReview(null);
    return request;
  };

  const continueWithoutTools = (): ToolSelectionRequest | null => {
    if (!pendingReview) return null;
    const request: ToolSelectionRequest = {
      mode: "none",
      include: [],
      exclude: [],
      scope: "turn",
      must_use: false,
      preview_id: pendingReview.previewId,
    };
    setPendingReview(null);
    return request;
  };

  const cancelReview = () => {
    setPendingReview(null);
  };

  const clearTurnStateAfterSend = ({ keepSelectedTools }: { keepSelectedTools: boolean }) => {
    setTurnModeOverride(null);
    setTurnExclude([]);
    if (!keepSelectedTools) setSelectedToolIds([]);
  };

  return {
    state: {
      effectiveMode,
      turnModeOverride,
      turnInclude,
      turnExclude,
      conversationPreferences: {},
      pendingReview,
      latestDecision,
    },
    setTurnMode,
    toggleTurnTarget,
    removeTarget,
    buildRequest,
    previewReview,
    approveReview,
    continueWithoutTools,
    cancelReview,
    clearTurnStateAfterSend,
  };
}
