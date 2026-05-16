import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { copyPanelBuild } from "./copy-panel-build.mjs";

test("copyPanelBuild replaces panel output with dist contents", async () => {
  const root = await mkdtemp(join(tmpdir(), "rumi-panel-copy-"));
  const distDir = join(root, "dist");
  const panelDir = join(root, "panel");

  await writeFile(join(root, "placeholder"), "root", "utf8");
  await mkdir(distDir, { recursive: true });
  await writeFile(join(distDir, "index.html"), "<main>ok</main>", "utf8");
  await mkdir(panelDir, { recursive: true });
  await writeFile(join(panelDir, "old.txt"), "old", "utf8");

  await copyPanelBuild({ distDir, panelDir });

  assert.equal(await readFile(join(panelDir, "index.html"), "utf8"), "<main>ok</main>");
  await assert.rejects(readFile(join(panelDir, "old.txt"), "utf8"));
});
