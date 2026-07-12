import { rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(SCRIPT_DIR, "..");
const DEFAULT_DIST_DIR = resolve(FRONTEND_ROOT, "dist");

export async function clean({ distDir = DEFAULT_DIST_DIR } = {}) {
  await rm(distDir, { recursive: true, force: true });
  return { distDir };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  clean().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
