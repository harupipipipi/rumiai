import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { Check, ChevronDown, Loader2, Search, X } from "lucide-react";

import { cn } from "../../lib/cn";
import type { ModelSearchItem, SettingsSection } from "../../lib/api";
import {
  buildVisibleModelOptions,
  findSelectedModelOption,
  modelFieldOptionToModelSelectOption,
  modelSearchItemToModelSelectOption,
  modelSelectDisplay,
  type ModelSelectOption,
} from "../../features/models/modelSelect";
import {
  buildApiKeySavePayload,
  collectApiProviderOptions,
  customProviderRegistrationPayload,
  filterApiProviderOptions,
  type ApiProviderKind,
  type ApiProviderOption,
  type ApiProviderRow,
} from "../../features/apiKeys/apiKeySetup";
import { settingsApiResources } from "../../features/settings/resources/settingsApiResources";
import { availabilityCopy, type ModelAvailabilityAfterKeySave } from "../../features/settings/resources/useModelAvailability";
import type { SettingsFieldRendererEntry, SettingsFieldRendererProps } from "./fieldRendererRegistry";

type SettingsOption = NonNullable<SettingsSection["fields"][number]["options"]>[number];

function fieldOptions(field: SettingsFieldRendererProps["field"]): SettingsOption[] {
  return Array.isArray(field.options) ? field.options : [];
}

function providerRows(value: unknown): ApiProviderRow[] {
  return Array.isArray(value)
    ? value.filter((item): item is ApiProviderRow => Boolean(item) && typeof item === "object")
    : [];
}

function fieldProviderRows(field: SettingsFieldRendererProps["field"], sectionValues?: Record<string, unknown>): ApiProviderRow[] {
  const fromField = providerRows(field.api_keys);
  if (fromField.length) return fromField;
  return providerRows(sectionValues?.api_keys);
}

function fieldOptionProviderRows(field: SettingsFieldRendererProps["field"]): ApiProviderRow[] {
  return fieldOptions(field)
    .map((option): ApiProviderRow => {
      const optionRecord = option as Record<string, unknown>;
      return {
        provider_id: option.provider_id ?? option.value,
        label: option.provider_display_name ?? option.label ?? option.value,
        kind: optionRecord.kind,
        builtin: optionRecord.builtin,
      };
    })
    .filter((item) => Boolean(item.provider_id));
}

function registeredApiRows(providers: ApiProviderRow[]): ApiProviderRow[] {
  return providers.flatMap((provider) => {
    const apis = Array.isArray(provider.apis) ? provider.apis : [];
    return apis
      .filter((item): item is ApiProviderRow => Boolean(item) && typeof item === "object")
      .map((api) => ({ ...api, provider_id: api.provider_id ?? provider.provider_id }))
      .filter((api) => Boolean((api as Record<string, unknown>).configured));
  });
}

function modelSelectTargetFieldId(field: SettingsFieldRendererProps["field"]): string {
  return field.id === "preferred_model" ? field.id : "preferred_model";
}

function apiKeySetupTargetFieldId(field: SettingsFieldRendererProps["field"]): string {
  return field.id === "api_keys" ? field.id : "api_keys";
}

function selectedProviderKind(providerId: string, options: ApiProviderOption[]): ApiProviderKind {
  return options.find((option) => option.provider_id === providerId)?.kind ?? "llm";
}

function SettingsFieldShell({
  field,
  children,
}: {
  field: SettingsFieldRendererProps["field"];
  children: ReactElement;
}) {
  return (
    <div className="space-y-1.5 min-w-0">
      <div className="flex flex-col gap-2">
        <span className="text-sm text-zinc-300">{field.label}</span>
        {children}
      </div>
      {field.help && <p className="text-[11px] text-zinc-500">{field.help}</p>}
    </div>
  );
}

function SettingsModelSearchField({
  value,
  options,
  onChange,
  placeholder = "model/provider/特徴メモで検索",
}: {
  value: string;
  options: ModelSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [remoteResults, setRemoteResults] = useState<ModelSearchItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const searchRequestSeq = useRef(0);
  const trimmedQuery = query.trim();
  const remoteOptions = useMemo(() => remoteResults.map(modelSearchItemToModelSelectOption), [remoteResults]);
  const selected = findSelectedModelOption(options, value, remoteOptions);
  const selectedDisplay = selected ? modelSelectDisplay(selected) : null;

  useEffect(() => {
    if (!open) return;
    searchRequestSeq.current += 1;
    const requestSeq = searchRequestSeq.current;
    if (!trimmedQuery) {
      setRemoteResults([]);
      setBusy(false);
      setError("");
      return;
    }
    let disposed = false;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      settingsApiResources.searchModels({ query: trimmedQuery, max_results: 30 })
        .then((result) => {
          if (disposed || requestSeq !== searchRequestSeq.current) return;
          setRemoteResults(result.models ?? []);
        })
        .catch((searchError: unknown) => {
          if (disposed || requestSeq !== searchRequestSeq.current) return;
          setRemoteResults([]);
          setError(searchError instanceof Error ? searchError.message : "モデル検索に失敗しました");
        })
        .finally(() => {
          if (!disposed && requestSeq === searchRequestSeq.current) setBusy(false);
        });
    }, 160);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [open, trimmedQuery]);

  const visibleOptions = useMemo(() => (
    buildVisibleModelOptions({
      options,
      selected,
      remoteOptions,
      query: trimmedQuery,
    })
  ), [options, remoteOptions, selected, trimmedQuery]);

  return (
    <div className="relative" data-settings-renderer="model_select">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700 focus:border-emerald-500/70"
      >
        <span className="min-w-0">
          <span className="block truncate">{selectedDisplay?.label || value || "モデルを選択"}</span>
          {selectedDisplay?.subtitle && (
            <span className="block truncate text-[11px] text-zinc-500">{selectedDisplay.subtitle}</span>
          )}
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="モデル検索を閉じる" className="fixed inset-0 rumi-layer-panel cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] rumi-layer-local-popover overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-2xl">
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
                  aria-label="モデル検索をクリア"
                >
                  <X size={13} />
                </button>
              )}
            </label>
            {error && <div className="border-t border-zinc-800 px-3 py-2 text-[11px] text-rose-300">{error}</div>}
            <div className="max-h-72 overflow-y-auto border-t border-zinc-800 p-1">
              {visibleOptions.length > 0 ? visibleOptions.map((option) => {
                const active = option.value === value || option.qualified_model_id === value;
                const display = modelSelectDisplay(option);
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
                      <span className="block truncate text-sm font-medium text-zinc-100">{display.label}</span>
                      <span className="block truncate text-[11px] text-zinc-500">{display.subtitle}</span>
                    </span>
                    <span className="flex max-w-[160px] flex-wrap justify-end gap-1">
                      {display.badges.map((badge) => (
                        <span key={badge.id} className="rounded-full border border-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400">
                          {badge.label}
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

function SearchableProviderField({
  value,
  options,
  onChange,
  onAddCustom,
  placeholder = "provider を検索",
}: {
  value: string;
  options: ApiProviderOption[];
  onChange: (value: string) => void;
  onAddCustom?: (option: { providerId: string; label: string; kind: ApiProviderKind }) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [draftId, setDraftId] = useState("");
  const [draftKind, setDraftKind] = useState<ApiProviderKind>("custom");
  const selected = options.find((option) => option.provider_id === value) ?? null;
  const filtered = useMemo(() => filterApiProviderOptions(options, query), [options, query]);

  const closeAll = () => {
    setOpen(false);
    setCreating(false);
    setDraftId("");
    setQuery("");
  };

  const submitDraft = () => {
    const payload = customProviderRegistrationPayload({ providerId: draftId, label: draftId, kind: draftKind });
    if (!payload) return;
    onAddCustom?.({ providerId: payload.provider_id, label: payload.label, kind: payload.kind });
    onChange(payload.provider_id);
    closeAll();
  };

  return (
    <div className="relative" data-settings-renderer="provider_select">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex min-h-10 w-full items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate">{selected?.label ?? (value || "provider を選択")}</span>
          {selected && selected.provider_id !== selected.label && (
            <span className="block truncate text-[11px] text-zinc-500">{selected.provider_id}</span>
          )}
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="close provider select" className="fixed inset-0 rumi-layer-panel cursor-default" onClick={closeAll} />
          <div className="absolute left-0 top-[calc(100%+6px)] rumi-layer-local-popover w-[min(520px,calc(100vw-32px))] max-w-[calc(100vw-32px)] overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-2xl">
            <label className="m-2 flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-black/30 px-3 text-xs text-zinc-500 focus-within:border-zinc-600 focus-within:text-zinc-300">
              <Search size={14} />
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={placeholder}
                className="min-w-0 flex-1 bg-transparent text-zinc-200 outline-none placeholder:text-zinc-600"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300"
                  aria-label="clear provider search"
                >
                  <X size={13} />
                </button>
              )}
            </label>
            <div className="max-h-64 overflow-y-auto border-t border-zinc-800 p-1">
              {filtered.length > 0 ? filtered.map((option) => {
                const active = option.provider_id === value;
                return (
                  <button
                    key={option.provider_id}
                    type="button"
                    onClick={() => {
                      onChange(option.provider_id);
                      closeAll();
                    }}
                    className={cn(
                      "flex w-full items-start justify-between gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                      active ? "bg-zinc-800 text-zinc-100" : "text-zinc-300 hover:bg-zinc-900",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block whitespace-normal break-all leading-5">{option.label}</span>
                      {option.provider_id !== option.label && (
                        <span className="block whitespace-normal break-all text-[11px] leading-4 text-zinc-500">{option.provider_id}</span>
                      )}
                      {!option.builtin && (
                        <span className="mt-1 inline-flex rounded-full border border-zinc-700 px-1.5 text-[9px] uppercase text-zinc-400">
                          {option.kind === "custom" ? "non-llm" : "custom"}
                        </span>
                      )}
                    </span>
                    {active && <Check size={13} className="mt-1 shrink-0 text-emerald-300" />}
                  </button>
                );
              }) : (
                <div className="px-3 py-3 text-xs text-zinc-600">一致する provider がありません。</div>
              )}
            </div>
            {onAddCustom && (
              creating ? (
                <div className="space-y-2 border-t border-zinc-800 bg-zinc-950/80 p-3">
                  <input
                    autoFocus
                    value={draftId}
                    onChange={(event) => setDraftId(event.target.value)}
                    placeholder="provider id (例: tavily, searchapi)"
                    className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-200 outline-none"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        submitDraft();
                      }
                    }}
                  />
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-zinc-500">種類:</span>
                    {(["llm", "custom"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setDraftKind(option)}
                        className={cn(
                          "rounded-full border px-2.5 py-1 transition-colors",
                          draftKind === option
                            ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-200"
                            : "border-zinc-700 text-zinc-400 hover:text-zinc-200",
                        )}
                      >
                        {option === "llm" ? "LLM" : "Non-LLM"}
                      </button>
                    ))}
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setCreating(false);
                        setDraftId("");
                      }}
                      className="rounded-md border border-zinc-800 px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={submitDraft}
                      disabled={!draftId.trim()}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-xs",
                        draftId.trim()
                          ? "border-zinc-100 bg-zinc-100 text-zinc-950"
                          : "border-zinc-800 bg-zinc-900 text-zinc-600",
                      )}
                    >
                      Add
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="flex w-full items-center gap-2 border-t border-zinc-800 px-3 py-2 text-left text-xs text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                >
                  <span className="text-base leading-none">+</span>
                  Add custom provider...
                </button>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}

function BuiltinModelSelectRenderer({ sectionId, field, value, sectionValues, onChange }: SettingsFieldRendererProps) {
  const targetFieldId = modelSelectTargetFieldId(field);
  const selectedValue = String(sectionValues?.[targetFieldId] ?? value ?? field.default ?? "");
  return (
    <SettingsFieldShell field={field}>
      <SettingsModelSearchField
        value={selectedValue}
        options={fieldOptions(field).map(modelFieldOptionToModelSelectOption)}
        onChange={(nextValue) => onChange(sectionId, targetFieldId, nextValue)}
      />
    </SettingsFieldShell>
  );
}

function BuiltinProviderSelectRenderer({ sectionId, field, value, sectionValues, onChange }: SettingsFieldRendererProps) {
  const providerOptions = collectApiProviderOptions([
    ...fieldOptionProviderRows(field),
    ...fieldProviderRows(field, sectionValues),
  ]);
  return (
    <SettingsFieldShell field={field}>
      <SearchableProviderField
        value={String(value ?? field.default ?? providerOptions[0]?.provider_id ?? "")}
        options={providerOptions}
        onChange={(nextValue) => onChange(sectionId, field.id, nextValue)}
      />
    </SettingsFieldShell>
  );
}

function BuiltinApiKeySetupRenderer({ sectionId, field, value, sectionValues, onChange }: SettingsFieldRendererProps) {
  const targetFieldId = apiKeySetupTargetFieldId(field);
  const providers = fieldProviderRows(field, sectionValues);
  const providerOptions = collectApiProviderOptions([
    ...fieldOptionProviderRows(field),
    ...providers,
  ]);
  const registeredApis = registeredApiRows(providers);
  const [providerId, setProviderId] = useState(String(field.provider_id ?? providerOptions[0]?.provider_id ?? "google"));
  const [apiName, setApiName] = useState("main");
  const [secret, setSecret] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [allowedModels, setAllowedModels] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [quotaLabel, setQuotaLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [saveError, setSaveError] = useState("");
  const [availability, setAvailability] = useState<ModelAvailabilityAfterKeySave | null>(null);
  const selectedKind = selectedProviderKind(providerId, providerOptions);
  const feedback = saveState === "saved" ? availabilityCopy(availability) : null;

  const resetFeedback = () => {
    setSaveState("idle");
    setSaveError("");
    setAvailability(null);
  };

  const handleSubmit = async () => {
    const payload = buildApiKeySavePayload({
      provider_id: providerId,
      name: apiName,
      value: secret,
      kind: selectedKind,
      base_url: baseUrl,
      allowed_models: allowedModels,
      default_model: defaultModel,
      quota_label: quotaLabel,
      notes,
    });
    if (!payload) return;
    setSaveState("saving");
    setSaveError("");
    setAvailability(null);
    try {
      const result = await settingsApiResources.saveProviderApiKey(payload.provider_id, payload.value, payload.options);
      setAvailability(result.model_availability ?? {
        status: "route_required",
        provider_id: payload.provider_id,
        api_id: payload.options.apiId,
        candidate_models: [],
        reason: "Saved, but the backend did not confirm model availability. Choose a model route before using this key.",
      });
      setSecret("");
      setBaseUrl("");
      setAllowedModels("");
      setDefaultModel("");
      setQuotaLabel("");
      setNotes("");
      setSaveState("saved");
      onChange(sectionId, targetFieldId, { action: "oauth_refresh" });
    } catch (saveErrorValue) {
      setSaveState("idle");
      setSaveError(saveErrorValue instanceof Error ? saveErrorValue.message : "API key save failed.");
    }
  };

  return (
    <SettingsFieldShell field={field}>
      <div className="space-y-3" data-settings-renderer="api_key_setup">
        {registeredApis.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950/70">
            {registeredApis.map((api) => (
              <div key={String(api.key ?? `${api.provider_id}:${api.api_id}`)} className="flex flex-wrap items-center gap-2 border-b border-zinc-800/80 px-3 py-2.5 last:border-b-0">
                <span className="text-sm font-medium text-zinc-200">{String(api.name ?? api.api_id ?? "")}</span>
                <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                  {String(api.provider_id ?? "")}
                </span>
                <span className="font-mono text-xs text-zinc-500">{String(api.provider_id ?? "")}:{String(api.api_id ?? "")}:***</span>
              </div>
            ))}
          </div>
        )}
        <div className="grid gap-2 md:grid-cols-[180px_minmax(120px,1fr)_minmax(180px,2fr)_auto]">
          <SearchableProviderField
            value={providerId}
            options={providerOptions}
            onChange={(nextProviderId) => {
              setProviderId(nextProviderId);
              resetFeedback();
            }}
            onAddCustom={(option) => {
              onChange(sectionId, targetFieldId, {
                action: "register_provider",
                provider_id: option.providerId,
                label: option.label,
                kind: option.kind,
              });
              setProviderId(option.providerId);
              resetFeedback();
            }}
          />
          <input
            value={apiName}
            onChange={(event) => {
              setApiName(event.target.value);
              resetFeedback();
            }}
            placeholder="名前 (例: main, work)"
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none"
          />
          <input
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(event) => {
              setSecret(event.target.value);
              resetFeedback();
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              void handleSubmit();
            }}
            placeholder={`${providerId || "provider"} API key`}
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none"
          />
          <button
            type="button"
            disabled={saveState === "saving" || !providerId.trim() || !apiName.trim() || !secret.trim()}
            onClick={() => void handleSubmit()}
            className={cn(
              "rounded-lg border px-3 py-2 text-xs transition-colors",
              saveState !== "saving" && providerId.trim() && apiName.trim() && secret.trim()
                ? "border-zinc-100 bg-zinc-100 text-zinc-950"
                : "cursor-not-allowed border-zinc-800 bg-zinc-900 text-zinc-600",
            )}
          >
            {saveState === "saving" ? "Saving" : "Save"}
          </button>
        </div>
        <details className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-xs">
          <summary className="cursor-pointer select-none text-zinc-400 hover:text-zinc-200">Advanced (任意): base_url / model 制限 / quota / notes</summary>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <input value={baseUrl} onChange={(event) => { setBaseUrl(event.target.value); resetFeedback(); }} placeholder="base_url (optional)" className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={defaultModel} onChange={(event) => { setDefaultModel(event.target.value); resetFeedback(); }} placeholder="default model for this API" className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={allowedModels} onChange={(event) => { setAllowedModels(event.target.value); resetFeedback(); }} placeholder="allowed models, comma separated" className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <input value={quotaLabel} onChange={(event) => { setQuotaLabel(event.target.value); resetFeedback(); }} placeholder="quota label" className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none" />
            <textarea value={notes} onChange={(event) => { setNotes(event.target.value); resetFeedback(); }} placeholder="notes for routing" className="min-h-20 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 outline-none md:col-span-2" />
          </div>
        </details>
        {feedback?.text && (
          <div className={cn(
            "rounded-lg border px-3 py-2 text-[11px]",
            feedback.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-amber-500/30 bg-amber-500/10 text-amber-100",
          )}
          >
            {feedback.text}
          </div>
        )}
        {saveError && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200">
            {saveError}
          </div>
        )}
      </div>
    </SettingsFieldShell>
  );
}

export const builtinSettingsFieldRendererEntries: SettingsFieldRendererEntry[] = [
  {
    id: "builtin-settings-model-select",
    types: ["model_select"],
    renderers: ["model_select", "SettingsModelSearchSelect"],
    component: "SettingsModelSearchSelect",
    render: BuiltinModelSelectRenderer,
  },
  {
    id: "builtin-settings-provider-select",
    types: ["provider_select"],
    renderers: ["provider_select", "SearchableProviderSelect"],
    component: "SearchableProviderSelect",
    render: BuiltinProviderSelectRenderer,
  },
  {
    id: "builtin-settings-api-key-setup",
    types: ["api_key_setup"],
    renderers: ["api_key_setup", "ApiKeySetupField"],
    component: "ApiKeySetupField",
    render: BuiltinApiKeySetupRenderer,
  },
];
