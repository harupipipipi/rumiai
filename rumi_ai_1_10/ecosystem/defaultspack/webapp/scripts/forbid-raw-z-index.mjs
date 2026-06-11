import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));
const offenders = [];

function isAllowed(rel) {
  return rel.startsWith("ui/layers/");
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
    if (isAllowed(rel)) continue;
    const text = fs.readFileSync(full, "utf8");
    if (/\bz-\[?\d|zIndex\s*:/.test(text)) {
      offenders.push(rel);
    }
  }
}

walk(root);

if (offenders.length) {
  console.error("Raw z-index is forbidden outside src/ui/layers:");
  console.error(offenders.join("\n"));
  process.exit(1);
}
