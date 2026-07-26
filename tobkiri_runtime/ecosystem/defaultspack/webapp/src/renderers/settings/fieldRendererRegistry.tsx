import { type ComponentType, type ReactElement } from "react";

import type { SettingChangeHandler } from "../types";
import {
  FrontendComponentHost,
  type FrontendComponentRegistry,
} from "../components/frontendComponentRegistry";
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

function legacyFallbackProps(props: SettingsFieldRendererProps): SettingsFieldRendererProps {
  if (props.field.type === "model_select") {
    const preferredValue = props.sectionValues?.preferred_model ?? props.value;
    return {
      ...props,
      value: preferredValue,
      field: {
        ...props.field,
        id: "preferred_model",
        type: "select",
        label: props.field.label || "Preferred Model",
      },
    };
  }
  if (props.field.type === "provider_select") {
    return {
      ...props,
      field: {
        ...props.field,
        type: "select",
      },
    };
  }
  if (props.field.type === "api_key_setup") {
    const apiKeysValue = props.sectionValues?.api_keys ?? props.value;
    return {
      ...props,
      value: apiKeysValue,
      field: {
        ...props.field,
        id: "api_keys",
        type: "api_keys",
        label: props.field.label || "API Keys / Tokens",
      },
    };
  }
  return props;
}

export function SettingsFieldRendererHost({
  registry,
  frontendComponentRegistry,
  componentBindings,
  fallbackRenderer: FallbackRenderer,
  ...props
}: SettingsFieldRendererProps & {
  registry: SettingsFieldRendererRegistry;
  frontendComponentRegistry?: FrontendComponentRegistry;
  componentBindings?: TemplateComponentBinding[];
  fallbackRenderer: SettingsFieldRenderer;
}): ReactElement {
  const match = registry.resolve(props.field, componentBindings);
  if (!match) {
    const binding = resolveGenericComponentBinding(props.field, componentBindings ?? []);
    if (frontendComponentRegistry && binding) {
      return (
        <FrontendComponentHost
          registry={frontendComponentRegistry}
          request={{
            componentId: binding.component_id ?? binding.component,
            apiVersion: binding.api_version,
            slot: binding.slot ?? "settings_field",
            props: binding.props,
            data: binding.data,
            actions: binding.actions,
            dataSourceIds: binding.data_source_ids,
            fallbackComponentId: binding.fallback_component_id,
            templateId: binding.template_id,
            templateSourcePackId: binding.source_pack_id,
            templateTrust: binding.trust_level,
          }}
        />
      );
    }
    return <FallbackRenderer {...legacyFallbackProps(props)} />;
  }

  const Renderer = match.entry.render;
  return <Renderer {...props} />;
}

function resolveGenericComponentBinding(
  field: TemplateSettingsField,
  componentBindings: TemplateComponentBinding[],
): TemplateComponentBinding | null {
  const lookupKeys = settingsFieldRendererLookupKeys(field, componentBindings);
  return (
    componentBindings.find(
      (binding) =>
        lookupKeys.includes(binding.part_id) ||
        lookupKeys.includes(binding.component_id ?? binding.component),
    ) ?? null
  );
}
