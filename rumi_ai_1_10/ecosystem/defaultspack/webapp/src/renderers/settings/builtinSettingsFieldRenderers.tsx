import type { SettingsFieldRendererEntry } from "./fieldRendererRegistry";
import { BuiltinApiKeySetupRenderer } from "./renderers/apiKeySetupField";
import { BuiltinModelSelectRenderer } from "./renderers/modelSelectField";
import { BuiltinProviderSelectRenderer } from "./renderers/providerSelectField";

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
