import { useEffect, useState, type ReactElement } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown, Copy, Loader2, MoreVertical, Pencil, Trash2, X } from "lucide-react";

import { cn } from "../lib/cn";
import { api } from "../lib/api";
import type { SettingsSection } from "../lib/api";
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
  onChange,
}: {
  sectionId: string;
  field: SettingsSection["fields"][number];
  value: unknown;
  onChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const [secretDraft, setSecretDraft] = useState("");
  const [secretState, setSecretState] = useState<"idle" | "saved">("idle");
  const [apiProvider, setApiProvider] = useState("google");
  const [apiName, setApiName] = useState("main");
  const [apiSecret, setApiSecret] = useState("");
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
  const commonLabel = <span className="text-sm text-zinc-300">{field.label}</span>;
  const isSecretConfigured = Boolean(value);

  let control: ReactElement;
  switch (field.type) {
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
                    <span className="truncate text-sm text-zinc-500">No guardrails</span>
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
                });
                setApiSecret("");
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
      control = (
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
  onClose,
  onSettingChange,
}: SettingsModalRendererProps) {
  const [activeSectionId, setActiveSectionId] = useState(settingsSections[0]?.id ?? "system");
  useEffect(() => {
    if (!requestedSectionId) return;
    if (settingsSections.some((section) => section.id === requestedSectionId)) {
      setActiveSectionId(requestedSectionId);
    }
  }, [requestedSectionId, settingsSections]);
  const activeSection = settingsSections.find((section) => section.id === activeSectionId) ?? settingsSections[0];
  const primaryFields = activeSection?.fields.filter((field) => !field.advanced) ?? [];
  const advancedFields = activeSection?.fields.filter((field) => field.advanced) ?? [];

  const renderField = (field: SettingsSection["fields"][number]) => (
    <div
      key={`${activeSection?.id}.${field.id}`}
      className={cn(
        "rounded-lg border border-zinc-800 bg-zinc-950/50 p-4",
        field.type === "textarea" || field.type === "secret" || field.type === "api_keys" || field.type === "external_tokens" || field.type === "public_url" || field.id.endsWith("_setup_guide") ? "lg:col-span-2" : "",
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
              <div>
                <h2 className="text-lg font-medium text-zinc-100">Settings</h2>
                <p className="text-xs text-zinc-500 mt-1">
                  backend registry: {catalog?.extension_points.length ?? 0} extension points, {catalog?.parts?.length ?? 0} parts, {health?.pack ?? "defaultspack"}
                </p>
              </div>
              <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
                <X size={18} />
              </button>
            </div>
            <div className="grid flex-1 min-h-0 md:grid-cols-[220px_1fr]">
              <nav className="border-b border-zinc-800 bg-zinc-950/50 p-3 md:border-b-0 md:border-r overflow-x-auto md:overflow-y-auto">
                <div className="flex gap-2 md:flex-col">
                  {settingsSections.map((section) => {
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
                        <span className="mt-0.5 block text-[10px] text-zinc-600">{primaryFieldCount} controls</span>
                      </button>
                    );
                  })}
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
                      {primaryFields.map(renderField)}
                    </div>
                    {advancedFields.length > 0 && (
                      <details className="rounded-lg border border-zinc-800 bg-zinc-950/40">
                        <summary className="cursor-pointer list-none px-4 py-3 text-xs font-medium text-zinc-400 transition-colors hover:text-zinc-200">
                          Advanced settings
                        </summary>
                        <div className="grid gap-4 border-t border-zinc-800 p-4 lg:grid-cols-2">
                          {advancedFields.map(renderField)}
                        </div>
                      </details>
                    )}
                  </section>
                )}

              <details className="rounded-lg border border-zinc-800 bg-zinc-950/30">
                <summary className="cursor-pointer list-none px-4 py-3 text-xs font-medium text-zinc-500 transition-colors hover:text-zinc-300">
                  Developer diagnostics
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
