import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEBAPP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RUMI_AI_ROOT = path.resolve(WEBAPP_ROOT, "..", "..", "..");
const CANONICAL_REGISTRY = path.join(RUMI_AI_ROOT, "core_runtime", "host_permissions", "default_registry.json");
const FRONTEND_REGISTRY = path.join(WEBAPP_ROOT, "src", "hostPermissions", "hostPermissionRegistry.json");
const CHECK_ONLY = process.argv.includes("--check");

function readJson(pathname) {
  return JSON.parse(readFileSync(pathname, "utf8"));
}

function normalizedRegistryText(pathname) {
  return `${JSON.stringify(readJson(pathname), null, 2)}\n`;
}

if (!existsSync(CANONICAL_REGISTRY)) {
  console.error(`Missing canonical host permission registry: ${CANONICAL_REGISTRY}`);
  process.exit(1);
}

const canonicalText = normalizedRegistryText(CANONICAL_REGISTRY);
const frontendText = existsSync(FRONTEND_REGISTRY) ? normalizedRegistryText(FRONTEND_REGISTRY) : "";

if (frontendText === canonicalText) {
  console.log("Frontend host permission registry is synchronized with core_runtime.");
  process.exit(0);
}

if (CHECK_ONLY) {
  console.error("Frontend host permission registry is out of sync with core_runtime/host_permissions/default_registry.json.");
  console.error("Run `npm run sync:host-permissions` from tobkiri_runtime/ecosystem/defaultspack/webapp.");
  process.exit(1);
}

writeFileSync(FRONTEND_REGISTRY, canonicalText);
console.log("Synchronized src/hostPermissions/hostPermissionRegistry.json from core_runtime.");
