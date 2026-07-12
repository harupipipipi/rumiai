import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { clean } from "./clean.mjs";

test("clean removes dist directory and tolerates missing dist", async () => {
  const root = await mkdtemp(join(tmpdir(), "rumi-panel-clean-"));
  const distDir = join(root, "dist");
  await mkdir(distDir, { recursive: true });
  await writeFile(join(distDir, "asset.txt"), "asset", "utf8");

  await clean({ distDir });
  await assert.rejects(access(distDir));

  await clean({ distDir });
});
