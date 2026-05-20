import { useEffect, useMemo, useState, type ReactElement } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown, Copy, Loader2, MoreVertical, Pencil, Search, Trash2, X } from "lucide-react";

import { cn } from "../lib/cn";
import { api } from "../lib/api";
import type { ModelSearchItem, SettingsSection } from "../lib/api";
import { t } from "../lib/i18n";
import { selectedApisForModel, toggleModelApiRoute, updateModelApiRouteText } from "../lib/modelApiRoutes";
import { settingsFieldSearchText, settingsSectionSearchText } from "../lib/settingsSearch";
import type { SettingsModalRendererProps } from "./types";

function formatReadonlyValue(value: unknown, fallback: unknown): string {
  const resolved = value ?? fallback ?? "";
  if (typeof resolved === "boolean") return resolved ? "Saved" : "Not set";
  if (resolved && typeof resolved === "object") return JSON.stringify(resolved, null, 2);
  return String(resolved);
}

async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function apiProviderRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function namedApiRows(provider: Record<string, unknown>): Array<Record<string, unknown>> {
  const apis = provider.apis;
  return Array.isArray(apis) ? apis.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function registeredApiRows(providers: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = providers.flatMap((provider) => (
    namedApiRows(provider).map((api) => ({
      ...api,
      provider_id: api.provider_id ?? provider.provider_id,
    }))
  ));
  return rows.filter((api) => Boolean(api.configured));
}

function modelRouteOptions(field: SettingsSection["fields"][number]): NonNullable<SettingsSection["fields"][number]["options"]> {
  return Array.isArray(field.options)
    ? field.options.filter((item) => Boolean(item) && typeof item === "object")
    : [];
}

function fieldApiProviderRows(field: SettingsSection["fields"][number]): Array<Record<string, unknown>> {
  return Array.isArray(field.api_keys)
    ? field.api_keys.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    : [];
}

function routeProviderForOption(option: SettingsModelOption | NonNullable<SettingsSection["fields"][number]["options"]>[number] | undefined, modelId: string): string {
  const provider = String(option?.provider_id ?? "").trim();
  if (provider) return provider;
  return modelId.includes("/") ? modelId.split("/", 1)[0] ?? "" : "";
}

function apiRefForRoute(api: Record<string, unknown>, fallbackProvider: string): string {
  const providerId = String(api.provider_id ?? fallbackProvider ?? "").trim();
  const apiId = String(api.api_id ?? "").trim();
  return providerId && apiId ? `${providerId}/${apiId}` : "";
}

function oauthProviderRows(providers: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return providers.filter((provider) => {
    const oauth = provider.oauth;
    return Boolean(oauth) && typeof oauth === "object" && Boolean((oauth as Record<string, unknown>).supported);
  });
}

function apiRowLabel(api: Record<string, unknown>): string {
  return String(api.label ?? `${api.provider_id}:${api.api_id}:***`);
}

function externalTokenProviderRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function namedTokenRows(provider: Record<string, unknown>): Array<Record<string, unknown>> {
  const tokens = provider.tokens;
  return Array.isArray(tokens) ? tokens.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function registeredExternalTokenRows(providers: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = providers.flatMap((provider) => (
    namedTokenRows(provider).map((token) => ({
      ...token,
      provider_id: token.provider_id ?? provider.provider_id,
    }))
  ));
  return rows.filter((token) => Boolean(token.configured));
}

function requiredExternalTokenRows(providers: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return providers.flatMap((provider) => {
    const required = provider.required_tokens;
    if (!Array.isArray(required)) return [];
    return required
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((item) => ({ ...item, provider_id: provider.provider_id }));
  });
}

function MaskedApiLabel({ api }: { api: Record<string, unknown> }) {
  const providerId = String(api.provider_id ?? "");
  const apiId = String(api.api_id ?? "");
  const fallback = apiRowLabel(api);
  if (!providerId || !apiId) {
    return <span className="truncate text-xs text-zinc-300">{fallback}</span>;
  }
  return (
    <span className="inline-flex max-w-full items-center overflow-hidden font-mono text-xs leading-5 text-zinc-500">
      <span className="truncate">{providerId}</span>
      <span className="px-0.5 text-zinc-600">:</span>
      <span className="truncate">{apiId}</span>
      <span className="px-0.5 text-zinc-600">:</span>
      <span className="tracking-normal text-zinc-500">***</span>
    </span>
  );
}

function MaskedExternalTokenLabel({ token }: { token: Record<string, unknown> }) {
  const providerId = String(token.provider_id ?? "");
  const tokenId = String(token.token_id ?? "");
  const fallback = String(token.label ?? `${providerId}:${tokenId}:***`);
  if (!providerId || !tokenId) {
    return <span className="truncate text-xs text-zinc-300">{fallback}</span>;
  }
  return (
    <span className="inline-flex max-w-full items-center overflow-hidden font-mono text-xs leading-5 text-zinc-500">
      <span className="truncate">{providerId}</span>
      <span className="px-0.5 text-zinc-600">:</span>
      <span className="truncate">{tokenId}</span>
      <span className="px-0.5 text-zinc-600">:</span>
      <span className="tracking-normal text-zinc-500">***</span>
    </span>
  );
}

function externalTokenKindOptions(providerId: string): Array<{ value: string; label: string }> {
  const common: Record<string, Array<{ value: string; label: string }>> = {
    line: [
      { value: "channel_secret", label: "Messaging API Channel Secret" },
      { value: "channel_access_token", label: "Messaging API Channel Access Token" },
      { value: "reply_token", label: "Reply Token" },
    ],
    discord: [
      { value: "bot_token", label: "Bot Token" },
      { value: "webhook_url", label: "Webhook URL" },
      { value: "application_id", label: "Application ID" },
      { value: "public_key", label: "Public Key" },
    ],
    slack: [
      { value: "bot_token", label: "Bot Token" },
      { value: "signing_secret", label: "Signing Secret" },
      { value: "app_token", label: "App Token" },
      { value: "channel_id", label: "Channel ID" },
    ],
    generic: [
      { value: "webhook_shared_secret", label: "Webhook Shared Secret" },
      { value: "webhook_url", label: "Webhook URL" },
      { value: "callback_url", label: "Callback URL" },
    ],
    web: [
      { value: "callback_url", label: "Callback URL" },
    ],
  };
  return common[providerId] ?? [
    { value: "token", label: "Token" },
    { value: "webhook_url", label: "Webhook URL" },
  ];
}

function CustomSelect({
  value,
  options,
  onChange,
  className,
}: {
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value) ?? options[0];
  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700"
      >
        <span className="truncate">{selected?.label ?? value}</span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="close select" className="fixed inset-0 z-10 cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 max-h-56 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-1 shadow-2xl">
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                  option.value === value ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                )}
              >
                <span className="truncate">{option.label}</span>
                {option.value === value && <Check size={13} className="shrink-0 text-emerald-300" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

type SettingsModelOption = {
  value: string;
  label: string;
  provider_id?: string;
  provider_display_name?: string;
  model_id?: string;
  qualified_model_id?: string;
  configured?: boolean;
  local?: boolean;
  supports_vision?: boolean;
  supports_image_input?: boolean;
  supports_tool_calling?: boolean;
  supports_thinking?: boolean;
  supports_fast?: boolean;
  speed_tier?: string;
  quality_tier?: string;
  cost_tier?: string;
  knowledge_level?: number;
  capability_tags?: string[];
  recommended_roles?: string[];
  notes?: string;
};

function modelFieldOptionToOption(option: NonNullable<SettingsSection["fields"][number]["options"]>[number]): SettingsModelOption {
  return {
    value: String(option.value ?? ""),
    label: String(option.label ?? option.value ?? ""),
    provider_id: option.provider_id,
    provider_display_name: option.provider_display_name,
    model_id: option.model_id,
    qualified_model_id: option.qualified_model_id,
    configured: option.configured,
    local: option.local,
    supports_vision: option.supports_vision,
    supports_image_input: option.supports_image_input,
    supports_tool_calling: option.supports_tool_calling,
    supports_thinking: option.supports_thinking,
    supports_fast: option.supports_fast,
    speed_tier: option.speed_tier,
    quality_tier: option.quality_tier,
    cost_tier: option.cost_tier,
    knowledge_level: option.knowledge_level,
    capability_tags: option.capability_tags,
    recommended_roles: option.recommended_roles,
    notes: option.notes,
  };
}

function modelSearchItemToOption(item: ModelSearchItem): SettingsModelOption {
  return {
    value: String(item.profile_id ?? item.qualified_model_id ?? `${item.provider_id ?? ""}/${item.model_id ?? ""}`),
    label: String(item.label ?? item.display_name ?? item.profile_id ?? ""),
    provider_id: item.provider_id,
    provider_display_name: item.provider_display_name,
    model_id: item.model_id,
    qualified_model_id: item.qualified_model_id,
    configured: item.configured,
    local: Boolean(item.local),
    supports_vision: item.supports_vision,
    supports_image_input: item.supports_image_input,
    supports_tool_calling: item.supports_tool_calling,
    supports_thinking: item.supports_thinking,
    supports_fast: item.supports_fast,
    speed_tier: item.speed_tier,
    quality_tier: item.quality_tier,
    cost_tier: item.cost_tier,
    knowledge_level: item.knowledge_level,
    capability_tags: item.capability_tags,
    recommended_roles: item.recommended_roles,
    notes: item.notes,
  };
}

function modelOptionSearchText(option: SettingsModelOption): string {
  return [
    option.value,
    option.label,
    option.provider_id,
    option.provider_display_name,
    option.model_id,
    option.qualified_model_id,
    option.speed_tier,
    option.quality_tier,
    option.cost_tier,
    option.notes,
    ...(option.capability_tags ?? []),
    ...(option.recommended_roles ?? []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function normalizeModelSearchText(value: string): string {
  return value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

function modelOptionMatchesSearch(option: SettingsModelOption, query: string): boolean {
  const rawText = modelOptionSearchText(option);
  const normalizedText = normalizeModelSearchText(rawText);
  const rawQuery = query.trim().toLowerCase();
  const normalizedQuery = normalizeModelSearchText(rawQuery);
  if (!normalizedQuery) return true;
  if (rawText.includes(rawQuery) || normalizedText.includes(normalizedQuery)) return true;
  return normalizedQuery.split(/\s+/).every((token) => normalizedText.includes(token) || rawText.includes(token));
}

function dedupeModelOptions(options: SettingsModelOption[]): SettingsModelOption[] {
  const seen = new Set<string>();
  const deduped: SettingsModelOption[] = [];
  for (const option of options) {
    if (!option.value || seen.has(option.value)) continue;
    seen.add(option.value);
    deduped.push(option);
  }
  return deduped;
}

function modelOptionBadges(option: SettingsModelOption): string[] {
  const badges: string[] = [];
  if (option.configured) badges.push("ready");
  if (option.local) badges.push("local");
  if (option.supports_vision || option.supports_image_input) badges.push("vision");
  if (option.supports_tool_calling) badges.push("tools");
  if (option.supports_thinking) badges.push("thinking");
  if (option.supports_fast || option.speed_tier === "fast") badges.push("fast");
  if (option.cost_tier && option.cost_tier !== "unknown") badges.push(option.cost_tier);
  return badges.slice(0, 4);
}

function SettingsModelSearchSelect({
  value,
  options,
  onChange,
  placeholder = "モデルを検索",
}: {
  value: string;
  options: SettingsModelOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [remoteResults, setRemoteResults] = useState<ModelSearchItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const trimmedQuery = query.trim();
  const selected = options.find((option) => option.value === value || option.qualified_model_id === value)
    ?? remoteResults.map(modelSearchItemToOption).find((option) => option.value === value || option.qualified_model_id === value)
    ?? (value ? { value, label: value } : null);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      api.searchModels({ query: query.trim(), max_results: 30 })
        .then((result) => {
          setRemoteResults(result.models ?? []);
        })
        .catch((searchError: unknown) => {
          setRemoteResults([]);
          setError(searchError instanceof Error ? searchError.message : "Model search failed");
        })
        .finally(() => setBusy(false));
    }, query.trim() ? 160 : 0);
    return () => window.clearTimeout(timer);
  }, [open, query]);

  const visibleOptions = useMemo(() => {
    const localMatches = trimmedQuery
      ? options.filter((option) => modelOptionMatchesSearch(option, trimmedQuery))
      : options;
    const merged = dedupeModelOptions([
      ...(selected ? [selected] : []),
      ...localMatches,
      ...remoteResults.map(modelSearchItemToOption),
    ]);
    return merged.slice(0, 40);
  }, [trimmedQuery, options, remoteResults, selected]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700 focus:border-emerald-500/70"
      >
        <span className="min-w-0">
          <span className="block truncate">{selected?.label || value || "Select model"}</span>
          {(selected?.provider_id || selected?.model_id) && (
            <span className="block truncate text-[11px] text-zinc-500">
              {[selected.provider_id, selected.model_id].filter(Boolean).join(" / ")}
            </span>
          )}
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="close model search" className="fixed inset-0 z-10 cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-2xl">
            <label className="m-2 flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-black/30 px-3 text-xs text-zinc-500 focus-within:border-zinc-600 focus-within:text-zinc-300">
              <Search size={14} />
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={placeholder}
                className="min-w-0 flex-1 bg-transparent text-zinc-200 outline-none placeholder:text-zinc-600"
              />
              {busy && <Loader2 size={13} className="animate-spin text-zinc-500" />}
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300"
                  aria-label="clear model search"
                >
                  <X size={13} />
                </button>
              )}
            </label>
            {error && <div className="border-t border-zinc-800 px-3 py-2 text-[11px] text-rose-300">{error}</div>}
            <div className="max-h-72 overflow-y-auto border-t border-zinc-800 p-1">
              {visibleOptions.length > 0 ? visibleOptions.map((option) => {
                const active = option.value === value || option.qualified_model_id === value;
                const badges = modelOptionBadges(option);
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      onChange(option.value);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-start justify-between gap-3 rounded-md px-2.5 py-2 text-left transition-colors",
                      active ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-zinc-100">{option.label}</span>
                      <span className="block truncate text-[11px] text-zinc-500">
                        {[option.provider_id, option.model_id || option.qualified_model_id || option.value].filter(Boolean).join(" / ")}
                      </span>
                    </span>
                    <span className="flex max-w-[160px] flex-wrap justify-end gap-1">
                      {badges.map((badge) => (
                        <span key={badge} className="rounded-full border border-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400">
                          {badge}
                        </span>
                      ))}
                      {active && <Check size={13} className="mt-1 shrink-0 text-emerald-300" />}
                    </span>
                  </button>
                );
              }) : (
                <div className="px-3 py-5 text-xs text-zinc-600">一致するモデルがありません。</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function publicUrlConfig(value: unknown, fallback: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  if (fallback && typeof fallback === "object" && !Array.isArray(fallback)) return fallback as Record<string, unknown>;
  return {};
}

function ProviderOAuthPanel({
  sectionId,
  fieldId,
  providers,
  onRefresh,
}: {
  sectionId: string;
  fieldId: string;
  providers: Array<Record<string, unknown>>;
  onRefresh: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const [clientDrafts, setClientDrafts] = useState<Record<string, string>>({});
  const [busyAction, setBusyAction] = useState("");
  const [messages, setMessages] = useState<Record<string, { tone: "success" | "error"; text: string }>>({});
  const oauthProviders = oauthProviderRows(providers);

  if (!oauthProviders.length) {
    return null;
  }

  const refresh = (providerId: string) => onRefresh(sectionId, fieldId, { action: "oauth_refresh", provider_id: providerId });

  return (
    <div className="space-y-3">
      {oauthProviders.map((provider) => {
        const providerId = String(provider.provider_id ?? "");
        const oauth = provider.oauth as Record<string, unknown>;
        const connected = Boolean(oauth.connected);
        const clientConfigured = Boolean(oauth.client_configured);
        const displayName = String(oauth.display_name ?? oauth.email ?? "");
        const email = String(oauth.email ?? "");
        const expiresAt = String(oauth.expires_at ?? "");
        const hint = String(oauth.config_hint ?? "");
        const scopes = Array.isArray(oauth.scopes) ? oauth.scopes.map((scope) => String(scope)).filter(Boolean) : [];
        const draft = clientDrafts[providerId] ?? "";
        const isBusy = busyAction.startsWith(`${providerId}:`);
        const banner = messages[providerId];
        const stateLabel = connected ? "Connected" : clientConfigured ? "Ready to connect" : "Client config needed";
        const stateTone = connected
          ? "border-emerald-800 bg-emerald-950/20 text-emerald-300"
          : clientConfigured
            ? "border-cyan-800 bg-cyan-950/20 text-cyan-300"
            : "border-zinc-800 bg-zinc-950 text-zinc-400";

        return (
          <div key={providerId} className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-medium text-zinc-100">{providerId} browser login</h4>
                  <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", stateTone)}>
                    {stateLabel}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-zinc-500">
                  {connected
                    ? `Connected${displayName ? ` as ${displayName}` : ""}${email ? ` (${email})` : ""}.`
                    : hint}
                </p>
                {expiresAt && (
                  <p className="mt-1 text-[11px] text-zinc-600">Access token expires at: {expiresAt}</p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={isBusy || !clientConfigured}
                  onClick={async () => {
                    let popup: Window | null = null;
                    try {
                      popup = window.open("", `rumi-oauth-${providerId}`, "popup=yes,width=560,height=760");
                      setBusyAction(`${providerId}:start`);
                      const result = await api.startProviderOAuth(providerId);
                      if (popup) {
                        popup.location.href = result.authorize_url;
                        popup.focus();
                      } else {
                        window.location.href = result.authorize_url;
                      }
                      setMessages((current) => ({
                        ...current,
                        [providerId]: { tone: "success", text: "Browser login opened in a new window." },
                      }));
                    } catch (errorValue) {
                      if (popup && !popup.closed) {
                        popup.close();
                      }
                      setMessages((current) => ({
                        ...current,
                        [providerId]: {
                          tone: "error",
                          text: errorValue instanceof Error ? errorValue.message : "Failed to start browser login.",
                        },
                      }));
                    } finally {
                      setBusyAction("");
                    }
                  }}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs transition-colors",
                    isBusy || !clientConfigured
                      ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                      : "border-cyan-700 bg-cyan-950/30 text-cyan-100 hover:border-cyan-500 hover:bg-cyan-900/35",
                  )}
                >
                  {isBusy && busyAction === `${providerId}:start` ? "Opening..." : connected ? "Reconnect in browser" : "Connect in browser"}
                </button>
                <button
                  type="button"
                  disabled={isBusy || !connected}
                  onClick={async () => {
                    try {
                      setBusyAction(`${providerId}:disconnect`);
                      await api.disconnectProviderOAuth(providerId);
                      refresh(providerId);
                      setMessages((current) => ({
                        ...current,
                        [providerId]: { tone: "success", text: "Browser login disconnected." },
                      }));
                    } catch (errorValue) {
                      setMessages((current) => ({
                        ...current,
                        [providerId]: {
                          tone: "error",
                          text: errorValue instanceof Error ? errorValue.message : "Failed to disconnect browser login.",
                        },
                      }));
                    } finally {
                      setBusyAction("");
                    }
                  }}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs transition-colors",
                    isBusy || !connected
                      ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                      : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:border-zinc-500",
                  )}
                >
                  Disconnect
                </button>
                <button
                  type="button"
                  disabled={isBusy || !clientConfigured}
                  onClick={async () => {
                    try {
                      setBusyAction(`${providerId}:clear`);
                      await api.clearProviderOAuthClientConfig(providerId);
                      setClientDrafts((current) => ({ ...current, [providerId]: "" }));
                      refresh(providerId);
                      setMessages((current) => ({
                        ...current,
                        [providerId]: { tone: "success", text: "Saved OAuth client config cleared." },
                      }));
                    } catch (errorValue) {
                      setMessages((current) => ({
                        ...current,
                        [providerId]: {
                          tone: "error",
                          text: errorValue instanceof Error ? errorValue.message : "Failed to clear OAuth client config.",
                        },
                      }));
                    } finally {
                      setBusyAction("");
                    }
                  }}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs transition-colors",
                    isBusy || !clientConfigured
                      ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                      : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-200",
                  )}
                >
                  Clear client
                </button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_auto]">
              <textarea
                value={draft}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  setClientDrafts((current) => ({ ...current, [providerId]: nextValue }));
                  setMessages((current) => {
                    if (!(providerId in current)) return current;
                    const next = { ...current };
                    delete next[providerId];
                    return next;
                  });
                }}
                placeholder='Paste Google OAuth desktop client JSON or a client ID like "123....apps.googleusercontent.com"'
                className="min-h-28 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-cyan-500"
              />
              <div className="flex flex-col justify-between gap-3">
                <button
                  type="button"
                  disabled={isBusy || !draft.trim()}
                  onClick={async () => {
                    try {
                      setBusyAction(`${providerId}:save`);
                      await api.saveProviderOAuthClientConfig(providerId, draft);
                      setClientDrafts((current) => ({ ...current, [providerId]: "" }));
                      refresh(providerId);
                      setMessages((current) => ({
                        ...current,
                        [providerId]: { tone: "success", text: "OAuth client config saved." },
                      }));
                    } catch (errorValue) {
                      setMessages((current) => ({
                        ...current,
                        [providerId]: {
                          tone: "error",
                          text: errorValue instanceof Error ? errorValue.message : "Failed to save OAuth client config.",
                        },
                      }));
                    } finally {
                      setBusyAction("");
                    }
                  }}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm transition-colors",
                    isBusy || !draft.trim()
                      ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
                      : "border-zinc-100 bg-zinc-100 text-zinc-950",
                  )}
                >
                  {isBusy && busyAction === `${providerId}:save` ? "Saving..." : "Save OAuth client"}
                </button>
                {scopes.length > 0 && (
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-[11px] text-zinc-500">
                    Scopes: {scopes.join(", ")}
                  </div>
                )}
              </div>
            </div>
            {banner && (
              <p className={cn("mt-3 text-[11px]", banner.tone === "success" ? "text-emerald-400" : "text-rose-300")}>
                {banner.text}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PublicUrlField({
  sectionId,
  field,
  value,
  onChange,
}: {
  sectionId: string;
  field: SettingsSection["fields"][number];
  value: unknown;
  onChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const config = publicUrlConfig(value, field.default);
  const [providerId, setProviderId] = useState(String(config.provider_id ?? "cloudflare_quick_tunnel"));
  const [localUrl, setLocalUrl] = useState(String(config.local_url ?? "http://127.0.0.1:8766"));
  const [routePath, setRoutePath] = useState(String(config.route_path ?? "/api/integrations/line/webhook"));
  const [result, setResult] = useState<Record<string, unknown> | null>(
    config.result && typeof config.result === "object" ? config.result as Record<string, unknown> : null,
  );
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const next = publicUrlConfig(value, field.default);
    setProviderId(String(next.provider_id ?? "cloudflare_quick_tunnel"));
    setLocalUrl(String(next.local_url ?? "http://127.0.0.1:8766"));
    setRoutePath(String(next.route_path ?? "/api/integrations/line/webhook"));
    setResult(next.result && typeof next.result === "object" ? next.result as Record<string, unknown> : null);
  }, [field.default, value]);

  const routeOptions = [
    { value: "/api/integrations/line/webhook", label: "LINE webhook" },
    { value: "/api/integrations/discord/interactions", label: "Discord interactions" },
    { value: "/api/integrations/discord/events", label: "Discord events" },
    { value: "/api/integrations/slack/events", label: "Slack events" },
    { value: "/api/webhooks/inbound/{webhook_id}", label: "Generic webhook" },
  ];
  const providerOptions = [
    { value: "cloudflare_quick_tunnel", label: "Cloudflare Quick Tunnel" },
    { value: "static", label: "Static URL" },
  ];
  const publicUrl = String(result?.public_url ?? "");
  const error = String(result?.error ?? "");

  const persist = (nextResult: Record<string, unknown> | null) => {
    onChange(sectionId, field.id, {
      provider_id: providerId,
      local_url: localUrl,
      route_path: routePath,
      result: nextResult,
    });
  };

  const createUrl = async () => {
    setBusy(true);
    setCopied(false);
    try {
      const next = await api.createPublicUrl({
        provider_id: providerId,
        local_url: localUrl,
        route_path: routePath,
      });
      setResult(next);
      persist(next);
    } catch (errorValue) {
      const next = { ok: false, error: errorValue instanceof Error ? errorValue.message : "Failed to create URL" };
      setResult(next);
      persist(next);
    } finally {
      setBusy(false);
    }
  };

  const closeUrl = async () => {
    const urlId = String(result?.url_id ?? "");
    if (urlId && urlId !== "static") {
      await api.closePublicUrl(urlId).catch(console.error);
    }
    setResult(null);
    persist(null);
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1.1fr_1.1fr_1.2fr]">
        <label className="space-y-1.5">
          <span className="text-[11px] font-medium uppercase text-zinc-500">URL provider</span>
          <CustomSelect value={providerId} onChange={setProviderId} options={providerOptions} />
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] font-medium uppercase text-zinc-500">Local Rumi URL</span>
          <input
            value={localUrl}
            onChange={(event) => setLocalUrl(event.target.value)}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500"
            placeholder="http://127.0.0.1:8766"
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] font-medium uppercase text-zinc-500">Webhook route</span>
          <CustomSelect value={routePath} onChange={setRoutePath} options={routeOptions} />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={createUrl}
          disabled={busy || !localUrl.trim() || !routePath.trim()}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
            busy || !localUrl.trim() || !routePath.trim()
              ? "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600"
              : "border-cyan-700 bg-cyan-950/35 text-cyan-100 hover:border-cyan-500 hover:bg-cyan-900/35",
          )}
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : <span className="h-2 w-2 rounded-full bg-cyan-300" />}
          {providerId === "cloudflare_quick_tunnel" ? "Cloudflare URLを発行" : "Webhook URLを作成"}
        </button>
        {publicUrl && (
          <button
            type="button"
            onClick={() => {
              void copyTextToClipboard(publicUrl).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1600);
              });
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 hover:border-zinc-500"
          >
            <Copy size={14} />
            {copied ? "コピー済み" : "Webhook URLをコピー"}
          </button>
        )}
        {result && (
          <button
            type="button"
            onClick={() => void closeUrl()}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-500 hover:text-zinc-200"
          >
            Clear / Close
          </button>
        )}
      </div>
      {publicUrl && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/20 px-3 py-2 font-mono text-xs text-emerald-200 break-all">
          {publicUrl}
        </div>
      )}
      {!publicUrl && error && (
        <div className="rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
          {error}
        </div>
      )}
    </div>
  );
}

function SettingsField({
  sectionId,
  field,
  value,
  sectionValues,
  onChange,
}: {
  sectionId: string;
  field: SettingsSection["fields"][number];
  value: unknown;
  sectionValues?: Record<string, unknown>;
  onChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const [secretDraft, setSecretDraft] = useState("");
  const [secretState, setSecretState] = useState<"idle" | "saved">("idle");
  const [apiProvider, setApiProvider] = useState("google");
  const [apiName, setApiName] = useState("main");
  const [apiSecret, setApiSecret] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiAllowedModels, setApiAllowedModels] = useState("");
  const [apiDefaultModel, setApiDefaultModel] = useState("");
  const [apiQuotaLabel, setApiQuotaLabel] = useState("");
  const [apiNotes, setApiNotes] = useState("");
  const [apiSaveState, setApiSaveState] = useState<"idle" | "saved">("idle");
  const [tokenProvider, setTokenProvider] = useState("line");
  const [tokenName, setTokenName] = useState("main");
  const [tokenKind, setTokenKind] = useState("channel_access_token");
  const [tokenSecret, setTokenSecret] = useState("");
  const [tokenSaveState, setTokenSaveState] = useState<"idle" | "saved">("idle");
  const [renamingKey, setRenamingKey] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [selectedApiKey, setSelectedApiKey] = useState("");
  const [openApiMenuKey, setOpenApiMenuKey] = useState("");
  const [selectedTokenKey, setSelectedTokenKey] = useState("");
  const [openTokenMenuKey, setOpenTokenMenuKey] = useState("");
  const routeOptions = modelRouteOptions(field);
  const routeOptionKey = routeOptions.map((option) => String(option.value ?? "")).join("|");
  const preferredRouteModel = field.type === "model_api_routes" ? String(sectionValues?.preferred_model ?? "").trim() : "";
  const [routeModel, setRouteModel] = useState(() => preferredRouteModel || String(routeOptions[0]?.value ?? ""));
  const [routeModelTouched, setRouteModelTouched] = useState(false);
  useEffect(() => {
    if (field.type !== "model_api_routes") return;
    if (!routeOptions.length) {
      if (routeModel) setRouteModel("");
      return;
    }
    const hasCurrent = routeOptions.some((option) => String(option.value ?? "") === routeModel);
    const hasPreferred = routeOptions.some((option) => String(option.value ?? "") === preferredRouteModel);
    if (!hasCurrent) {
      setRouteModel(hasPreferred ? preferredRouteModel : String(routeOptions[0]?.value ?? ""));
      setRouteModelTouched(false);
      return;
    }
    if (!routeModelTouched && hasPreferred && routeModel !== preferredRouteModel) {
      setRouteModel(preferredRouteModel);
    }
  }, [field.type, preferredRouteModel, routeModel, routeModelTouched, routeOptionKey, routeOptions]);
  const commonLabel = <span className="text-sm text-zinc-300">{field.label}</span>;
  const isSecretConfigured = Boolean(value);

  let control: ReactElement;
  switch (field.type) {
    case "model_api_routes": {
      const routeText = String(value ?? "");
      const selectedModel = routeModel || String(routeOptions[0]?.value ?? "");
      const selectedOption = routeOptions.find((option) => String(option.value ?? "") === selectedModel);
      const selectedProvider = routeProviderForOption(selectedOption, selectedModel);
      const isLocalModel = Boolean(selectedOption?.local) || selectedProvider === "stub";
      const providerRows = fieldApiProviderRows(field);
      const provider = providerRows.find((row) => String(row.provider_id ?? "") === selectedProvider);
      const providerApis = provider ? registeredApiRows([provider]) : [];
      const selectedApis = selectedApisForModel(routeText, selectedModel);
      control = (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(180px,0.42fr)]">
            <label className="space-y-1.5">
              <span className="text-[11px] uppercase tracking-[0.2em] text-zinc-600">Model</span>
              <SettingsModelSearchSelect
                value={selectedModel}
                options={routeOptions.map(modelFieldOptionToOption)}
                placeholder="model/provider/notes で検索"
                onChange={(nextModel) => {
                  setRouteModelTouched(true);
                  setRouteModel(nextModel);
                }}
              />
            </label>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2">
              <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-600">Provider</p>
              <p className="mt-1 font-mono text-sm text-zinc-300">{selectedProvider || "unknown"}</p>
            </div>
          </div>

          {isLocalModel ? (
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-3 text-sm text-zinc-400">
              ローカル/StubモデルはAPIキーのルーティング不要です。
            </div>
          ) : providerApis.length > 0 ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-[0.2em] text-zinc-600">Available API keys</span>
                <span className="text-[11px] text-zinc-500">クリック順がfallback順になります</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {providerApis.map((apiRow) => {
                  const routeRef = apiRefForRoute(apiRow, selectedProvider);
                  const active = selectedApis.includes(routeRef);
                  const order = selectedApis.indexOf(routeRef) + 1;
                  return (
                    <button
                      key={routeRef}
                      type="button"
                      onClick={() => onChange(sectionId, field.id, toggleModelApiRoute(routeText, selectedModel, routeRef))}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors",
                        active
                          ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-200"
                          : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200",
                      )}
                    >
                      {active && <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-400 px-1 text-[10px] font-semibold text-zinc-950">{order}</span>}
                      <MaskedApiLabel api={apiRow} />
                    </button>
                  );
                })}
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs text-zinc-500">
                {selectedApis.length > 0 ? (
                  <span>使用順: <span className="font-mono text-zinc-300">{selectedApis.join(" -> ")}</span></span>
                ) : (
                  <span>このモデルにはまだ使用APIが設定されていません。通常のprovider既定キーを使います。</span>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm text-amber-100">
              {selectedProvider || "このprovider"} のAPI keyがありません。APIs の API Keys に追加してから、ここで選んでください。
            </div>
          )}

          <details className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <summary className="cursor-pointer text-xs text-zinc-500">Advanced: route text</summary>
            <textarea
              value={routeText}
              onChange={(event) => onChange(sectionId, field.id, updateModelApiRouteText(event.target.value, "", []))}
              className="mt-3 min-h-28 w-full resize-y rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-300 outline-none focus:border-zinc-700"
              placeholder="google/gemini-2.5-pro: google/main, google/backup"
            />
          </details>
        </div>
      );
      break;
    }
    case "api_keys": {
      const providers = apiProviderRows(value);
      const providerOptions = providers.length
        ? providers.map((provider) => String(provider.provider_id ?? ""))
        : ["google", "openrouter", "openai", "anthropic"];
      const uniqueProviderOptions = [...new Set(providerOptions.filter(Boolean))];
      const registeredApis = registeredApiRows(providers);
      control = (
        <div className="space-y-4">
          <ProviderOAuthPanel
            sectionId={sectionId}
            fieldId={field.id}
            providers={providers}
            onRefresh={onChange}
          />
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
            <div className="grid grid-cols-[36px_minmax(220px,1.4fr)_minmax(120px,0.8fr)_minmax(90px,0.6fr)_minmax(90px,0.6fr)_48px] items-center gap-3 border-b border-zinc-800 bg-zinc-900/70 px-3 py-2 text-[11px] font-medium text-zinc-500">
              <span className="h-4 w-4 rounded border border-indigo-500/70" />
              <span>Key</span>
              <span>Guardrails</span>
              <span>Expires</span>
              <span>Last Used</span>
              <span />
            </div>
            <div className="divide-y divide-zinc-800/80">
              {registeredApis.length > 0 ? registeredApis.map((api) => {
                const key = String(api.key ?? `${api.provider_id}:${api.api_id}`);
                const isRenaming = renamingKey === key;
                const isMenuOpen = openApiMenuKey === key;
                const isSelected = selectedApiKey === key;
                return (
                  <div
                    key={key}
                    className={cn(
                      "grid grid-cols-[36px_minmax(220px,1.4fr)_minmax(120px,0.8fr)_minmax(90px,0.6fr)_minmax(90px,0.6fr)_48px] items-center gap-3 px-3 py-3 transition-colors",
                      isSelected ? "bg-zinc-900/85" : "bg-zinc-950/20 hover:bg-zinc-900/45",
                    )}
                    onClick={() => setSelectedApiKey(key)}
                  >
                    <span className={cn("h-4 w-4 rounded border", isSelected ? "border-indigo-400 bg-indigo-500/20" : "border-indigo-500/70")} />
                    <div className="min-w-0">
                      {isRenaming ? (
                        <div className="flex items-center gap-1.5">
                          <input
                            value={renameDraft}
                            autoFocus
                            onChange={(event) => setRenameDraft(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key !== "Enter") return;
                              event.preventDefault();
                              if (!renameDraft.trim()) return;
                              onChange(sectionId, field.id, {
                                action: "rename",
                                provider_id: api.provider_id,
                                api_id: api.api_id,
                                name: renameDraft.trim(),
                              });
                              setRenamingKey("");
                            }}
                            className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none"
                          />
                          <button
                            type="button"
                            disabled={!renameDraft.trim()}
                            onClick={(event) => {
                              event.stopPropagation();
                              if (!renameDraft.trim()) return;
                              onChange(sectionId, field.id, {
                                action: "rename",
                                provider_id: api.provider_id,
                                api_id: api.api_id,
                                name: renameDraft.trim(),
                              });
                              setRenamingKey("");
                            }}
                            className="rounded-md border border-zinc-700 p-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                            title="Rename"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setRenamingKey("");
                            }}
                            className="rounded-md border border-zinc-800 p-1 text-zinc-500 hover:text-zinc-300"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="truncate text-sm font-medium text-zinc-200">{String(api.name ?? api.api_id ?? "")}</div>
                          <MaskedApiLabel api={api} />
                        </>
                      )}
                    </div>
	                    <span className="truncate text-sm text-zinc-500">
	                      {String(api.quota_label ?? api.default_model ?? api.base_url ?? "No guardrails")}
	                    </span>
                    <span className="truncate text-sm text-zinc-500">Never</span>
                    <span className="truncate text-sm text-zinc-500">Never</span>
                    <div className="relative flex justify-end">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setOpenApiMenuKey(isMenuOpen ? "" : key);
                        }}
                        className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-500 transition-colors hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-200"
                        title="Actions"
                      >
                        <MoreVertical size={15} />
                      </button>
                      {isMenuOpen && (
                        <>
                          <button
                            type="button"
                            aria-label="close api menu"
                            className="fixed inset-0 z-10 cursor-default"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOpenApiMenuKey("");
                            }}
                          />
                          <div className="absolute right-0 top-[calc(100%+6px)] z-20 w-32 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 py-1 shadow-2xl">
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setRenamingKey(key);
                                setRenameDraft(String(api.name ?? api.api_id ?? ""));
                                setOpenApiMenuKey("");
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800"
                            >
                              <Pencil size={13} />
                              Rename
                            </button>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setOpenApiMenuKey("");
                                onChange(sectionId, field.id, {
                                  action: "delete",
                                  provider_id: api.provider_id,
                                  api_id: api.api_id,
                                });
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-rose-300 hover:bg-rose-950/30"
                            >
                              <Trash2 size={13} />
                              Delete
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                );
              }) : (
                <div className="px-3 py-5 text-xs text-zinc-600">No registered API keys yet.</div>
              )}
            </div>
          </div>
	          <div className="grid gap-2 md:grid-cols-[160px_1fr_1.4fr_auto]">
	            <CustomSelect
              value={apiProvider}
              onChange={setApiProvider}
              options={uniqueProviderOptions.map((providerId) => ({ value: providerId, label: providerId }))}
            />
            <input
              value={apiName}
              onChange={(event) => {
                setApiName(event.target.value);
                setApiSaveState("idle");
              }}
              placeholder="api name"
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
            />
            <input
              type="password"
              autoComplete="off"
              value={apiSecret}
              onChange={(event) => {
                setApiSecret(event.target.value);
                setApiSaveState("idle");
              }}
              placeholder={`${apiProvider} API key`}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
            />
	            <button
              type="button"
              disabled={!apiProvider.trim() || !apiName.trim() || !apiSecret.trim()}
              onClick={() => {
                if (!apiProvider.trim() || !apiName.trim() || !apiSecret.trim()) return;
                onChange(sectionId, field.id, {
                  action: "upsert",
                  provider_id: apiProvider,
	                  api_id: apiName,
	                  name: apiName,
	                  value: apiSecret,
	                  base_url: apiBaseUrl.trim(),
	                  allowed_models: apiAllowedModels.split(",").map((item) => item.trim()).filter(Boolean),
	                  default_model: apiDefaultModel.trim(),
	                  quota_label: apiQuotaLabel.trim(),
	                  notes: apiNotes.trim(),
	                });
	                setApiSecret("");
	                setApiBaseUrl("");
	                setApiAllowedModels("");
	                setApiDefaultModel("");
	                setApiQuotaLabel("");
	                setApiNotes("");
	                setApiSaveState("saved");
	              }}
              className={cn(
                "rounded-lg border px-3 py-2 text-xs transition-colors",
                apiProvider.trim() && apiName.trim() && apiSecret.trim()
                  ? "bg-zinc-100 text-zinc-950 border-zinc-100"
                  : "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed",
              )}
	            >
	              Save API
	            </button>
	          </div>
	          <div className="grid gap-2 md:grid-cols-2">
	            <input
	              value={apiBaseUrl}
	              onChange={(event) => {
	                setApiBaseUrl(event.target.value);
	                setApiSaveState("idle");
	              }}
	              placeholder="base_url (optional)"
	              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
	            />
	            <input
	              value={apiDefaultModel}
	              onChange={(event) => {
	                setApiDefaultModel(event.target.value);
	                setApiSaveState("idle");
	              }}
	              placeholder="default model for this API"
	              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
	            />
	            <input
	              value={apiAllowedModels}
	              onChange={(event) => {
	                setApiAllowedModels(event.target.value);
	                setApiSaveState("idle");
	              }}
	              placeholder="allowed models, comma separated"
	              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
	            />
	            <input
	              value={apiQuotaLabel}
	              onChange={(event) => {
	                setApiQuotaLabel(event.target.value);
	                setApiSaveState("idle");
	              }}
	              placeholder="quota label"
	              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
	            />
	            <textarea
	              value={apiNotes}
	              onChange={(event) => {
	                setApiNotes(event.target.value);
	                setApiSaveState("idle");
	              }}
	              placeholder="notes for routing"
	              className="min-h-20 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none md:col-span-2"
	            />
	          </div>
          {apiSaveState === "saved" && <p className="text-[11px] text-emerald-400">Saved</p>}
        </div>
      );
      break;
    }
    case "external_tokens": {
      const providers = externalTokenProviderRows(value);
      const providerOptions = providers.length
        ? providers.map((provider) => String(provider.provider_id ?? ""))
        : ["line", "discord", "generic", "slack"];
      const uniqueProviderOptions = [...new Set(providerOptions.filter(Boolean))];
      const registeredTokens = registeredExternalTokenRows(providers);
      const requiredTokens = requiredExternalTokenRows(providers);
      const tokenHintByProvider: Record<string, string> = {
        line: "LINE: Messaging API Channel Secret / Access Tokenを貼ります。返信は受信元 conversation へ返り、push時だけExplicit Target IDを使います。",
        discord: "Discord Bot + Channel: Bot Tokenを貼り、Channel IDはExplicit Target ID欄へ。Webhook mode: Webhook URLを貼ります。",
        slack: "Slack: Signing Secret / Bot Tokenを貼り、Channel IDやThread TSはTarget欄へ。",
        generic: "Generic: shared secretやcallback URLを貼ります。",
      };
      control = (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
            <div className="grid grid-cols-[36px_minmax(220px,1.4fr)_minmax(130px,0.8fr)_minmax(120px,0.8fr)_48px] items-center gap-3 border-b border-zinc-800 bg-zinc-900/70 px-3 py-2 text-[11px] font-medium text-zinc-500">
              <span className="h-4 w-4 rounded border border-cyan-500/70" />
              <span>Token</span>
              <span>Kind</span>
              <span>Endpoints</span>
              <span />
            </div>
            <div className="divide-y divide-zinc-800/80">
              {registeredTokens.length > 0 ? registeredTokens.map((token) => {
                const key = String(token.key ?? `${token.provider_id}:${token.token_id}`);
                const isRenaming = renamingKey === key;
                const isMenuOpen = openTokenMenuKey === key;
                const isSelected = selectedTokenKey === key;
                const endpointIds = Array.isArray(token.endpoint_ids) ? token.endpoint_ids.map(String).join(", ") : "";
                return (
                  <div
                    key={key}
                    className={cn(
                      "grid grid-cols-[36px_minmax(220px,1.4fr)_minmax(130px,0.8fr)_minmax(120px,0.8fr)_48px] items-center gap-3 px-3 py-3 transition-colors",
                      isSelected ? "bg-zinc-900/85" : "bg-zinc-950/20 hover:bg-zinc-900/45",
                    )}
                    onClick={() => setSelectedTokenKey(key)}
                  >
                    <span className={cn("h-4 w-4 rounded border", isSelected ? "border-cyan-400 bg-cyan-500/20" : "border-cyan-500/70")} />
                    <div className="min-w-0">
                      {isRenaming ? (
                        <div className="flex items-center gap-1.5">
                          <input
                            value={renameDraft}
                            autoFocus
                            onChange={(event) => setRenameDraft(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key !== "Enter") return;
                              event.preventDefault();
                              if (!renameDraft.trim()) return;
                              onChange(sectionId, field.id, {
                                action: "rename",
                                provider_id: token.provider_id,
                                token_id: token.token_id,
                                name: renameDraft.trim(),
                              });
                              setRenamingKey("");
                            }}
                            className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 outline-none"
                          />
                          <button
                            type="button"
                            disabled={!renameDraft.trim()}
                            onClick={(event) => {
                              event.stopPropagation();
                              if (!renameDraft.trim()) return;
                              onChange(sectionId, field.id, {
                                action: "rename",
                                provider_id: token.provider_id,
                                token_id: token.token_id,
                                name: renameDraft.trim(),
                              });
                              setRenamingKey("");
                            }}
                            className="rounded-md border border-zinc-700 p-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                            title="Rename"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setRenamingKey("");
                            }}
                            className="rounded-md border border-zinc-800 p-1 text-zinc-500 hover:text-zinc-300"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="truncate text-sm font-medium text-zinc-200">{String(token.name ?? token.token_id ?? "")}</div>
                          <MaskedExternalTokenLabel token={token} />
                        </>
                      )}
                    </div>
                    <span className="truncate text-sm text-zinc-500">{String(token.kind ?? "token")}</span>
                    <span className="truncate text-sm text-zinc-500">{endpointIds || "None"}</span>
                    <div className="relative flex justify-end">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setOpenTokenMenuKey(isMenuOpen ? "" : key);
                        }}
                        className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 text-zinc-500 transition-colors hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-200"
                        title="Actions"
                      >
                        <MoreVertical size={15} />
                      </button>
                      {isMenuOpen && (
                        <>
                          <button
                            type="button"
                            aria-label="close token menu"
                            className="fixed inset-0 z-10 cursor-default"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOpenTokenMenuKey("");
                            }}
                          />
                          <div className="absolute right-0 top-[calc(100%+6px)] z-20 w-32 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 py-1 shadow-2xl">
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setRenamingKey(key);
                                setRenameDraft(String(token.name ?? token.token_id ?? ""));
                                setOpenTokenMenuKey("");
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800"
                            >
                              <Pencil size={13} />
                              Rename
                            </button>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setOpenTokenMenuKey("");
                                onChange(sectionId, field.id, {
                                  action: "delete",
                                  provider_id: token.provider_id,
                                  token_id: token.token_id,
                                });
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-rose-300 hover:bg-rose-950/30"
                            >
                              <Trash2 size={13} />
                              Delete
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                );
              }) : (
                <div className="px-3 py-5 text-xs text-zinc-600">No registered external tokens yet.</div>
              )}
            </div>
          </div>
          {requiredTokens.length > 0 && (
            <div className="flex flex-wrap gap-2 text-[11px]">
              {requiredTokens.map((token) => (
                <span
                  key={`${String(token.provider_id)}:${String(token.kind)}`}
                  className={cn(
                    "rounded-md border px-2 py-1",
                    token.configured ? "border-emerald-800 bg-emerald-950/25 text-emerald-300" : "border-zinc-800 bg-zinc-950 text-zinc-500",
                  )}
                >
                  {String(token.provider_id)} / {String(token.kind)}: {token.configured ? "configured" : "missing"}
                </span>
              ))}
            </div>
          )}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="mb-3 text-xs leading-5 text-zinc-400">{tokenHintByProvider[tokenProvider] ?? "値は保存後に再表示しません。"}</div>
            <div className="grid gap-3 md:grid-cols-[150px_1fr_1fr_1.4fr_auto]">
              <label className="space-y-1.5">
                <span className="text-[11px] font-medium uppercase text-zinc-500">Provider</span>
                <CustomSelect
                  value={tokenProvider}
                  onChange={(nextProvider) => {
                    setTokenProvider(nextProvider);
                    setTokenKind(externalTokenKindOptions(nextProvider)[0]?.value ?? "token");
                    setTokenSaveState("idle");
                  }}
                  options={uniqueProviderOptions.map((providerId) => ({ value: providerId, label: providerId }))}
                />
              </label>
              <label className="space-y-1.5">
                <span className="text-[11px] font-medium uppercase text-zinc-500">Token ID</span>
                <input
                  value={tokenName}
                  onChange={(event) => {
                    setTokenName(event.target.value);
                    setTokenSaveState("idle");
                  }}
                  placeholder="main"
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-cyan-500"
                />
              </label>
              <label className="space-y-1.5">
                <span className="text-[11px] font-medium uppercase text-zinc-500">Paste Kind</span>
                <CustomSelect
                  value={tokenKind}
                  onChange={(nextKind) => {
                    setTokenKind(nextKind);
                    setTokenSaveState("idle");
                  }}
                  options={externalTokenKindOptions(tokenProvider)}
                />
              </label>
              <label className="space-y-1.5">
                <span className="text-[11px] font-medium uppercase text-zinc-500">Secret / URL Value</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={tokenSecret}
                  onChange={(event) => {
                    setTokenSecret(event.target.value);
                    setTokenSaveState("idle");
                  }}
                  placeholder={tokenKind === "webhook_url" ? "https://discord.com/api/webhooks/..." : `${tokenProvider} ${tokenKind}`}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-cyan-500"
                />
              </label>
              <div className="flex items-end">
                <button
                  type="button"
                  disabled={!tokenProvider.trim() || !tokenName.trim() || !tokenSecret.trim()}
                  onClick={() => {
                    if (!tokenProvider.trim() || !tokenName.trim() || !tokenSecret.trim()) return;
                    onChange(sectionId, field.id, {
                      action: "upsert",
                      provider_id: tokenProvider,
                      token_id: tokenName,
                      name: tokenName,
                      kind: tokenKind,
                      value: tokenSecret,
                    });
                    setTokenSecret("");
                    setTokenSaveState("saved");
                  }}
                  className={cn(
                    "w-full rounded-lg border px-3 py-2 text-sm transition-colors",
                    tokenProvider.trim() && tokenName.trim() && tokenSecret.trim()
                      ? "border-zinc-100 bg-zinc-100 text-zinc-950"
                      : "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600",
                  )}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
          {tokenSaveState === "saved" && <p className="text-[11px] text-emerald-400">Saved</p>}
        </div>
      );
      break;
    }
    case "public_url":
      control = (
        <PublicUrlField
          sectionId={sectionId}
          field={field}
          value={value}
          onChange={onChange}
        />
      );
      break;
    case "secret":
      control = (
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <input
            type="password"
            autoComplete="off"
            value={secretDraft}
            placeholder={isSecretConfigured ? "Saved" : "Not set"}
            onChange={(event) => {
              setSecretDraft(event.target.value);
              setSecretState("idle");
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || !secretDraft.trim()) return;
              event.preventDefault();
              onChange(sectionId, field.id, secretDraft);
              setSecretDraft("");
              setSecretState("saved");
            }}
            className="min-w-[220px] flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
          />
          <button
            type="button"
            disabled={!secretDraft.trim()}
            onClick={() => {
              if (!secretDraft.trim()) return;
              onChange(sectionId, field.id, secretDraft);
              setSecretDraft("");
              setSecretState("saved");
            }}
            className={cn(
              "px-3 py-2 rounded-lg text-xs border transition-colors",
              secretDraft.trim()
                ? "bg-zinc-100 text-zinc-950 border-zinc-100"
                : "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed",
            )}
          >
            Save
          </button>
          <span className="w-14 text-[11px] text-zinc-500">
            {secretState === "saved" || isSecretConfigured ? "Saved" : ""}
          </span>
        </div>
      );
      break;
    case "toggle":
      control = (
        <button
          type="button"
          onClick={() => onChange(sectionId, field.id, !Boolean(value))}
          className={cn("w-10 h-6 rounded-full relative transition-colors", Boolean(value) ? "bg-emerald-500" : "bg-zinc-700")}
        >
          <span className={cn("absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform", Boolean(value) && "translate-x-4")} />
        </button>
      );
      break;
    case "select":
      control = field.id === "preferred_model" ? (
        <SettingsModelSearchSelect
          value={String(value ?? field.default ?? "")}
          onChange={(nextValue) => onChange(sectionId, field.id, nextValue)}
          options={(field.options ?? []).map(modelFieldOptionToOption)}
          placeholder="model/provider/特徴メモで検索"
        />
      ) : (
        <CustomSelect
          value={String(value ?? field.default ?? "")}
          onChange={(nextValue) => onChange(sectionId, field.id, nextValue)}
          options={(field.options ?? []).map((option) => ({ value: String(option.value), label: option.label }))}
        />
      );
      break;
    case "number":
      control = (
        <input
          type="number"
          value={Number(value ?? field.default ?? 0)}
          min={field.min}
          max={field.max}
          onChange={(event) => onChange(sectionId, field.id, Number(event.target.value))}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none w-28"
        />
      );
      break;
    case "readonly":
      control = (
        <div className="group/readonly flex items-start justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
          <div className="whitespace-pre-wrap text-sm leading-6 text-zinc-300 select-text">{formatReadonlyValue(value, field.default)}</div>
          <button
            type="button"
            onClick={() => void copyTextToClipboard(formatReadonlyValue(value, field.default))}
            className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-zinc-800 text-zinc-500 opacity-70 transition-colors hover:border-zinc-600 hover:text-zinc-200 group-hover/readonly:opacity-100"
            title="Copy"
          >
            <Copy size={13} />
          </button>
        </div>
      );
      break;
    case "textarea":
      control = (
        <textarea
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="w-full h-20 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none resize-none"
        />
      );
      break;
    default:
      control = (
        <input
          type="text"
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none min-w-[240px]"
        />
      );
  }

  return (
    <div className="space-y-1.5 min-w-0">
      <div className="flex flex-col gap-2">
        {commonLabel}
        {control}
      </div>
      {field.help && <p className="text-[11px] text-zinc-500">{field.help}</p>}
    </div>
  );
}

export function SettingsModalRenderer({
  isOpen,
  activeSectionId: requestedSectionId,
  catalog,
  health,
  previewsCount,
  settingsSections,
  settingsValues,
  locale = "ja",
  onClose,
  onSettingChange,
}: SettingsModalRendererProps) {
  const [activeSectionId, setActiveSectionId] = useState(settingsSections[0]?.id ?? "system");
  const [settingsSearch, setSettingsSearch] = useState("");
  const normalizedSearch = settingsSearch.trim().toLowerCase();
  const visibleSections = normalizedSearch
    ? settingsSections.filter((section) => settingsSectionSearchText(section).includes(normalizedSearch))
    : settingsSections;
  useEffect(() => {
    if (!requestedSectionId) return;
    if (settingsSections.some((section) => section.id === requestedSectionId)) {
      setActiveSectionId(requestedSectionId);
    }
  }, [requestedSectionId, settingsSections]);
  useEffect(() => {
    if (!normalizedSearch) return;
    if (!visibleSections.some((section) => section.id === activeSectionId)) {
      setActiveSectionId(visibleSections[0]?.id ?? settingsSections[0]?.id ?? "system");
    }
  }, [activeSectionId, normalizedSearch, settingsSections, visibleSections]);
  const activeSection = visibleSections.find((section) => section.id === activeSectionId)
    ?? visibleSections[0]
    ?? settingsSections[0];
  const primaryFields = activeSection?.fields.filter((field) => !field.advanced) ?? [];
  const advancedFields = activeSection?.fields.filter((field) => field.advanced) ?? [];
  const activeSectionOwnText = [
    activeSection?.id ?? "",
    activeSection?.label ?? "",
    activeSection?.description ?? "",
  ].join(" ").toLowerCase();
  const fieldFilter = (field: SettingsSection["fields"][number]) => (
    !normalizedSearch
    || activeSectionOwnText.includes(normalizedSearch)
    || settingsFieldSearchText(field).includes(normalizedSearch)
  );
  const visiblePrimaryFields = primaryFields.filter(fieldFilter);
  const visibleAdvancedFields = advancedFields.filter(fieldFilter);

  const renderField = (field: SettingsSection["fields"][number]) => (
    <div
      key={`${activeSection?.id}.${field.id}`}
      className={cn(
        "rounded-lg border border-zinc-800 bg-zinc-950/50 p-4",
        field.type === "textarea" || field.type === "secret" || field.type === "api_keys" || field.type === "external_tokens" || field.type === "public_url" || field.type === "model_api_routes" || field.id.endsWith("_setup_guide") ? "lg:col-span-2" : "",
      )}
    >
      <SettingsField
        sectionId={activeSection?.id ?? ""}
        field={field}
        value={
          field.type === "secret" && field.configured_field
            ? settingsValues[activeSection?.id ?? ""]?.[field.configured_field]
            : settingsValues[activeSection?.id ?? ""]?.[field.id] ?? field.default
        }
        sectionValues={settingsValues[activeSection?.id ?? ""] ?? {}}
        onChange={onSettingChange}
      />
    </div>
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative h-[min(760px,calc(100vh-48px))] w-[min(1040px,calc(100vw-32px))] bg-[#09090b] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col"
          >
            <div className="px-6 py-4 border-b border-zinc-800 flex justify-between items-center">
              <div className="min-w-0">
                <h2 className="text-lg font-medium text-zinc-100">{t(locale, "settings.title")}</h2>
                <p className="text-xs text-zinc-500 mt-1">
                  {t(locale, "settings.backendRegistry", {
                    extensionPoints: catalog?.extension_points.length ?? 0,
                    parts: catalog?.parts?.length ?? 0,
                    pack: health?.pack ?? "defaultspack",
                  })}
                </p>
              </div>
              <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
                <X size={18} />
              </button>
            </div>
            <div className="grid flex-1 min-h-0 md:grid-cols-[220px_1fr]">
              <nav className="border-b border-zinc-800 bg-zinc-950/50 p-3 md:border-b-0 md:border-r overflow-x-auto md:overflow-y-auto">
                <label className="mb-3 flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-black/30 px-3 text-xs text-zinc-500 focus-within:border-zinc-600 focus-within:text-zinc-300">
                  <Search size={14} />
                  <input
                    value={settingsSearch}
                    onChange={(event) => setSettingsSearch(event.target.value)}
                    placeholder={t(locale, "settings.searchPlaceholder")}
                    className="min-w-0 flex-1 bg-transparent text-zinc-200 outline-none placeholder:text-zinc-600"
                  />
                  {settingsSearch && (
                    <button
                      type="button"
                      onClick={() => setSettingsSearch("")}
                      className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300"
                      aria-label={t(locale, "settings.clearSearch")}
                    >
                      <X size={13} />
                    </button>
                  )}
                </label>
                <div className="flex gap-2 md:flex-col">
                  {visibleSections.map((section) => {
                    const primaryFieldCount = section.fields.filter((field) => !field.advanced).length;
                    return (
                      <button
                        key={section.id}
                        type="button"
                        onClick={() => setActiveSectionId(section.id)}
                        className={cn(
                          "flex-shrink-0 rounded-lg px-3 py-2 text-left text-xs transition-colors border",
                          activeSection?.id === section.id
                            ? "border-zinc-600 bg-zinc-800 text-zinc-100"
                            : "border-transparent text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300",
                        )}
                      >
                        <span className="block font-medium">{section.label}</span>
                        <span className="mt-0.5 block text-[10px] text-zinc-600">{t(locale, "settings.controls", { count: primaryFieldCount })}</span>
                      </button>
                    );
                  })}
                  {visibleSections.length === 0 && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-4 text-xs text-zinc-500">
                      {t(locale, "settings.noSections")}
                    </div>
                  )}
                </div>
              </nav>

              <div className="flex-1 overflow-y-auto p-6 space-y-8">
                {activeSection && (
                  <section className="space-y-4">
                    <div>
                      <h3 className="text-sm font-medium text-zinc-100">{activeSection.label}</h3>
                      {activeSection.description && <p className="text-xs text-zinc-500 mt-1">{activeSection.description}</p>}
                    </div>
                    <div className="grid gap-4 lg:grid-cols-2">
                      {visiblePrimaryFields.map(renderField)}
                    </div>
                    {normalizedSearch && visiblePrimaryFields.length === 0 && visibleAdvancedFields.length === 0 && (
                      <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 text-sm text-zinc-500">
                        {t(locale, "settings.noFields")}
                      </div>
                    )}
                    {visibleAdvancedFields.length > 0 && (
                      <details className="rounded-lg border border-zinc-800 bg-zinc-950/40">
                        <summary className="cursor-pointer list-none px-4 py-3 text-xs font-medium text-zinc-400 transition-colors hover:text-zinc-200">
                          {t(locale, "settings.advanced")}
                        </summary>
                        <div className="grid gap-4 border-t border-zinc-800 p-4 lg:grid-cols-2">
                          {visibleAdvancedFields.map(renderField)}
                        </div>
                      </details>
                    )}
                  </section>
                )}

              <details className="rounded-lg border border-zinc-800 bg-zinc-950/30">
                <summary className="cursor-pointer list-none px-4 py-3 text-xs font-medium text-zinc-500 transition-colors hover:text-zinc-300">
                  {t(locale, "settings.developerDiagnostics")}
                </summary>
                <div className="space-y-6 border-t border-zinc-800 p-4">
                  <section className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-100">Extension Points</h3>
                    <div className="grid gap-3 md:grid-cols-3">
                      {(catalog?.extension_points ?? []).map((point) => (
                        <div key={point.id} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 space-y-2">
                          <div className="text-sm text-zinc-200">{point.id}</div>
                          <div className="text-[11px] text-zinc-500 font-mono break-all">{point.path}</div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-100">Parts</h3>
                    <div className="grid gap-3 md:grid-cols-2">
                      {(catalog?.parts ?? []).map((part) => (
                        <div key={part.id} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 space-y-2">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm text-zinc-200">{part.label ?? part.id}</div>
                            <div className="text-[10px] text-zinc-500 font-mono">{part.kind}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-100">System Status</h3>
                    <textarea
                      className="w-full h-28 bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-300 resize-none focus:border-zinc-600 outline-none font-mono"
                      value={JSON.stringify(
                        {
                          health,
                          previewCount: previewsCount,
                          chatRenderers: catalog?.chat_rendering.renderers ?? [],
                          componentBindings: catalog?.component_bindings ?? [],
                          diagnostics: catalog?.diagnostics ?? [],
                        },
                        null,
                        2,
                      )}
                      readOnly
                    />
                  </section>
                </div>
              </details>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
