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

const BLOCKED_RAW_LABELS = new Map([
  ["mimo", "Mimo model preset"],
  ["computer_use_gradient", "Automation visual indicator"],
  ["openrouter_auto", "OpenRouter auto routing"],
]);

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
  [/\b(oauth|account|connection|connect|gmail|drive|google|cloudflare|github)\b/i, "accounts_connections"],
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
  return BLOCKED_RAW_LABELS.get(label.toLowerCase()) ?? label;
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
  if (/cloudflare|google|gmail|drive|connection|oauth|continuity/.test(text)) score += 40;
  if (/computer|browser|screen|accessibility|approval|mcp/.test(text)) score += 30;
  if (fieldType === "secret" || fieldType === "api_key_setup" || fieldType === "model_select") score += 20;
  if ((field as SettingsField & { advanced?: boolean }).advanced) score -= 40;
  return score;
}
