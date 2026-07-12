import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEBAPP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PACK_UI_ROOT = path.resolve(WEBAPP_ROOT, "../ui");
const CSS_FILES = [
  path.join(WEBAPP_ROOT, "src/index.css"),
  path.join(PACK_UI_ROOT, "shell-app.css"),
].filter((filePath) => existsSync(filePath));

const REMOTE_FONT_PATTERNS = [
  /fonts\.(?:googleapis|gstatic)\.com/i,
  /@import\s+url\(\s*["']?https?:/i,
];

const failures = [];
for (const filePath of CSS_FILES) {
  const css = readFileSync(filePath, "utf8");
  for (const pattern of REMOTE_FONT_PATTERNS) {
    if (pattern.test(css)) {
      failures.push(path.relative(WEBAPP_ROOT, filePath));
      break;
    }
  }
}

if (failures.length > 0) {
  console.error("Remote runtime font imports are not allowed in defaultspack CSS:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Checked ${CSS_FILES.length} defaultspack CSS file(s) for remote runtime font imports.`);
