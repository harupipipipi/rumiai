import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEBAPP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const indexCss = readFileSync(path.join(WEBAPP_ROOT, "src/index.css"), "utf8");

test("defaultspack CSS does not import remote runtime fonts", () => {
  assert.doesNotMatch(indexCss, /fonts\.(?:googleapis|gstatic)\.com/i);
  assert.doesNotMatch(indexCss, /@import\s+url\(\s*["']?https?:/i);
});

test("chat structured content owns horizontal scrolling", () => {
  assert.match(indexCss, /\.rumi-message-content\s*\{[^}]*overflow-x:\s*auto;/s);
  assert.match(indexCss, /\.rumi-log-card-body\s*\{[^}]*overflow-x:\s*auto;[^}]*white-space:\s*pre;/s);
  assert.match(indexCss, /\.markdown-body pre\s*\{[^}]*overflow-x:\s*auto;[^}]*white-space:\s*pre;/s);
  assert.match(indexCss, /\.markdown-body pre code\s*\{[^}]*width:\s*max-content;[^}]*white-space:\s*pre;/s);
  assert.match(indexCss, /\.markdown-body table\s*\{[^}]*overflow-x:\s*auto;/s);
});
