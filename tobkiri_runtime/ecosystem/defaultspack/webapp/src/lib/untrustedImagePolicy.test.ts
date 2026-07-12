import assert from "node:assert/strict";
import test from "node:test";

import { classifyUntrustedImageUrl, extractImageBlockUrl } from "./untrustedImagePolicy";

test("remote HTTPS images require consent and expose a normalized source", () => {
  assert.deepEqual(classifyUntrustedImageUrl(" HTTPS://Example.COM:443/a/../pixel.png?q=1 "), {
    disposition: "remote-consent",
    normalizedUrl: "https://example.com/pixel.png?q=1",
    sourceLabel: "example.com",
  });
});

test("unsafe schemes, SVG data, credentials, and private destinations are blocked", () => {
  for (const fixture of [
    "file:///etc/passwd", "javascript:alert(1)",
    "data:image/svg+xml,<svg onload=alert(1)>",
    "https://user:secret@example.com/image.png", "http://localhost/pixel",
    "http://127.0.0.1/pixel", "http://10.1.2.3/pixel",
    "http://169.254.169.254/latest/meta-data", "http://[::1]/pixel",
    "http://printer.local/pixel",
  ]) assert.equal(classifyUntrustedImageUrl(fixture).disposition, "blocked", fixture);
});

test("same-origin attachment needs identity and authoritative trust marker", () => {
  const options = { appOrigin: "https://app.rumi.test", attachmentId: "attachment_123" };
  const url = "https://app.rumi.test/api/attachments/attachment_123/image";
  assert.equal(classifyUntrustedImageUrl(url, options).disposition, "remote-consent");
  assert.equal(classifyUntrustedImageUrl(url, { ...options, trustedAttachment: true }).disposition, "trusted-attachment");
});

test("block helper extracts only string URL values", () => {
  assert.equal(extractImageBlockUrl({ image_url: { url: "https://example.com/a.png" } }), "https://example.com/a.png");
});
