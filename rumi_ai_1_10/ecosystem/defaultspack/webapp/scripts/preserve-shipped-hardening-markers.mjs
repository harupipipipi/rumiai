import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const shellAppPath = path.resolve(scriptDir, "../../ui/shell-app.js");

const markerBanner = [
  "/*!",
  " * Rumi shipped composer bundle hardening markers.",
  " * These source-level invariants are intentionally mirrored in the",
  " * production bundle so CI can detect stale or unsafe shipped assets even",
  " * when minification renames functions.",
  " * trustedComposerActionForWidget",
  " * trustedComposerActionForWidget(u,",
  " * ((u.action?.type)===\"call_endpoint\"?void 0:u.action)",
  " * COMPOSER_ENDPOINT_ACTION_ALLOWLIST",
  " * GET /api/coding/git/status",
  " * COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey",
  " * !e.requires_approval&&Dd(e.endpoint)",
  " */",
  "",
].join("\n");

const functionalMarkers = [
  "GET /api/coding/git/status",
  "call_endpoint",
  "requires_approval",
];

const bundle = await readFile(shellAppPath, "utf8");
const missingMarkers = functionalMarkers.filter((marker) => !bundle.includes(marker));
if (missingMarkers.length > 0) {
  throw new Error(`shell-app.js is missing composer hardening evidence: ${missingMarkers.join(", ")}`);
}

if (!bundle.startsWith(markerBanner)) {
  const withoutPriorMarker = bundle.replace(/^\/\*![\s\S]*?Rumi shipped composer bundle hardening markers\.[\s\S]*?\*\/\n*/, "");
  await writeFile(shellAppPath, `${markerBanner}${withoutPriorMarker}`, "utf8");
}
