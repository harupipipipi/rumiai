import type { SettingsSection, UICatalog } from "./api";

export type SettingsValues = Record<string, Record<string, unknown>>;

export type SettingsPayload = {
  sections?: SettingsSection[] | null;
  values?: SettingsValues | null;
} | null | undefined;

export type ResolvedSettingsState = {
  sections: SettingsSection[];
  values: SettingsValues;
  sectionsSource: "settings" | "catalog" | "empty";
  valuesSource: "settings" | "catalog" | "empty";
};

function settingsValues(value: unknown): SettingsValues {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as SettingsValues;
}

function hasValues(value: SettingsValues): boolean {
  return Object.keys(value).length > 0;
}

export function resolveSettingsState(
  settings: SettingsPayload,
  catalog: UICatalog | null | undefined,
): ResolvedSettingsState {
  const settingsSections = Array.isArray(settings?.sections) ? settings.sections : [];
  const catalogSections = Array.isArray(catalog?.settings?.sections) ? catalog.settings.sections : [];
  const sections = settingsSections.length > 0 ? settingsSections : catalogSections;

  const directValues = settingsValues(settings?.values);
  const catalogValues = settingsValues(catalog?.settings?.values);
  const values = hasValues(directValues) ? directValues : catalogValues;

  return {
    sections,
    values,
    sectionsSource: settingsSections.length > 0 ? "settings" : catalogSections.length > 0 ? "catalog" : "empty",
    valuesSource: hasValues(directValues) ? "settings" : hasValues(catalogValues) ? "catalog" : "empty",
  };
}
