import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  checkGeneratedFrontendContractMap,
  generateFrontendContractMap,
} from "./generate-frontend-contract-map.mjs";

test("the checked-in generated map is deterministic and current", async () => {
  const result = await checkGeneratedFrontendContractMap();
  assert.equal(result.rawDigest, "sha256:3b0e6c0360fad519cabc25eb7fb5f442a0d37cb9f1590e94f7cdff8f69a420e3");
  assert.equal(result.runtimeMap.routes.length, 21);
});

test("a stale or tampered canonical artifact fails closed before generation", async () => {
  const root = await mkdtemp(join(tmpdir(), "tobkiri-contract-map-"));
  const sourcePath = join(root, "frontend_contract_map.v4.json");
  const outputPath = join(root, "generatedFrontendContractMap.ts");
  try {
    const source = JSON.parse(await readFile(
      "../../tobkiri_runtime/ecosystem/defaultspack/defaultspack/frontend_contract_map.v4.json",
      "utf8",
    ));
    source.routes = source.routes.filter((route) => route.path !== "/api/runtime-surface/profile");
    await writeFile(sourcePath, JSON.stringify(source), "utf8");
    await assert.rejects(
      generateFrontendContractMap({mapPath: sourcePath, outputPath}),
      /canonical map digest|missing or non-exact route|generation failed/i,
    );
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});
