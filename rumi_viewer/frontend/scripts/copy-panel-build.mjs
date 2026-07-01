import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(SCRIPT_DIR, "..");
const DEFAULT_DIST_DIR = resolve(FRONTEND_ROOT, "dist");
const DEFAULT_PANEL_DIR = resolve(
  FRONTEND_ROOT,
  "../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web",
);
const TEXT_EXTENSIONS = new Set([".css", ".html", ".js", ".json", ".map", ".svg", ".txt"]);

async function normalizeTextFiles(root) {
  const entries = await readdir(root, { withFileTypes: true });
  await Promise.all(entries.map(async (entry) => {
    const fullPath = join(root, entry.name);
    if (entry.isDirectory()) {
      await normalizeTextFiles(fullPath);
      return;
    }
    if (!entry.isFile() || !TEXT_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
      return;
    }
    const original = await readFile(fullPath, "utf8");
    const normalized = original.replace(/\r\n?/g, "\n");
    if (normalized !== original) {
      await writeFile(fullPath, normalized, "utf8");
    }
  }));
}

export async function copyPanelBuild({
  distDir = DEFAULT_DIST_DIR,
  panelDir = DEFAULT_PANEL_DIR,
} = {}) {
  await rm(panelDir, { recursive: true, force: true });
  await mkdir(panelDir, { recursive: true });
  await cp(distDir, panelDir, { recursive: true });
  await normalizeTextFiles(panelDir);
  return { distDir, panelDir };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  copyPanelBuild().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
