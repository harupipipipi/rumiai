import type { SettingsSection } from "../lib/api";
import { settingsFieldSearchText } from "../lib/settingsSearch";

export type ControlCenterSectionId =
  | "quick_setup"
  | "models_api"
  | "accounts_connections"
  | "tools_mcp"
  | "computer_automation"
  | "workspace_ui"
  | "profiles"
  | "privacy_security"
  | "packs_extensions"
  | "advanced"
  | "diagnostics";

export type ControlCenterField = SettingsSection["fields"][number] & {
  controlSectionId: ControlCenterSectionId;
  sourceSectionId: string;
  sourceSectionLabel: string;
  sourceSectionDescription?: string;
};

export type ControlCenterSection = {
  id: ControlCenterSectionId;
  label: string;
  description: string;
  help: string;
  order: number;
  fields: ControlCenterField[];
  sourceSections: SettingsSection[];
};

type SettingsField = SettingsSection["fields"][number];
type SettingsValues = Record<string, Record<string, unknown>>;

export type AccountConnectionScopeModeOption = {
  id: string;
  label: string;
  description: string;
  scopes: string[];
  services: string[];
  restricted: boolean;
  warning: string;
};

export type AccountConnectionPreludeCard = {
  providerId: string;
  label: string;
  description: string;
  connected: boolean;
  statusLabel: string;
  status: string;
  canConnect: boolean;
  connectAction?: {
    providerId: string;
    scopeMode?: string;
    services?: string[];
  };
  primaryLabel: string;
  disabledReason: string;
  officialAppDescription: string;
  selfHostDescription: string;
  configureSectionId: ControlCenterSectionId;
  configureLabel: string;
  scopeMode?: string;
  services: string[];
  scopes: string[];
  scopeModes: AccountConnectionScopeModeOption[];
  credential?: {
    kind: "codex_access_token";
    configured: boolean;
    canClear: boolean;
    placeholder: string;
    saveLabel: string;
    clearLabel: string;
  };
};

export type CodexAppServerPrelude = {
  configured: boolean;
  enabled: boolean;
  statusLabel: string;
  status: string;
  blockedReason: string;
  baseUrl: string;
  websocketUrl: string;
  loopback: boolean;
  authRequired: boolean;
  authConfigured: boolean;
  toolSourceStatus: string;
  automationEndpointStatus: string;
};

const BLOCKED_RAW_LABELS = new Map([
  ["mimo", "Mimo model preset"],
  ["computer_use_gradient", "Automation visual indicator"],
  ["openrouter_auto", "OpenRouter auto routing"],
]);

const BLOCKED_RAW_LABEL_PATTERNS: Array<[RegExp, string]> = [
  [/\bmimo(?:[_ -]?(?:model|preset|coding|company|v\d+(?:\.\d+)?))*\b/i, "Mimo model preset"],
  [/\bcomputer[_ -]?use[_ -]?gradient(?:[_ -]?(?:enabled|color|opacity|mode))*\b/i, "Automation visual indicator"],
  [/\bopenrouter[_ -]?auto(?:[_ -]?(?:mode|routing|fallback))*\b/i, "OpenRouter auto routing"],
];

const SECTION_META: Array<Omit<ControlCenterSection, "fields" | "sourceSections">> = [
  {
    id: "quick_setup",
    label: "Quick Setup",
    description: "Setup blockers and the first choices that make Rumi usable.",
    help: "Shows model, API, account, MCP, computer approval, and cloud continuation setup first.",
    order: 10,
  },
  {
    id: "models_api",
    label: "Models & API",
    description: "Model roles, providers, API keys, routing, and fallback.",
    help: "Model ids and provider quirks stay here instead of leaking into unrelated sections.",
    order: 20,
  },
  {
    id: "accounts_connections",
    label: "Accounts & Connections",
    description: "OAuth and account connections for Cloudflare, Google, Gmail, Drive, and future providers.",
    help: "Connections own credentials and identity. Tool execution policy lives in Tools & MCP.",
    order: 30,
  },
  {
    id: "tools_mcp",
    label: "Tools & MCP",
    description: "Installed tools, MCP servers, discovered tools, visibility, and approval policy.",
    help: "MCP servers can require a connection, but the login flow belongs to Accounts & Connections.",
    order: 40,
  },
  {
    id: "computer_automation",
    label: "Computer & Automation",
    description: "Screen observation, browser automation, local permissions, approvals, and cloud continuation.",
    help: "Computer control is shown as a high-impact permission surface, not as a normal tool row.",
    order: 50,
  },
  {
    id: "workspace_ui",
    label: "Workspace & UI",
    description: "Theme, layout, panes, shortcuts, composer behavior, and visual indicators.",
    help: "Visual-only settings live here, including automation indicators.",
    order: 60,
  },
  {
    id: "profiles",
    label: "Profiles",
    description: "Profile-specific runtime presets for models, tools, credentials, and policy.",
    help: "Profile-aware settings should show configured, missing, disabled, and unapproved states.",
    order: 70,
  },
  {
    id: "privacy_security",
    label: "Privacy & Security",
    description: "Credentials, approvals, audit logs, data retention, and dangerous action policy.",
    help: "Write-like actions, secrets, and approvals stay visible and policy-aware.",
    order: 80,
  },
  {
    id: "packs_extensions",
    label: "Packs & Extensions",
    description: "Pack install, update, enable, disable, and settings contributions.",
    help: "Packs contribute settings through a registry contract instead of mutating UI directly.",
    order: 90,
  },
  {
    id: "advanced",
    label: "Advanced",
    description: "Rare power-user and compatibility settings.",
    help: "Low-frequency knobs stay below the daily setup path.",
    order: 100,
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    description: "Health checks, logs, raw state, migration reports, and developer diagnostics.",
    help: "Debug and raw JSON settings are intentionally parked here.",
    order: 110,
  },
];

const SECTION_ID_ALIASES: Record<string, ControlCenterSectionId> = {
  quick_setup: "quick_setup",
  setup: "quick_setup",
  onboarding: "quick_setup",
  models: "models_api",
  model: "models_api",
  model_routing: "models_api",
  ai_model: "models_api",
  apis: "models_api",
  api: "models_api",
  providers: "models_api",
  provider: "models_api",
  accounts: "accounts_connections",
  connections: "accounts_connections",
  integrations: "accounts_connections",
  oauth: "accounts_connections",
  tools: "tools_mcp",
  tool: "tools_mcp",
  mcp: "tools_mcp",
  computer: "computer_automation",
  computer_use: "computer_automation",
  browser: "computer_automation",
  automation: "computer_automation",
  ambient: "computer_automation",
  continuity: "computer_automation",
  system_info: "computer_automation",
  general: "workspace_ui",
  preview: "workspace_ui",
  sidebar: "workspace_ui",
  history: "workspace_ui",
  composer: "workspace_ui",
  commands: "workspace_ui",
  theme: "workspace_ui",
  layout: "workspace_ui",
  calendar: "workspace_ui",
  workspace: "workspace_ui",
  ui: "workspace_ui",
  profile: "profiles",
  profiles: "profiles",
  adaptive: "profiles",
  privacy: "privacy_security",
  security: "privacy_security",
  permissions: "privacy_security",
  approvals: "privacy_security",
  authority: "privacy_security",
  packs: "packs_extensions",
  pack: "packs_extensions",
  extensions: "packs_extensions",
  extension: "packs_extensions",
  advanced: "advanced",
  diagnostics: "diagnostics",
  debug: "diagnostics",
  logs: "diagnostics",
};

const FIELD_TOKEN_ALIASES: Array<[RegExp, ControlCenterSectionId]> = [
  [/\b(model|provider|api[_ -]?key|api[_ -]?route|token|openrouter)\b/i, "models_api"],
  [/\b(oauth|account|connection|connect|gmail|drive|google|cloudflare|codex|github)\b/i, "accounts_connections"],
  [/\b(computer|browser|screen|click|type|scroll|desktop|accessibility|continuity|automation|ambient|camera|microphone)\b/i, "computer_automation"],
  [/\b(mcp|tool|approval|allowlist|denylist|permission[_ -]?overrides)\b/i, "tools_mcp"],
  [/\b(theme|layout|sidebar|preview|composer|shortcut|command|gradient|indicator|calendar|language|voice)\b/i, "workspace_ui"],
  [/\b(profile|runtime|adaptive)\b/i, "profiles"],
  [/\b(privacy|security|audit|retention|secret|credential|dangerous|authority)\b/i, "privacy_security"],
  [/\b(pack|extension|template)\b/i, "packs_extensions"],
  [/\b(debug|diagnostic|health|log|raw|migration)\b/i, "diagnostics"],
];

export function controlCenterSectionMeta(): ControlCenterSection[] {
  return SECTION_META.map((section) => ({ ...section, fields: [], sourceSections: [] }));
}

export function safeSettingsLabel(value: unknown, fallback: unknown = ""): string {
  const label = String(value ?? fallback ?? "").trim();
  const exact = BLOCKED_RAW_LABELS.get(label.toLowerCase());
  if (exact) return exact;
  for (const [pattern, replacement] of BLOCKED_RAW_LABEL_PATTERNS) {
    if (pattern.test(label)) return replacement;
  }
  return label;
}

export function normalizeSettingsField(field: SettingsField): SettingsField {
  const normalized = { ...field };
  normalized.label = safeSettingsLabel(field.label, field.id);
  if (Array.isArray(field.options)) {
    normalized.options = field.options.map((option) => ({
      ...option,
      label: safeSettingsLabel(option.label, option.value),
    }));
  }
  return normalized;
}

export function mapSettingsSectionId(sectionId: string | null | undefined): ControlCenterSectionId | null {
  if (!sectionId) return null;
  const normalized = sectionId.trim().toLowerCase();
  return SECTION_ID_ALIASES[normalized] ?? null;
}

export function controlCenterSectionForField(section: SettingsSection, field: SettingsField): ControlCenterSectionId {
  const fieldRecord = field as SettingsField & Record<string, unknown>;
  const explicit = mapSettingsSectionId(String(fieldRecord.control_center_section ?? fieldRecord.section ?? ""));
  if (explicit) return explicit;
  const sectionMatch = mapSettingsSectionId(section.id);
  if (
    sectionMatch === "computer_automation"
    || sectionMatch === "accounts_connections"
    || sectionMatch === "privacy_security"
  ) {
    return sectionMatch;
  }
  const haystack = [
    field.id,
    field.label,
    field.help ?? "",
    field.type,
  ].join(" ");
  for (const [pattern, target] of FIELD_TOKEN_ALIASES) {
    if (pattern.test(haystack)) return target;
  }
  return sectionMatch ?? "packs_extensions";
}

export function buildControlCenterSections(settingsSections: SettingsSection[]): ControlCenterSection[] {
  const sections = controlCenterSectionMeta();
  const byId = new Map(sections.map((section) => [section.id, section]));
  for (const sourceSection of settingsSections) {
    const sourceSectionTargets = new Set<ControlCenterSectionId>();
    for (const rawField of sourceSection.fields) {
      const targetId = controlCenterSectionForField(sourceSection, rawField);
      sourceSectionTargets.add(targetId);
      const target = byId.get(targetId);
      if (!target) continue;
      const field = normalizeSettingsField(rawField) as ControlCenterField;
      field.controlSectionId = targetId;
      field.sourceSectionId = sourceSection.id;
      field.sourceSectionLabel = safeSettingsLabel(sourceSection.label, sourceSection.id);
      field.sourceSectionDescription = sourceSection.description;
      target.fields.push(field);
    }
    const fallbackTargetId = mapSettingsSectionId(sourceSection.id) ?? "packs_extensions";
    sourceSectionTargets.add(fallbackTargetId);
    for (const targetId of sourceSectionTargets) {
      byId.get(targetId)?.sourceSections.push(sourceSection);
    }
  }
  const quickSetup = byId.get("quick_setup");
  if (quickSetup) {
    quickSetup.fields = selectQuickSetupFields(sections);
  }
  return sections;
}

export function filterControlCenterSections(
  sections: ControlCenterSection[],
  searchQuery: string,
): ControlCenterSection[] {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return sections;
  return sections.filter((section) => {
    const sectionText = [section.id, section.label, section.description, section.help].join(" ").toLowerCase();
    return sectionText.includes(query) || section.fields.some((field) => settingsFieldSearchText(field).includes(query));
  });
}

function selectQuickSetupFields(sections: ControlCenterSection[]): ControlCenterField[] {
  const wanted = new Set(["models_api", "accounts_connections", "tools_mcp", "computer_automation"]);
  const scored = sections
    .filter((section) => wanted.has(section.id))
    .flatMap((section) => section.fields.map((field) => ({ field, score: quickSetupScore(field) })))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.field.sourceSectionLabel.localeCompare(b.field.sourceSectionLabel));

  const seen = new Set<string>();
  const selected: ControlCenterField[] = [];
  for (const { field } of scored) {
    const key = `${field.sourceSectionId}.${field.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    selected.push({ ...field, controlSectionId: "quick_setup" });
    if (selected.length >= 6) break;
  }
  return selected;
}

function quickSetupScore(field: ControlCenterField): number {
  const text = [field.id, field.label, field.help ?? "", field.type].join(" ").toLowerCase();
  const fieldType = String(field.type);
  let score = 0;
  if (/default|preferred|api[_ -]?key|provider|model/.test(text)) score += 50;
  if (/cloudflare|google|gmail|drive|codex|connection|oauth|continuity/.test(text)) score += 40;
  if (/computer|browser|screen|accessibility|approval|mcp/.test(text)) score += 30;
  if (fieldType === "secret" || fieldType === "api_key_setup" || fieldType === "model_select") score += 20;
  if ((field as SettingsField & { advanced?: boolean }).advanced) score -= 40;
  return score;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

const GOOGLE_ACCOUNT_SCOPE_MODE_IDS = new Set([
  "google_identity",
  "google_drive",
  "google_gmail_labels",
  "google_gmail_metadata",
  "google_gmail_readonly",
]);

const GOOGLE_ACCOUNT_SCOPE_MODE_FALLBACKS: AccountConnectionScopeModeOption[] = [
  {
    id: "google_identity",
    label: "Google identity",
    description: "Basic sign-in identity only.",
    scopes: ["openid", "email", "profile"],
    services: ["identity"],
    restricted: false,
    warning: "",
  },
  {
    id: "google_drive",
    label: "Google Drive selected files",
    description: "Drive file scope for files explicitly selected or shared with Rumi.",
    scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.file"],
    services: ["identity", "drive_file"],
    restricted: false,
    warning: "",
  },
  {
    id: "google_gmail_labels",
    label: "Gmail labels",
    description: "Read Gmail labels without message bodies.",
    scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.labels"],
    services: ["identity", "gmail_labels"],
    restricted: false,
    warning: "",
  },
  {
    id: "google_gmail_metadata",
    label: "Gmail metadata/search",
    description: "Restricted metadata/search scope for Gmail.",
    scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.metadata"],
    services: ["identity", "gmail_metadata"],
    restricted: true,
    warning: "Restricted Gmail scopes require explicit self-host acknowledgement or Google verification review.",
  },
  {
    id: "google_gmail_readonly",
    label: "Gmail read-only bodies",
    description: "Restricted read-only access to Gmail message bodies.",
    scopes: ["openid", "email", "profile", "https://www.googleapis.com/auth/gmail.readonly"],
    services: ["identity", "gmail_readonly"],
    restricted: true,
    warning: "Restricted Gmail scopes can expose message content and may require Google security review.",
  },
];

function accountScopeModeOptions(value: unknown): AccountConnectionScopeModeOption[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const row = recordValue(item);
    const id = String(row.id ?? "").trim();
    const surface = String(row.surface ?? "").trim();
    if (!id || !GOOGLE_ACCOUNT_SCOPE_MODE_IDS.has(id) || surface === "models_api") return [];
    return [{
      id,
      label: String(row.label || id),
      description: String(row.description || ""),
      scopes: stringList(row.scopes),
      services: stringList(row.services),
      restricted: Boolean(row.restricted),
      warning: String(row.warning || ""),
    }];
  });
}

function oauthStatusForProvider(settingsValues: SettingsValues, providerId: string): Record<string, unknown> {
  const apiRows = Array.isArray(settingsValues.apis?.api_keys) ? settingsValues.apis.api_keys : [];
  for (const row of apiRows) {
    const provider = recordValue(row);
    if (String(provider.provider_id ?? "").trim() !== providerId) continue;
    return recordValue(provider.oauth);
  }
  const connections = recordValue(settingsValues.accounts_connections?.providers);
  return recordValue(connections[providerId]);
}

export function buildAccountConnectionPrelude(settingsValues: SettingsValues = {}): AccountConnectionPreludeCard[] {
  const definitions: Array<{
    providerId: AccountConnectionPreludeCard["providerId"];
    label: string;
    description: string;
    fallbackStatus: Record<string, unknown>;
    scopeMode?: string;
    configureSectionId: ControlCenterSectionId;
    configureLabel: string;
    credential?: (status: Record<string, unknown>) => AccountConnectionPreludeCard["credential"];
  }> = [
    {
      providerId: "cloudflare",
      label: "Cloudflare",
      description: "Continue Rumi tasks in the user's Cloudflare account when this computer is offline.",
      fallbackStatus: {
        backend_supported: false,
        connect_enabled: false,
        connected: false,
        connection_status: "missing_scope_config",
        status_label: "Missing scope config",
        disabled_reason: "Configure self-host OAuth",
        scopes: [],
      },
      scopeMode: undefined,
      configureSectionId: "accounts_connections" as const,
      configureLabel: "Configure self-host OAuth",
    },
    {
      providerId: "google",
      label: "Google",
      description: "Connect Google identity, Drive selected files, Gmail labels, or explicit restricted Gmail modes.",
      fallbackStatus: {
        backend_supported: true,
        connect_enabled: false,
        connected: false,
        connection_status: "missing_self_host_config",
        status_label: "Client config needed",
        disabled_reason: "Configure self-host OAuth",
        scopes: [],
        scope_mode: "google_identity",
        scope_modes: GOOGLE_ACCOUNT_SCOPE_MODE_FALLBACKS,
      },
      scopeMode: "google_identity",
      configureSectionId: "models_api" as const,
      configureLabel: "Configure self-host OAuth",
    },
    {
      providerId: "codex",
      label: "Codex",
      description: "Save the local/programmatic Codex workflow access credential.",
      fallbackStatus: {
        supported: true,
        backend_supported: true,
        connect_enabled: false,
        connected: false,
        configured: false,
        token_configured: false,
        can_clear: false,
        connection_status: "missing_token",
        status_label: "Token needed",
        disabled_reason: "Save Codex access token",
      },
      configureSectionId: "privacy_security" as const,
      configureLabel: "Review credential policy",
      credential: (status) => ({
        kind: "codex_access_token",
        configured: Boolean(status.token_configured ?? status.configured ?? status.connected),
        canClear: Boolean(status.can_clear),
        placeholder: "Codex access token",
        saveLabel: Boolean(status.token_configured ?? status.configured ?? status.connected) ? "Update token" : "Save token",
        clearLabel: "Clear token",
      }),
    },
  ];
  return definitions.map((definition) => {
    const status = {
      ...definition.fallbackStatus,
      ...oauthStatusForProvider(settingsValues, definition.providerId),
    };
    const connected = Boolean(status.connected);
    const canConnect = Boolean(status.connect_enabled);
    const credential = definition.credential?.(status);
    const disabledReason = connected || canConnect ? "" : String(status.disabled_reason || status.status_label || "Configure self-host OAuth");
    const scopeModes = definition.providerId === "google"
      ? accountScopeModeOptions(status.scope_modes).length
        ? accountScopeModeOptions(status.scope_modes)
        : GOOGLE_ACCOUNT_SCOPE_MODE_FALLBACKS
      : [];
    const requestedScopeMode = String(status.scope_mode || definition.scopeMode || "").trim();
    const selectedScopeMode = scopeModes.some((option) => option.id === requestedScopeMode)
      ? requestedScopeMode
      : scopeModes[0]?.id ?? definition.scopeMode;
    const selectedScopeModeOption = scopeModes.find((option) => option.id === selectedScopeMode);
    const selectedServices = selectedScopeModeOption?.services ?? [];
    return {
      providerId: definition.providerId,
      label: definition.label,
      description: definition.description,
      connected,
      statusLabel: String(status.status_label || (connected ? "Connected" : "Disconnected")),
      status: String(status.connection_status || (connected ? "connected" : "disconnected")),
      canConnect,
      connectAction: canConnect && !credential
        ? { providerId: definition.providerId, scopeMode: selectedScopeMode, services: selectedServices }
        : undefined,
      primaryLabel: definition.providerId === "google"
        ? connected ? "Reconnect selected mode" : "Connect selected mode"
        : connected ? `Reconnect ${definition.label}` : `Connect ${definition.label}`,
      disabledReason,
      officialAppDescription: credential
        ? "Stored through local secret storage and only exposed as configured status."
        : "Official app required for hosted broker mode.",
      selfHostDescription: credential
        ? "Separate from Platform API keys and Workspace Agent tokens."
        : disabledReason === "Configure self-host OAuth"
        ? "Configure self-host OAuth with explicit scopes before connecting."
        : "Self-host OAuth remains available when a client and scopes are configured.",
      configureSectionId: definition.configureSectionId,
      configureLabel: definition.configureLabel,
      scopeMode: selectedScopeMode,
      services: selectedServices,
      scopes: selectedScopeModeOption?.scopes.length ? selectedScopeModeOption.scopes : stringList(status.scopes),
      scopeModes,
      credential,
    };
  });
}

export function buildCodexAppServerPrelude(settingsValues: SettingsValues = {}): CodexAppServerPrelude {
  const toolsMcp = recordValue(settingsValues.tools_mcp);
  const appServer = recordValue(toolsMcp.codex_app_server);
  const toolSource = recordValue(appServer.tool_source);
  const automationEndpoint = recordValue(appServer.automation_endpoint);
  const configured = Boolean(appServer.configured);
  const enabled = Boolean(appServer.enabled);
  const status = String(appServer.connection_status || (configured ? "configured" : "not_configured"));
  return {
    configured,
    enabled,
    statusLabel: String(appServer.status_label || (configured ? "Configured" : "Not configured")),
    status,
    blockedReason: String(appServer.blocked_reason || ""),
    baseUrl: String(appServer.base_url || ""),
    websocketUrl: String(appServer.websocket_url || ""),
    loopback: appServer.loopback !== false,
    authRequired: Boolean(appServer.auth_required),
    authConfigured: Boolean(appServer.auth_configured),
    toolSourceStatus: String(toolSource.status || "disabled"),
    automationEndpointStatus: String(automationEndpoint.status || "disabled"),
  };
}
