import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEBAPP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const approvalPath = path.join(WEBAPP_ROOT, "src/lib/authorityApprovalBrowserToken.ts");
const attachmentPath = path.join(WEBAPP_ROOT, "src/lib/attachments.ts");

const approvalSource = readFileSync(approvalPath, "utf8");
const attachmentSource = readFileSync(attachmentPath, "utf8");
const failures = [];

const forbiddenApprovalPatterns = [
  {
    pattern: /readStorageValue\(\s*["']localStorage["']\s*\)/,
    message: "browser approval tokens must not be read from persistent localStorage",
  },
  {
    pattern: /writeStorageValue\(\s*["']localStorage["']/,
    message: "browser approval tokens must not be written to persistent localStorage",
  },
  {
    pattern: /return\s+url\.toString\(\)/,
    message: "tokenized destinations must not return an arbitrary absolute URL",
  },
  {
    pattern: /browser_approval_token=\$\{encodeURIComponent\(token\)\}/,
    message: "parse failures must not append approval tokens to unvalidated strings",
  },
];

for (const check of forbiddenApprovalPatterns) {
  if (check.pattern.test(approvalSource)) failures.push(check.message);
}

const requiredApprovalPatterns = [
  {
    pattern: /const url = sameOriginUrl\(pathOrUrl\);\s*if \(!url\) return pathOrUrl;/,
    message: "browserApprovalTokenizedPath must fail closed before adding a token",
  },
  {
    pattern: /removeStorageValue\("localStorage"\)/,
    message: "legacy localStorage approval-token values must be actively removed",
  },
];

for (const check of requiredApprovalPatterns) {
  if (!check.pattern.test(approvalSource)) failures.push(check.message);
}

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

console.log("UI security guardrails verified.");
