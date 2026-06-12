import { api, type ModelSearchResponse } from "../../../lib/api";

export const chatComposerResources = {
  searchModels(payload: { query: string; max_results: number }) {
    return api.searchModels(payload) as Promise<ModelSearchResponse>;
  },
};
