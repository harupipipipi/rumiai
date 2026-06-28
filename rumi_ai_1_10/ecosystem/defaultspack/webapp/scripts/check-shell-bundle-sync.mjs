import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const uiDir = path.resolve(here, "../../ui");
const shellPath = path.join(uiDir, "shell.html");
const expectedAssets = new Set([
  "shell-app.css",
  "shell-app.js",
  "shell-icons.js",
  "shell-markdown.js",
  "shell-motion.js",
  "shell-rolldown-runtime.js",
  "shell-vendor.js",
]);

const shell = fs.readFileSync(shellPath, "utf8");
for (const asset of ["shell-app.css", "shell-app.js"]) {
  if (!shell.includes(`/static/${asset}`)) {
    throw new Error(`shell.html does not reference /static/${asset}`);
  }
}

const actualShellAssets = fs
  .readdirSync(uiDir)
  .filter((name) => /^shell-.*\.(?:js|css)$/.test(name))
  .sort();
const expected = [...expectedAssets].sort();
if (JSON.stringify(actualShellAssets) !== JSON.stringify(expected)) {
  throw new Error(
    `shell bundle assets are out of sync. expected=${expected.join(",")} actual=${actualShellAssets.join(",")}`,
  );
}
