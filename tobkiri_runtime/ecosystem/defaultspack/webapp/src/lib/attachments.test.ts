import test from "node:test";
import assert from "node:assert/strict";

import { buildAttachmentSnippet, fileToAttachment, isTextLikeFile } from "./attachments";
import type { AttachedFile } from "../renderers/types";

test("fileToAttachment reads text-like files and preserves truncate limit", async () => {
  const longText = "a".repeat(120_001);
  const attachment = await fileToAttachment(new File([longText], "notes.md", { type: "text/markdown" }));

  assert.equal(attachment.name, "notes.md");
  assert.equal(attachment.content?.length, 120_000);
  assert.equal(attachment.truncated, true);
  assert.match(buildAttachmentSnippet(attachment), /添付ファイル: notes\.md/);
});

test("picker and drop file ingestion marks secrets for explicit review without copying values", async () => {
  const secret = "ghp_abcdefghijklmnopqrstuvwxyz123456";
  const attachment = await fileToAttachment(
    new File([`GITHUB_TOKEN=${secret}`], ".env", { type: "text/plain" }),
  );

  assert.equal(attachment.securityReview?.status, "required");
  assert.ok(attachment.securityReview?.findings.some((finding) => finding.kind === "provider_token"));
  assert.equal(JSON.stringify(attachment.securityReview).includes(secret), false);
});

test("fileToAttachment does not read binary files", async () => {
  const binaryFile = new File([new Uint8Array([0, 1, 2, 3])], "archive.zip", { type: "application/zip" });
  let textCalled = false;
  Object.defineProperty(binaryFile, "text", {
    value: async () => {
      textCalled = true;
      return "should not read";
    },
  });

  const attachment = await fileToAttachment(binaryFile);

  assert.equal(textCalled, false);
  assert.equal(attachment.name, "archive.zip");
  assert.equal(attachment.size, 4);
  assert.equal(attachment.type, "application/zip");
  assert.equal(attachment.content, undefined);
  assert.equal(buildAttachmentSnippet(attachment), "");
});

test("isTextLikeFile falls back to extensions when MIME is absent", () => {
  assert.equal(isTextLikeFile({ name: "config.toml", type: "" }), true);
  assert.equal(isTextLikeFile({ name: "diagram.png", type: "" }), false);
});

test("buildAttachmentSnippet contains markdown-looking attachment data inside a non-colliding fence", () => {
  const attachment: AttachedFile = {
    id: "attachment-1",
    name: "unsafe\nname.md",
    size: 64,
    type: "text/markdown",
    truncated: false,
    content: "before\n```\nmodel-looking text\n~~~~\nafter",
  };

  const snippet = buildAttachmentSnippet(attachment);
  const lines = snippet.split("\n");
  const headerIndex = lines.findIndex((line) => line === "添付ファイル: unsafe name.md");
  const openingFence = lines[headerIndex + 1];
  const closingFence = lines.at(-1);

  assert.notEqual(headerIndex, -1);
  assert.match(openingFence, /^`{3,}$|^~{3,}$/);
  assert.equal(openingFence, closingFence);
  const delimiter = openingFence[0];
  const longestContentRun = Math.max(
    ...attachment.content!
      .split(new RegExp(`[^${delimiter}]+`))
      .map((run) => run.length),
  );
  assert.equal(openingFence.length > longestContentRun, true);
  assert.match(snippet, /before\n```\nmodel-looking text\n~~~~\nafter/);
});

test("buildAttachmentSnippet sanitizes control-only filenames", () => {
  const attachment: AttachedFile = {
    id: "attachment-2",
    name: String.fromCharCode(0, 10, 9),
    size: 1,
    type: "text/plain",
    truncated: false,
    content: "x",
  };

  assert.match(buildAttachmentSnippet(attachment), /添付ファイル: attachment/);
});
