import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { scanAttachmentSecurity } from "../lib/attachmentSecurity";
import { AttachmentSecurityReviewDialog } from "./ComposerRenderer";

test("attachment review discloses categories and choices without rendering secret values", () => {
  const secret = "ghp_abcdefghijklmnopqrstuvwxyz123456";
  const file = {
    id: "sensitive-1",
    name: ".env",
    size: secret.length,
    type: "text/plain",
    content: `GITHUB_TOKEN=${secret}`,
    truncated: false,
  };
  const html = renderToStaticMarkup(createElement(AttachmentSecurityReviewDialog, {
    file: { ...file, securityReview: scanAttachmentSecurity(file) },
    destination: "OpenRouter / remote model",
    processing: "remote",
    selectedToolCount: 2,
    onUseLocalModel() {},
    onUpdate() {},
    onRemove() {},
    onClose() {},
  }));

  assert.match(html, /role="dialog"/);
  assert.match(html, /Review sensitive attachment/);
  assert.match(html, /OpenRouter \/ remote model/);
  assert.match(html, /2 selected/);
  assert.match(html, /Remote provider/);
  assert.match(html, /characters 0–/);
  assert.match(html, /high risk file/);
  assert.match(html, /provider token/);
  assert.match(html, /Metadata only/);
  assert.match(html, /Redact selected/);
  assert.match(html, /Use local model/);
  assert.match(html, /Send unchanged/);
  assert.match(html, /values are not displayed/i);
  assert.match(html, /retention policy/i);
  assert.equal(html.includes(secret), false);
});
