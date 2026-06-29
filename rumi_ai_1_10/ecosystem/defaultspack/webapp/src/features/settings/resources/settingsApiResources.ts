import { api } from "../../../lib/api";
import type { ModelSearchResponse } from "../../../lib/api";
import { createProviderApiKeyResources, type ProviderKeySaveResult } from "../../apiKeys";
import { createModelSearchResources } from "../../models";

const modelSearchResources = createModelSearchResources(api);
const providerApiKeyResources = createProviderApiKeyResources<Parameters<typeof api.saveProviderApiKey>[2]>(api);

export const settingsApiResources = {
  searchModels(payload: { query: string; max_results: number }) {
    return modelSearchResources.searchModels(payload) as Promise<ModelSearchResponse>;
  },

  saveProviderApiKey(providerId: string, value: string, options?: Parameters<typeof api.saveProviderApiKey>[2]) {
    return providerApiKeyResources.saveProviderApiKey(providerId, value, options) as Promise<ProviderKeySaveResult>;
  },

  startProviderOAuth(providerId: string, options?: { scopeMode?: string; services?: string[] }) {
    return api.startProviderOAuth(providerId, options);
  },

  disconnectProviderOAuth(providerId: string) {
    return api.disconnectProviderOAuth(providerId);
  },

  clearProviderOAuthClientConfig(providerId: string) {
    return api.clearProviderOAuthClientConfig(providerId);
  },

  saveProviderOAuthClientConfig(providerId: string, clientConfig: string) {
    return api.saveProviderOAuthClientConfig(providerId, clientConfig);
  },

  createPublicUrl(payload: Parameters<typeof api.createPublicUrl>[0]) {
    return api.createPublicUrl(payload);
  },

  closePublicUrl(urlId: string) {
    return api.closePublicUrl(urlId);
  },
};
