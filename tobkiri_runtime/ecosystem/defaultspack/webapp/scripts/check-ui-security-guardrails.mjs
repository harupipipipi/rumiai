import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webappRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const attachmentSource = readFileSync(path.join(webappRoot, "src/lib/attachments.ts"), "utf8");
const failures = [];

if (attachmentSource.includes("\\`\\`\\`\\n${file.content}")) {
  failures.push("attachment snippets must not use a fixed Markdown fence around untrusted content");
}
if (!/function markdownFenceFor\(content: string\)/.test(attachmentSource)) {
  failures.push("attachment snippets must choose a non-colliding Markdown fence");
}
if (!/function safeAttachmentName\(name: string\)/.test(attachmentSource)) {
  failures.push("attachment snippet filenames must be normalized before interpolation");
}

if (failures.length > 0) {
  console.error("UI security guardrail check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("UI attachment security guardrails verified.");
