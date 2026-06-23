import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { buildMobilePairingBaseUrls, normalizeMobileBaseUrl } from "./mobilePairingUrls";

describe("mobilePairingUrls", () => {
  it("filters loopback origins from pairing QR base URLs", () => {
    const urls = buildMobilePairingBaseUrls([
      "http://localhost:8765",
      "http://127.0.0.1:8765",
      "http://192.168.1.44:8765",
    ]);

    assert.deepEqual(urls, ["http://192.168.1.44:8765"]);
  });

  it("normalizes valid LAN origins and rejects non-http values", () => {
    assert.equal(normalizeMobileBaseUrl("192.168.1.44:8765/api/mobile/v1"), "http://192.168.1.44:8765");
    assert.equal(normalizeMobileBaseUrl("file:///tmp/rumi"), "");
  });
});
