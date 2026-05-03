import test from "node:test";
import assert from "node:assert/strict";

import { buildAttachmentSnippet, fileToAttachment, isTextLikeFile } from "./attachments";

test("fileToAttachment reads text-like files and preserves truncate limit", async () => {
  const longText = "a".repeat(120_001);
  const attachment = await fileToAttachment(new File([longText], "notes.md", { type: "text/markdown" }));

  assert.equal(attachment.name, "notes.md");
  assert.equal(attachment.content?.length, 120_000);
  assert.equal(attachment.truncated, true);
  assert.match(buildAttachmentSnippet(attachment), /添付ファイル: notes\.md/);
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
