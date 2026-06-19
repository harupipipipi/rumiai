import type { ReactElement } from "react";

import type { SettingsSection } from "../../../lib/api";
import type { ApiProviderKind, ApiProviderOption, ApiProviderRow } from "../../../features/apiKeys/apiKeySetup";
import type { SettingsFieldRendererProps } from "../fieldRendererRegistry";

export type SettingsOption = NonNullable<SettingsSection["fields"][number]["options"]>[number];

export function fieldOptions(field: SettingsFieldRendererProps["field"]): SettingsOption[] {
  return Array.isArray(field.options) ? field.options : [];
}

function providerRows(value: unknown): ApiProviderRow[] {
  return Array.isArray(value)
    ? value.filter((item): item is ApiProviderRow => Boolean(item) && typeof item === "object")
    : [];
}

export function fieldProviderRows(field: SettingsFieldRendererProps["field"], sectionValues?: Record<string, unknown>): ApiProviderRow[] {
  const fromField = providerRows(field.api_keys);
  if (fromField.length) return fromField;
  return providerRows(sectionValues?.api_keys);
}

export function fieldOptionProviderRows(field: SettingsFieldRendererProps["field"]): ApiProviderRow[] {
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

export function registeredApiRows(providers: ApiProviderRow[]): ApiProviderRow[] {
  return providers.flatMap((provider) => {
    const apis = Array.isArray(provider.apis) ? provider.apis : [];
    return apis
      .filter((item): item is ApiProviderRow => Boolean(item) && typeof item === "object")
      .map((api) => ({ ...api, provider_id: api.provider_id ?? provider.provider_id }))
      .filter((api) => Boolean((api as Record<string, unknown>).configured));
  });
}

export function modelSelectTargetFieldId(field: SettingsFieldRendererProps["field"]): string {
  const target = String((field as Record<string, unknown>).target_field_id ?? "").trim();
  if (target) return target;
  return field.id === "model_select" ? "preferred_model" : field.id;
}

export function apiKeySetupTargetFieldId(field: SettingsFieldRendererProps["field"]): string {
  return field.id;
}

export function selectedProviderKind(providerId: string, options: ApiProviderOption[]): ApiProviderKind {
  return options.find((option) => option.provider_id === providerId)?.kind ?? "llm";
}

export function SettingsFieldShell({
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
