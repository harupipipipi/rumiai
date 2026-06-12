import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));
const offenders = [];
const importPattern = /import\s+(?!type\b)([\s\S]*?)\s+from\s+["']([^"']+)["']/g;

function isTypeOnlyBinding(binding) {
  const trimmed = binding.trim();
  if (trimmed.startsWith("type ")) return true;
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false;
  return trimmed
    .slice(1, -1)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .every((item) => item.startsWith("type "));
}

function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      walk(full);
      continue;
    }
    if (!/\.(tsx?|jsx?)$/.test(name)) continue;
    const rel = path.relative(root, full).replaceAll("\\", "/");
    if (!rel.startsWith("renderers/") && !rel.startsWith("components/")) continue;
    if (rel.includes("/__fixtures__/")) continue;
    const text = fs.readFileSync(full, "utf8");
    for (const match of text.matchAll(importPattern)) {
      if (isTypeOnlyBinding(match[1])) continue;
      const specifier = match[2];
      const resolved = path
        .normalize(path.join(path.dirname(rel), specifier))
        .replaceAll("\\", "/")
        .replace(/\.(tsx?|jsx?)$/, "");
      if (resolved === "lib/api" || resolved.endsWith("/lib/api")) {
        offenders.push(rel);
        break;
      }
    }
  }
}

walk(root);

if (offenders.length) {
  console.error("Renderers/components must not import runtime API clients directly:");
  console.error(offenders.join("\n"));
  console.error("Move API access into features/**/resources/** and pass data/actions through props.");
  process.exit(1);
}
