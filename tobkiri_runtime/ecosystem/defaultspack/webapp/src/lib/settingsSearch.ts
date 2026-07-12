import type { SettingsSection } from "./api";

export function settingsFieldSearchText(field: SettingsSection["fields"][number]): string {
  return [
    field.id,
    field.label,
    field.help ?? "",
    field.type,
    ...(Array.isArray(field.options) ? field.options.map((option) => `${option.value} ${option.label}`) : []),
  ].join(" ").toLowerCase();
}

export function settingsSectionSearchText(section: SettingsSection): string {
  return [
    section.id,
    section.label,
    section.description ?? "",
    ...section.fields.map(settingsFieldSearchText),
  ].join(" ").toLowerCase();
}
