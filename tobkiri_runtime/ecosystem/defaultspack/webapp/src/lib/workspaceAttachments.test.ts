import test from "node:test";
import assert from "node:assert/strict";

import { hasWorkspaceAttachment, workspaceFileToAttachment, WORKSPACE_ATTACHMENT_TEXT_LIMIT } from "./workspaceAttachments";

test("workspaceFileToAttachment creates capped text workspace attachments", () => {
  const content = "a".repeat(WORKSPACE_ATTACHMENT_TEXT_LIMIT + 1);
  const attachment = workspaceFileToAttachment("README.md", content, 123);

  assert.equal(attachment.name, "README.md");
  assert.equal(attachment.source, "workspace");
  assert.equal(attachment.sourcePath, "README.md");
  assert.equal(attachment.size, 123);
  assert.equal(attachment.type, "text/plain");
  assert.equal(attachment.content?.length, WORKSPACE_ATTACHMENT_TEXT_LIMIT);
  assert.equal(attachment.truncated, true);
});

test("workspace attachments use the same secret review boundary", () => {
  const secret = ["xox", "b-123456789012-abcdefghijklmnopqrstuv"].join("");
  const attachment = workspaceFileToAttachment(
    "config/secrets.txt",
    `SLACK_TOKEN=${secret}`,
  );

  assert.equal(attachment.source, "workspace");
  assert.equal(attachment.securityReview?.status, "required");
  assert.equal(JSON.stringify(attachment.securityReview).includes(secret), false);
});

test("hasWorkspaceAttachment detects existing workspace paths", () => {
  const attachment = workspaceFileToAttachment("docs/notes.md", "hello");

  assert.equal(hasWorkspaceAttachment([attachment], "docs/notes.md"), true);
  assert.equal(hasWorkspaceAttachment([{ ...attachment, sourcePath: undefined }], "docs/notes.md"), true);
  assert.equal(hasWorkspaceAttachment([attachment], "README.md"), false);
});
