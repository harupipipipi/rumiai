import { type ComponentType, type ReactElement } from "react";

import type { SettingChangeHandler } from "../types";
import {
  settingsFieldRendererLookupKeys,
  type TemplateComponentBinding,
  type TemplateSettingsField,
  type TemplateSettingsFieldType,
} from "../template/settingsFieldMetadata";

export type SettingsFieldRendererProps = {
  sectionId: string;
  field: TemplateSettingsField;
  value: unknown;
  sectionValues?: Record<string, unknown>;
  onChange: SettingChangeHandler;
};

export type SettingsFieldRenderer = ComponentType<SettingsFieldRendererProps>;

export type SettingsFieldRendererEntry = {
  id: string;
  types?: TemplateSettingsFieldType[];
  renderers?: string[];
  component?: string;
  render: SettingsFieldRenderer;
};

export type SettingsFieldRendererMatch = {
  entry: SettingsFieldRendererEntry;
  key: string;
};

export type SettingsFieldRendererRegistry = {
  register: (entry: SettingsFieldRendererEntry) => SettingsFieldRendererRegistry;
  resolve: (field: TemplateSettingsField, componentBindings?: TemplateComponentBinding[]) => SettingsFieldRendererMatch | null;
  entries: () => SettingsFieldRendererEntry[];
};

function entryKeys(entry: SettingsFieldRendererEntry): string[] {
  return [
    entry.id,
    entry.component,
    ...(entry.renderers ?? []),
    ...(entry.types ?? []).map(String),
  ].filter((item): item is string => Boolean(item));
}

export function createSettingsFieldRendererRegistry(
  initialEntries: SettingsFieldRendererEntry[] = [],
): SettingsFieldRendererRegistry {
  const entries = [...initialEntries];
  const registry: SettingsFieldRendererRegistry = {
    register(entry) {
      entries.push(entry);
      return registry;
    },
    resolve(field, componentBindings = []) {
      const lookupKeys = settingsFieldRendererLookupKeys(field, componentBindings);
      for (const key of lookupKeys) {
        const match = entries.find((entry) => entryKeys(entry).includes(key));
        if (match) return { entry: match, key };
      }
      return null;
    },
    entries() {
      return [...entries];
    },
  };
  return registry;
}

export function SettingsFieldRendererHost({
  registry,
  componentBindings,
  fallbackRenderer: FallbackRenderer,
  ...props
}: SettingsFieldRendererProps & {
  registry: SettingsFieldRendererRegistry;
  componentBindings?: TemplateComponentBinding[];
  fallbackRenderer: SettingsFieldRenderer;
}): ReactElement {
  const match = registry.resolve(props.field, componentBindings);
  if (!match) return <FallbackRenderer {...props} />;

  const Renderer = match.entry.render;
  return <Renderer {...props} />;
}
