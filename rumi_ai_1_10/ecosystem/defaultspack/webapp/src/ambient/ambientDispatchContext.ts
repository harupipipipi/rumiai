import type { ToolSelectionRequest } from "../lib/api";
import type { AmbientEventPayload } from "./ambientTriggerClient";

export type AmbientDispatchTemplateSelection = {
  model?: string | null;
  templateParams?: Record<string, unknown> | null;
  templateToolPolicy?: Record<string, unknown> | null;
  selectedToolIds?: readonly string[] | null;
};

export type AmbientDispatchTemplateContext = {
  eventPayload: Pick<AmbientEventPayload, "model" | "params" | "tools">;
  metadata: Record<string, unknown>;
};

export function buildAmbientDispatchTemplateContext({
  model,
  templateParams,
  templateToolPolicy,
  selectedToolIds,
}: AmbientDispatchTemplateSelection): AmbientDispatchTemplateContext {
  const modelId = cleanText(model);
  const selectedTools = uniqueCleanList(selectedToolIds);
  const params = cleanRecord(templateParams);
  const baseToolPolicy = cleanRecord(templateToolPolicy);
  const toolSelection = ambientToolSelectionRequest(selectedTools);

  if (modelId && !cleanText(params.model) && !cleanText(params.profile_id)) {
    params.model = modelId;
  }
  if (toolSelection) {
    params.tool_selection = toolSelection;
  }
  if (Object.keys(baseToolPolicy).length || selectedTools.length) {
    params.tool_policy = {
      ...baseToolPolicy,
      ...(selectedTools.length ? { selected_tools: selectedTools } : {}),
    };
  }

  return {
    eventPayload: {
      ...(modelId ? { model: modelId, params } : Object.keys(params).length ? { params } : {}),
      ...(selectedTools.length ? { tools: selectedTools } : {}),
    },
    metadata: {
      ...(modelId ? { selected_model: modelId } : {}),
      ...(selectedTools.length ? { selected_tools: selectedTools, tool_selection_scope: "turn" } : {}),
    },
  };
}

export function mergeAmbientDispatchMetadata(
  metadata: Record<string, unknown>,
  dispatchContext: AmbientDispatchTemplateContext,
): Record<string, unknown> {
  return {
    ...metadata,
    ...dispatchContext.metadata,
  };
}

function ambientToolSelectionRequest(selectedTools: string[]): ToolSelectionRequest | undefined {
  if (!selectedTools.length) return undefined;
  return {
    mode: "manual",
    include: selectedTools,
    scope: "turn",
    must_use: false,
  };
}

function cleanText(value: unknown): string {
  return String(value ?? "").trim();
}

function cleanRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? { ...(value as Record<string, unknown>) } : {};
}

function uniqueCleanList(value: readonly string[] | null | undefined): string[] {
  return Array.from(new Set((value ?? []).map((item) => cleanText(item)).filter(Boolean)));
}
