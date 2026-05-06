import { useState, type ReactElement } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

import { cn } from "../lib/cn";
import type { SettingsSection } from "../lib/api";
import type { SettingsModalRendererProps } from "./types";

function formatReadonlyValue(value: unknown, fallback: unknown): string {
  const resolved = value ?? fallback ?? "";
  if (typeof resolved === "boolean") return resolved ? "Saved" : "Not set";
  return String(resolved);
}

function apiProviderRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function namedApiRows(provider: Record<string, unknown>): Array<Record<string, unknown>> {
  const apis = provider.apis;
  return Array.isArray(apis) ? apis.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
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
  const commonLabel = <span className="text-sm text-zinc-300">{field.label}</span>;
  const isSecretConfigured = Boolean(value);

  let control: ReactElement;
  switch (field.type) {
    case "api_keys": {
      const providers = apiProviderRows(value);
      const providerOptions = providers.length
        ? providers.map((provider) => String(provider.provider_id ?? ""))
        : ["google", "openrouter", "openai", "anthropic"];
      control = (
        <div className="space-y-4">
          <div className="grid gap-2 md:grid-cols-[160px_1fr_1.4fr_auto]">
            <select
              value={apiProvider}
              onChange={(event) => setApiProvider(event.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
            >
              {[...new Set(providerOptions.filter(Boolean))].map((providerId) => (
                <option key={providerId} value={providerId}>
                  {providerId}
                </option>
              ))}
            </select>
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
          <div className="grid gap-2 md:grid-cols-2">
            {providers.map((provider) => {
              const rows = namedApiRows(provider);
              const configured = Boolean(provider.configured);
              return (
                <div key={String(provider.provider_id)} className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-zinc-200">{String(provider.provider_id)}</span>
                    <span className={cn("text-[11px]", configured ? "text-emerald-400" : "text-zinc-600")}>
                      {configured ? "configured" : "not set"}
                    </span>
                  </div>
                  <div className="mt-2 space-y-1">
                    {rows.length > 0 ? rows.map((api) => (
                      <div key={String(api.key)} className="flex items-center justify-between gap-2 text-xs text-zinc-500">
                        <span>{String(api.name ?? api.api_id)}</span>
                        <span className="font-mono">{String(api.key ?? "")}</span>
                      </div>
                    )) : (
                      <p className="text-xs text-zinc-600">No named APIs yet.</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      );
      break;
    }
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
        <select
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(sectionId, field.id, event.target.value)}
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none"
        >
          {(field.options ?? []).map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
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
      control = <div className="text-sm text-zinc-300">{formatReadonlyValue(value, field.default)}</div>;
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
  catalog,
  health,
  previewsCount,
  settingsSections,
  settingsValues,
  onClose,
  onSettingChange,
}: SettingsModalRendererProps) {
  const [activeSectionId, setActiveSectionId] = useState(settingsSections[0]?.id ?? "system");
  const activeSection = settingsSections.find((section) => section.id === activeSectionId) ?? settingsSections[0];
  const primaryFields = activeSection?.fields.filter((field) => !field.advanced) ?? [];
  const advancedFields = activeSection?.fields.filter((field) => field.advanced) ?? [];

  const renderField = (field: SettingsSection["fields"][number]) => (
    <div
      key={`${activeSection?.id}.${field.id}`}
      className={cn(
        "rounded-lg border border-zinc-800 bg-zinc-950/50 p-4",
        field.type === "textarea" || field.type === "secret" || field.type === "api_keys" ? "lg:col-span-2" : "",
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
            className="relative w-full max-w-5xl bg-[#09090b] border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[84vh]"
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
