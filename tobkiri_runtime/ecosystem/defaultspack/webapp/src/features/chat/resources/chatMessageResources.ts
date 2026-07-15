import { api, defaultspackApiFetch, type BrowserScreenshot } from "../../../lib/api";

export const chatMessageResources = {
  writeClipboard(content: string) {
    return api.writeClipboard(content);
  },

  getBrowserScreenshots(conversationId: string, runId: string) {
    return api.getBrowserScreenshots(conversationId, runId);
  },

  async loadRemoteImage(url: string): Promise<{ blobUrl: string; proxyUrl: string }> {
    const consentResponse = await defaultspackApiFetch("/api/remote-images/consents", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    if (!consentResponse.ok) throw new Error(`Remote image consent failed (${consentResponse.status})`);
    const envelope = await consentResponse.json() as { data?: { proxy_url?: unknown } };
    const proxyUrl = String(envelope.data?.proxy_url ?? "");
    if (!proxyUrl.startsWith("/api/remote-images/")) throw new Error("Remote image proxy returned an invalid URL");
    const imageResponse = await defaultspackApiFetch(proxyUrl, { headers: { Accept: "image/*" } });
    if (!imageResponse.ok) throw new Error(`Remote image load failed (${imageResponse.status})`);
    const blob = await imageResponse.blob();
    return { blobUrl: URL.createObjectURL(blob), proxyUrl };
  },

  async revokeRemoteImage(proxyUrl: string): Promise<void> {
    if (!proxyUrl.startsWith("/api/remote-images/")) return;
    await defaultspackApiFetch(proxyUrl, { method: "DELETE" });
  },
};

export type { BrowserScreenshot };
