import type { ChatMessage, SidebarItem } from "./api";

export type ToolFilterEntry = {
  tool_name: string;
  status: "allowed" | "blocked" | "hidden" | "approval_required" | "rejected" | string;
  reason_code?: string;
  reason?: string;
  required?: Record<string, unknown>;
  actual?: Record<string, unknown>;
  repair_suggestions?: string[];
};

export type RuntimeCapabilitySnapshot = {
  input_traits?: string[];
  model_capabilities?: string[];
  runtime_capabilities?: string[];
  policy_capabilities?: string[];
  tags?: string[];
};

export type ToolFilterContext = {
  entries: ToolFilterEntry[];
  snapshot: RuntimeCapabilitySnapshot | null;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

export function normalizeToolFilterEntries(value: unknown): ToolFilterEntry[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => asRecord(entry))
    .filter((entry) => String(entry.tool_name ?? "").trim())
    .map((entry) => ({
      tool_name: String(entry.tool_name ?? "").trim(),
      status: String(entry.status ?? "blocked").trim() || "blocked",
      reason_code: String(entry.reason_code ?? "").trim() || undefined,
      reason: String(entry.reason ?? "").trim() || undefined,
      required: asRecord(entry.required),
      actual: asRecord(entry.actual),
      repair_suggestions: asStringList(entry.repair_suggestions),
    }));
}

export function normalizeRuntimeCapabilitySnapshot(value: unknown): RuntimeCapabilitySnapshot | null {
  const record = asRecord(value);
  if (!Object.keys(record).length) return null;
  return {
    input_traits: asStringList(record.input_traits),
    model_capabilities: asStringList(record.model_capabilities),
    runtime_capabilities: asStringList(record.runtime_capabilities),
    policy_capabilities: asStringList(record.policy_capabilities),
    tags: asStringList(record.tags),
  };
}

export function extractLatestToolFilterContext(messages: ChatMessage[]): ToolFilterContext {
  for (const message of [...messages].reverse()) {
    const metadata = asRecord(message.metadata);
    const entries = normalizeToolFilterEntries(metadata.tool_filter_result);
    const snapshot = normalizeRuntimeCapabilitySnapshot(metadata.runtime_capability_snapshot);
    if (entries.length || snapshot) {
      return { entries, snapshot };
    }
  }
  return { entries: [], snapshot: null };
}

export function toolFilterReasonLabel(reasonCode: string | undefined): string {
  switch (String(reasonCode ?? "").trim().toLowerCase()) {
    case "missing_capability":
      return "必要な capability がありません";
    case "missing_input":
      return "必要な入力がありません";
    case "model_unsupported":
      return "現在のモデルでは使えません";
    case "disabled_by_user":
      return "ユーザー設定でOFFです";
    case "disabled_by_policy":
      return "ポリシーで無効です";
    case "requires_approval":
      return "承認が必要です";
    case "not_connected_to_profile":
      return "接続設定が不足しています";
    case "not_attached_to_turn":
      return "今回の実行に接続されていません";
    case "unknown_selected_tool":
      return "登録されていない機能です";
    case "requires_trusted_workspace":
      return "trusted workspace が必要です";
    case "missing_api_key":
      return "API key がありません";
    case "attachment_not_supported":
      return "添付に対応していません";
    case "risk_blocked":
      return "リスク制御で停止しました";
    default:
      return "このターンでは使えません";
  }
}

function requiredModelCapabilities(entry: ToolFilterEntry): string[] {
  return asStringList(asRecord(entry.required).model_capabilities);
}

export function isVisionBlockedEntry(entry: ToolFilterEntry): boolean {
  return entry.status === "blocked"
    && entry.reason_code === "model_unsupported"
    && requiredModelCapabilities(entry).includes("model.image_input");
}

export function toolFilterReasonDetail(entry: ToolFilterEntry): string {
  if (isVisionBlockedEntry(entry)) {
    return "Vision対応モデルに切り替えると使えます。";
  }
  if (entry.status === "hidden") {
    return "現在の表示設定では非表示です。";
  }
  if (entry.reason && entry.reason.trim()) return entry.reason.trim();
  const suggestions = entry.repair_suggestions ?? [];
  if (suggestions.length > 0) return suggestions[0] ?? "";
  return toolFilterReasonLabel(entry.reason_code);
}

export function toolFilterBlockedSummary(entry: ToolFilterEntry): string {
  if (entry.reason_code === "model_unsupported") {
    const required = requiredModelCapabilities(entry);
    return `Blocked: ${required.length ? required.join(", ") : "model_unsupported"}`;
  }
  return `Blocked: ${entry.reason_code ?? entry.status}`;
}

export function toolFilterStatusLabel(entry: ToolFilterEntry): string {
  if (entry.status === "hidden") return "現在は非表示です";
  if (entry.status === "approval_required") return "承認が必要です";
  if (entry.status === "blocked" || entry.status === "rejected") {
    return toolFilterReasonLabel(entry.reason_code);
  }
  return "利用可能";
}

export type ToolManagerSummary = {
  totalCount: number;
  onCount: number;
  offByUserCount: number;
  hiddenCount: number;
  blockedCount: number;
  needsApprovalCount: number;
  missingSetupCount: number;
};

export function summarizeToolManager(
  tools: SidebarItem[],
  options: {
    disabledToolIds?: string[];
    hiddenToolIds?: string[];
    filterEntries?: ToolFilterEntry[];
  } = {},
): ToolManagerSummary {
  const disabledSet = new Set(options.disabledToolIds ?? []);
  const hiddenSet = new Set(options.hiddenToolIds ?? []);
  const filterEntries = options.filterEntries ?? [];
  const uniqueBlocked = new Set(
    filterEntries
      .filter((entry) => entry.status === "blocked" || entry.status === "rejected")
      .map((entry) => entry.tool_name),
  );
  const totalCount = tools.length;
  const offByUserCount = tools.filter((tool) => disabledSet.has(tool.id)).length;
  const hiddenCount = tools.filter((tool) => hiddenSet.has(tool.id)).length;
  const needsApprovalCount = tools.filter((tool) => tool.tool_info?.requires_approval).length;
  const missingSetupCount = tools.filter((tool) => tool.tool_info?.setup_state?.status === "missing").length;
  const onCount = Math.max(0, totalCount - offByUserCount);
  return {
    totalCount,
    onCount,
    offByUserCount,
    hiddenCount,
    blockedCount: uniqueBlocked.size,
    needsApprovalCount,
    missingSetupCount,
  };
}

export function toolCapabilityChips(tool: SidebarItem): string[] {
  const info = tool.tool_info;
  if (!info) return [];
  const chips: string[] = [];
  if (info.requires_approval) chips.push("approval");
  if (info.requires_model_capabilities?.includes("model.image_input")) chips.push("vision");
  if (info.requires_runtime_capabilities?.length) chips.push("runtime");
  if (info.attachment_policy) chips.push(`attach:${info.attachment_policy}`);
  if (info.setup_state?.status === "missing") chips.push("setup");
  return chips;
}
