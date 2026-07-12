import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(SCRIPT_DIR, "..");
const DEFAULT_DIST_DIR = resolve(FRONTEND_ROOT, "dist");
const DEFAULT_PANEL_DIR = resolve(
  FRONTEND_ROOT,
  "../../tobkiri_runtime/core_runtime/core_pack/core_control_panel/web",
);

export async function copyPanelBuild({
  distDir = DEFAULT_DIST_DIR,
  panelDir = DEFAULT_PANEL_DIR,
} = {}) {
  await rm(panelDir, { recursive: true, force: true });
  await mkdir(panelDir, { recursive: true });
  await cp(distDir, panelDir, { recursive: true });
  const indexPath = resolve(panelDir, "index.html");
  const indexHtml = await readFile(indexPath, "utf8");
  await writeFile(indexPath, indexHtml.replace(/\r\n?/g, "\n"), "utf8");
  return { distDir, panelDir };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  copyPanelBuild().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
