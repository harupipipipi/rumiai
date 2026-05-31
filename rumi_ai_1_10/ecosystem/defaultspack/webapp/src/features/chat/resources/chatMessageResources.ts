import { api, type BrowserScreenshot } from "../../../lib/api";

export const chatMessageResources = {
  writeClipboard(content: string) {
    return api.writeClipboard(content);
  },

  getBrowserScreenshots(conversationId: string, runId: string) {
    return api.getBrowserScreenshots(conversationId, runId);
  },
};

export type { BrowserScreenshot };
