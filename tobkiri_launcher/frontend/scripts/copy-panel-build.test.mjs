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
  await writeFile(join(distDir, "index.html"), "<main>ok</main>\r\n", "utf8");
  await writeFile(join(distDir, "app.js"), "console.log('ok');\r\n", "utf8");
  await writeFile(join(distDir, "manifest.json"), "{\r\n  \"z\": 2,\r\n  \"a\": 1,\r\n  \"file\": \"assets\\\\app.js\"\r\n}\r\n", "utf8");
  await mkdir(join(distDir, "nested"), { recursive: true });
  const binary = Buffer.from([0, 255, 1, 254]);
  await writeFile(join(distDir, "nested", "icon.bin"), binary);
  await mkdir(panelDir, { recursive: true });
  await writeFile(join(panelDir, "old.txt"), "old", "utf8");

  await copyPanelBuild({ distDir, panelDir });

  assert.equal(await readFile(join(panelDir, "index.html"), "utf8"), "<main>ok</main>\n");
  assert.equal(await readFile(join(panelDir, "app.js"), "utf8"), "console.log('ok');\n");
  assert.equal(await readFile(join(panelDir, "manifest.json"), "utf8"), '{\n  "a": 1,\n  "file": "assets/app.js",\n  "z": 2\n}\n');
  assert.equal(await readFile(join(distDir, "manifest.json"), "utf8"), '{\n  "a": 1,\n  "file": "assets/app.js",\n  "z": 2\n}\n');
  assert.deepEqual(await readFile(join(panelDir, "nested", "icon.bin")), binary);
  await assert.rejects(readFile(join(panelDir, "old.txt"), "utf8"));
});
