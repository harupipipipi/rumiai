import { api } from "../../../lib/api";
import type { ModelSearchResponse } from "../../../lib/api";
import type { ModelAvailabilityAfterKeySave } from "./useModelAvailability";

export type ProviderKeySaveResult = {
  provider_id: string;
  api_id?: string;
  name?: string;
  configured: boolean;
  kind?: string;
  model_availability?: ModelAvailabilityAfterKeySave;
};

export const settingsApiResources = {
  searchModels(payload: { query: string; max_results: number }) {
    return api.searchModels(payload) as Promise<ModelSearchResponse>;
  },

  saveProviderApiKey(providerId: string, value: string, options?: Parameters<typeof api.saveProviderApiKey>[2]) {
    return api.saveProviderApiKey(providerId, value, options) as Promise<ProviderKeySaveResult>;
  },

  startProviderOAuth(providerId: string) {
    return api.startProviderOAuth(providerId);
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
