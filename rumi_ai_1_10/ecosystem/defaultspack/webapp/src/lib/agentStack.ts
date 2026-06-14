import type { ModelProfile } from "./api";

export type AgentStackModelConstraints = {
  requires_vision?: boolean;
  model_ids?: string[];
  model_id_includes?: string[];
  model_id_regex?: string[];
  provider_ids?: string[];
};

export type AgentStackProfile = {
  id: string;
  label: string;
  description?: string;
  system_prompt?: string;
  tools?: string[];
  skills?: string[];
  tool_policy?: Record<string, unknown>;
  constraints?: AgentStackModelConstraints;
};

export type AgentStackConversationState = {
  profile_ids?: string[];
  tool_overrides?: Record<string, boolean>;
};

export type AgentStackSource = "default" | "group_default" | "conversation" | "draft";

export type AgentStackSettings = {
  featureName: string;
  profilesJson: string;
  profiles: AgentStackProfile[];
  parseError: string | null;
  defaultProfileIds: string[];
  groupDefaults: Record<string, string[]>;
};

export type ResolvedAgentStackSelection = {
  source: AgentStackSource;
  defaultProfileIds: string[];
  profileIds: string[];
  toolOverrides: Record<string, boolean>;
};

export type AgentStackAvailability = {
  matches: boolean;
  reason: string | null;
};

export type ResolvedAgentStackProfile = {
  profile: AgentStackProfile;
  available: boolean;
  reason: string | null;
};

export type MergedAgentStackProfiles = {
  toolIds: string[];
  skillIds: string[];
  systemPrompt: string;
  toolPolicy: Record<string, unknown>;
};

const DEFAULT_FEATURE_NAME = "Agent Stack";
const AGENT_STACK_TOOL_POLICY_ALLOWED_KEYS = new Set([
  "allow_file_write",
  "allow_network",
  "allow_shell",
  "allowed_tools",
  "disabled_tools",
  "enabled_tools",
  "max_tool_calls",
  "model_allowlist",
  "model_denylist",
  "parallel_tool_calls",
  "profile_id",
  "selected_tools",
  "tool_allowlist",
  "tool_blocklist",
  "tool_choice",
  "tool_denylist",
]);
const AGENT_STACK_APPROVAL_BYPASS_KEYS = new Set([
  "_tool_server_approval_token_valid",
  "_tool_server_approved",
  "allow_client_supplied_approved",
  "approval_bypass",
  "approval_granted",
  "approval_token",
  "approved",
  "bypass_approval",
  "grant_approval",
  "is_approved",
  "server_approved",
  "tool_approval_tokens",
  "yolo_mode",
]);
const AGENT_STACK_APPROVAL_REQUIRE_KEYS = new Set([
  "delete_actions_require_approval",
  "destructive_actions_require_approval",
  "git_push_requires_approval",
  "high_risk_tools_require_approval",
  "open_world_require_approval",
  "terminal_actions_require_approval",
  "write_actions_require_approval",
]);

const DEFAULT_PROFILES: AgentStackProfile[] = [
  {
    id: "coding",
    label: "coding",
    description: "Coding-oriented tools and a concise code-focused system prompt.",
    system_prompt: "Focus on code changes. Prefer the smallest safe diff, verify behavior, and explain tradeoffs briefly.",
    tools: [
      "coding_file_list",
      "coding_file_read",
      "coding_file_search",
      "coding_file_patch",
      "coding_file_write",
      "coding_file_create",
      "coding_file_delete",
      "coding_git_status",
      "coding_git_diff",
      "coding_git_commit",
      "coding_git_push",
      "coding_terminal_exec",
      "coding_terminal_stream",
    ],
  },
  {
    id: "subagent",
    label: "subagent",
    description: "Delegation-first orchestration profile for OpenCode Zen MiniMax M3 Free.",
    system_prompt: "大規模なタスクでは、自分で細部を進めず、subagent の制作・依頼・管理・結果統合のみを行ってください。大規模でないタスクでも、メインではない作業、または取得したい情報が明確に決まっている作業は、できるだけ subagent に依頼してください。自分はオーケストレーターとして振る舞い、subagent には目的、範囲、期待する出力を具体的に渡してください。",
    tools: [
      "subagent",
    ],
    constraints: {
      provider_ids: ["opencode-zen"],
      model_ids: ["minimax-m3-free", "opencode-zen/minimax-m3-free"],
    },
  },
  {
    id: "all",
    label: "all",
    description: "Wide tool access across coding, browser, research, and planning surfaces.",
    tools: [
      "coding_file_list",
      "coding_file_read",
      "coding_file_search",
      "coding_file_patch",
      "coding_file_write",
      "coding_git_status",
      "coding_git_diff",
      "coding_terminal_exec",
      "browser_use",
      "browser_companion",
      "browser_computer",
      "web_search",
      "reddit_search",
      "todo",
      "subagent",
      "rumi_api",
    ],
  },
  {
    id: "yolo",
    label: "yolo",
    description: "High-autonomy profile for fully local coding/browser execution.",
    system_prompt: "Move decisively. When the path is clear, execute directly instead of waiting for extra confirmation.",
    tool_policy: {
      yolo_mode: true,
      allow_shell: true,
      allow_file_write: true,
      write_actions_require_approval: false,
      delete_actions_require_approval: false,
      terminal_actions_require_approval: false,
    },
  },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cleanString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function cleanStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => cleanString(item)).filter(Boolean))];
}

function cloneJsonValue(value: unknown): unknown {
  if (value === null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.map(cloneJsonValue).filter((item) => item !== undefined);
  if (!isRecord(value)) return undefined;
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, entry]) => [key, cloneJsonValue(entry)])
      .filter(([, entry]) => entry !== undefined),
  );
}

export function sanitizeAgentStackToolPolicy(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) return {};
  const sanitized: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) {
    const normalizedKey = key.trim();
    if (!normalizedKey) continue;
    const lowerKey = normalizedKey.toLowerCase();
    if (AGENT_STACK_APPROVAL_BYPASS_KEYS.has(lowerKey)) continue;
    if (AGENT_STACK_APPROVAL_REQUIRE_KEYS.has(lowerKey) && entry === false) continue;
    if (!AGENT_STACK_TOOL_POLICY_ALLOWED_KEYS.has(lowerKey) && !AGENT_STACK_APPROVAL_REQUIRE_KEYS.has(lowerKey)) continue;
    const cloned = cloneJsonValue(entry);
    if (cloned !== undefined) sanitized[normalizedKey] = cloned;
  }
  return sanitized;
}

function normalizeConstraints(value: unknown): AgentStackModelConstraints | undefined {
  if (!isRecord(value)) return undefined;
  const constraints: AgentStackModelConstraints = {};
  if (value.requires_vision === true) constraints.requires_vision = true;
  const modelIds = cleanStringArray(value.model_ids);
  const modelIdIncludes = cleanStringArray(value.model_id_includes);
  const modelIdRegex = cleanStringArray(value.model_id_regex);
  const providerIds = cleanStringArray(value.provider_ids);
  if (modelIds.length) constraints.model_ids = modelIds;
  if (modelIdIncludes.length) constraints.model_id_includes = modelIdIncludes;
  if (modelIdRegex.length) constraints.model_id_regex = modelIdRegex;
  if (providerIds.length) constraints.provider_ids = providerIds;
  return Object.keys(constraints).length ? constraints : undefined;
}

function normalizeProfile(value: unknown): AgentStackProfile | null {
  if (!isRecord(value)) return null;
  const id = cleanString(value.id || value.name);
  const label = cleanString(value.label || value.name || id);
  if (!id || !label) return null;
  const profile: AgentStackProfile = {
    id,
    label,
  };
  const description = cleanString(value.description);
  const systemPrompt = cleanString(value.system_prompt || value.systemPrompt);
  const tools = cleanStringArray(value.tools || value.tool_ids);
  const skills = cleanStringArray(value.skills || value.skill_ids);
  const toolPolicy = sanitizeAgentStackToolPolicy(value.tool_policy || value.toolPolicy);
  const constraints = normalizeConstraints(value.constraints || value.availability);
  if (description) profile.description = description;
  if (systemPrompt) profile.system_prompt = systemPrompt;
  if (tools.length) profile.tools = tools;
  if (skills.length) profile.skills = skills;
  if (Object.keys(toolPolicy).length) profile.tool_policy = toolPolicy;
  if (constraints) profile.constraints = constraints;
  return profile;
}

function normalizeProfiles(value: unknown): AgentStackProfile[] {
  const list = Array.isArray(value)
    ? value
    : isRecord(value) && Array.isArray(value.profiles)
      ? value.profiles
      : [];
  const byId = new Map<string, AgentStackProfile>();
  for (const item of list) {
    const profile = normalizeProfile(item);
    if (!profile) continue;
    byId.set(profile.id, profile);
  }
  return Array.from(byId.values());
}

function selectionIdsForKnownProfiles(ids: unknown, profiles: AgentStackProfile[]): string[] {
  const knownIds = new Set(profiles.map((profile) => profile.id));
  return cleanStringArray(ids).filter((id) => knownIds.has(id));
}

function normalizeGroupDefaults(value: unknown, profiles: AgentStackProfile[]): Record<string, string[]> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([groupId, ids]) => [cleanString(groupId), selectionIdsForKnownProfiles(ids, profiles)])
      .filter(([groupId]) => Boolean(groupId)),
  );
}

export function defaultAgentStackProfiles(): AgentStackProfile[] {
  return DEFAULT_PROFILES.map((profile) => ({ ...profile }));
}

export function defaultAgentStackProfilesJson(): string {
  return JSON.stringify(DEFAULT_PROFILES, null, 2);
}

export function normalizeAgentStackSettings(value: unknown): AgentStackSettings {
  const section = isRecord(value) ? value : {};
  const featureName = cleanString(section.feature_name || section.featureName) || DEFAULT_FEATURE_NAME;
  const rawProfilesJson = typeof section.profiles_json === "string"
    ? section.profiles_json
    : Array.isArray(section.profiles)
      ? JSON.stringify(section.profiles, null, 2)
      : defaultAgentStackProfilesJson();
  let profiles = normalizeProfiles(DEFAULT_PROFILES);
  let parseError: string | null = null;
  const trimmedProfilesJson = rawProfilesJson.trim();
  if (trimmedProfilesJson) {
    try {
      const parsed = JSON.parse(trimmedProfilesJson);
      profiles = normalizeProfiles(parsed);
    } catch (error) {
      parseError = error instanceof Error ? error.message : "Invalid JSON";
    }
  }
  const defaultProfileIds = selectionIdsForKnownProfiles(section.default_profile_ids, profiles);
  const groupDefaults = normalizeGroupDefaults(section.group_defaults, profiles);
  return {
    featureName,
    profilesJson: rawProfilesJson,
    profiles,
    parseError,
    defaultProfileIds,
    groupDefaults,
  };
}

function activeGroupDefault(groupId: string | null | undefined, settings: AgentStackSettings): string[] | null {
  const normalizedGroupId = cleanString(groupId);
  if (!normalizedGroupId) return null;
  if (Object.prototype.hasOwnProperty.call(settings.groupDefaults, normalizedGroupId)) {
    return settings.groupDefaults[normalizedGroupId] ?? [];
  }
  return null;
}

function normalizeToolOverrides(value: unknown): Record<string, boolean> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([toolId, enabled]) => [cleanString(toolId), enabled === true ? true : enabled === false ? false : undefined])
      .filter(([toolId, enabled]) => Boolean(toolId) && enabled !== undefined),
  ) as Record<string, boolean>;
}

export function parseAgentStackConversationState(value: unknown): AgentStackConversationState | null {
  if (!isRecord(value)) return null;
  const profileIds = cleanStringArray(value.profile_ids || value.profileIds);
  const toolOverrides = normalizeToolOverrides(value.tool_overrides || value.toolOverrides);
  if (!profileIds.length && Object.keys(toolOverrides).length === 0) return null;
  return {
    ...(profileIds.length ? { profile_ids: profileIds } : {}),
    ...(Object.keys(toolOverrides).length ? { tool_overrides: toolOverrides } : {}),
  };
}

export function resolveAgentStackSelection(options: {
  settings: AgentStackSettings;
  groupId?: string | null;
  conversationState?: AgentStackConversationState | null;
  draftState?: AgentStackConversationState | null;
}): ResolvedAgentStackSelection {
  const { settings, groupId, conversationState, draftState } = options;
  const groupDefaultIds = activeGroupDefault(groupId, settings);
  const defaultProfileIds = groupDefaultIds ?? settings.defaultProfileIds;
  const explicitState = conversationState ?? draftState ?? null;
  if (conversationState) {
    return {
      source: "conversation",
      defaultProfileIds,
      profileIds: selectionIdsForKnownProfiles(conversationState.profile_ids ?? [], settings.profiles),
      toolOverrides: normalizeToolOverrides(conversationState.tool_overrides),
    };
  }
  if (draftState) {
    return {
      source: "draft",
      defaultProfileIds,
      profileIds: selectionIdsForKnownProfiles(draftState.profile_ids ?? [], settings.profiles),
      toolOverrides: normalizeToolOverrides(draftState.tool_overrides),
    };
  }
  if (explicitState) {
    return {
      source: "conversation",
      defaultProfileIds,
      profileIds: selectionIdsForKnownProfiles(explicitState.profile_ids ?? [], settings.profiles),
      toolOverrides: normalizeToolOverrides(explicitState.tool_overrides),
    };
  }
  if (groupDefaultIds) {
    return {
      source: "group_default",
      defaultProfileIds,
      profileIds: defaultProfileIds,
      toolOverrides: {},
    };
  }
  return {
    source: "default",
    defaultProfileIds,
    profileIds: defaultProfileIds,
    toolOverrides: {},
  };
}

function modelIdCandidates(modelProfile: ModelProfile | null | undefined): string[] {
  const candidates = [
    modelProfile?.profile_id,
    modelProfile?.qualified_model_id,
    modelProfile?.model_id,
    modelProfile?.provider_id && modelProfile?.model_id ? `${modelProfile.provider_id}/${modelProfile.model_id}` : "",
    modelProfile?.display_name,
  ];
  return [...new Set(candidates.map((item) => cleanString(item)).filter(Boolean))];
}

export function agentStackProfileAvailability(
  profile: AgentStackProfile,
  modelProfile: ModelProfile | null | undefined,
): AgentStackAvailability {
  const constraints = profile.constraints;
  if (!constraints) return { matches: true, reason: null };
  if (constraints.requires_vision && !modelProfile?.supports_vision && !modelProfile?.supports_image_input) {
    return { matches: false, reason: "Vision model only" };
  }
  const candidateIds = modelIdCandidates(modelProfile);
  const lowerCandidateIds = candidateIds.map((item) => item.toLowerCase());
  const providerId = cleanString(modelProfile?.provider_id).toLowerCase();
  if (constraints.provider_ids?.length) {
    const allowedProviders = new Set(constraints.provider_ids.map((item) => item.toLowerCase()));
    if (!providerId || !allowedProviders.has(providerId)) {
      return { matches: false, reason: `Provider: ${constraints.provider_ids.join(", ")}` };
    }
  }
  if (constraints.model_ids?.length) {
    const allowedIds = new Set(constraints.model_ids.map((item) => item.toLowerCase()));
    if (!lowerCandidateIds.some((item) => allowedIds.has(item))) {
      return { matches: false, reason: `Model id: ${constraints.model_ids.join(", ")}` };
    }
  }
  if (constraints.model_id_includes?.length) {
    const includes = constraints.model_id_includes.map((item) => item.toLowerCase());
    if (!lowerCandidateIds.some((candidate) => includes.some((part) => candidate.includes(part)))) {
      return { matches: false, reason: `Model contains: ${constraints.model_id_includes.join(", ")}` };
    }
  }
  if (constraints.model_id_regex?.length) {
    const compiled = constraints.model_id_regex
      .map((pattern) => {
        try {
          return new RegExp(pattern, "i");
        } catch {
          return null;
        }
      })
      .filter((pattern): pattern is RegExp => Boolean(pattern));
    if (compiled.length && !candidateIds.some((candidate) => compiled.some((pattern) => pattern.test(candidate)))) {
      return { matches: false, reason: `Regex: ${constraints.model_id_regex.join(", ")}` };
    }
  }
  return { matches: true, reason: null };
}

export function resolveAgentStackProfiles(
  profileIds: string[],
  settings: AgentStackSettings,
  modelProfile: ModelProfile | null | undefined,
): ResolvedAgentStackProfile[] {
  const byId = new Map(settings.profiles.map((profile) => [profile.id, profile]));
  return profileIds
    .map((profileId) => byId.get(profileId))
    .filter((profile): profile is AgentStackProfile => Boolean(profile))
    .map((profile) => {
      const availability = agentStackProfileAvailability(profile, modelProfile);
      return {
        profile,
        available: availability.matches,
        reason: availability.reason,
      };
    });
}

function mergeToolPolicyValue(current: unknown, incoming: unknown): unknown {
  if (Array.isArray(current) || Array.isArray(incoming)) {
    return [...new Set([...(Array.isArray(current) ? current : []), ...(Array.isArray(incoming) ? incoming : [])].map((item) => cloneJsonValue(item)).filter((item) => item !== undefined))];
  }
  if (isRecord(current) && isRecord(incoming)) {
    const merged: Record<string, unknown> = { ...current };
    for (const [key, value] of Object.entries(incoming)) {
      merged[key] = key in merged ? mergeToolPolicyValue(merged[key], value) : cloneJsonValue(value);
    }
    return merged;
  }
  return cloneJsonValue(incoming);
}

export function mergeAgentStackProfiles(profiles: AgentStackProfile[]): MergedAgentStackProfiles {
  const toolIds: string[] = [];
  const skillIds: string[] = [];
  const systemPrompts: string[] = [];
  let toolPolicy: Record<string, unknown> = {};
  for (const profile of profiles) {
    for (const toolId of profile.tools ?? []) {
      if (!toolIds.includes(toolId)) toolIds.push(toolId);
    }
    for (const skillId of profile.skills ?? []) {
      if (!skillIds.includes(skillId)) skillIds.push(skillId);
    }
    if (profile.system_prompt) {
      systemPrompts.push(profile.system_prompt);
    }
    if (isRecord(profile.tool_policy)) {
      toolPolicy = mergeToolPolicyValue(toolPolicy, sanitizeAgentStackToolPolicy(profile.tool_policy)) as Record<string, unknown>;
    }
  }
  return {
    toolIds,
    skillIds,
    systemPrompt: systemPrompts.join("\n\n").trim(),
    toolPolicy,
  };
}

export function applyAgentStackToolOverrides(baseToolIds: string[], toolOverrides: Record<string, boolean> | null | undefined): string[] {
  const next = baseToolIds.filter((toolId) => toolOverrides?.[toolId] !== false);
  for (const [toolId, enabled] of Object.entries(toolOverrides ?? {})) {
    if (enabled === true && !next.includes(toolId)) {
      next.push(toolId);
    }
  }
  return next;
}

export function toggleAgentStackToolOverride(
  baseToolIds: string[],
  toolOverrides: Record<string, boolean> | null | undefined,
  toolId: string,
  enabled: boolean,
): Record<string, boolean> {
  const normalizedToolId = cleanString(toolId);
  if (!normalizedToolId) return normalizeToolOverrides(toolOverrides);
  const next = { ...normalizeToolOverrides(toolOverrides) };
  const inBase = baseToolIds.includes(normalizedToolId);
  if (inBase) {
    if (enabled) {
      delete next[normalizedToolId];
    } else {
      next[normalizedToolId] = false;
    }
    return next;
  }
  if (enabled) {
    next[normalizedToolId] = true;
  } else {
    delete next[normalizedToolId];
  }
  return next;
}

export function batchAgentStackToolOverrides(
  baseToolIds: string[],
  toolOverrides: Record<string, boolean> | null | undefined,
  toolIds: string[],
  enabled: boolean,
): Record<string, boolean> {
  let next = normalizeToolOverrides(toolOverrides);
  for (const toolId of cleanStringArray(toolIds)) {
    next = toggleAgentStackToolOverride(baseToolIds, next, toolId, enabled);
  }
  return next;
}

export function buildAgentStackConversationStateForStorage(profileIds: string[], defaultProfileIds: string[], toolOverrides: Record<string, boolean> | null | undefined): AgentStackConversationState | null {
  const normalizedProfileIds = cleanStringArray(profileIds);
  const normalizedDefaults = cleanStringArray(defaultProfileIds);
  const normalizedToolOverrides = normalizeToolOverrides(toolOverrides);
  const sameProfiles = normalizedProfileIds.length === normalizedDefaults.length
    && normalizedProfileIds.every((profileId, index) => profileId === normalizedDefaults[index]);
  if (sameProfiles && Object.keys(normalizedToolOverrides).length === 0) {
    return null;
  }
  return {
    profile_ids: normalizedProfileIds,
    ...(Object.keys(normalizedToolOverrides).length ? { tool_overrides: normalizedToolOverrides } : {}),
  };
}

export function agentStackSourceLabel(source: AgentStackSource): string {
  switch (source) {
    case "conversation":
      return "Chat Override";
    case "draft":
      return "Draft";
    case "group_default":
      return "Group Default";
    default:
      return "Default";
  }
}
