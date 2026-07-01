import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {PNG} from 'pngjs';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, '..');
const viewerRoot = path.resolve(frontendRoot, '..');
const repoRoot = path.resolve(viewerRoot, '..');
const expectedSplashSvgSha256 = '1a54a160dac4c18a78908248c82af466cce79f83eef8f45b602ec3bad1d56b7d';
const expectedSourceIconSha256 = '358f7aa82385dbe1229bd53cc4ad3481792c6a1b2840ac8f5da31cd50acf6d37';
const expectedGeneratedIconSha256 = '7c3bb943ab46ce4b008aae9e2bd01fdb8615f95913f8f0edf1f02920ac1b080c';

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function textSha256(text) {
  return createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex');
}

function pixelStats(buffer) {
  const png = PNG.sync.read(buffer);
  const buckets = new Set();
  let visible = 0;
  const pixelCount = png.width * png.height;
  const step = Math.max(1, Math.floor(pixelCount / 50_000));

  for (let pixel = 0; pixel < pixelCount; pixel += step) {
    const offset = pixel * 4;
    const alpha = png.data[offset + 3];
    if (alpha < 8) continue;
    visible += 1;
    buckets.add(`${png.data[offset] >> 4}:${png.data[offset + 1] >> 4}:${png.data[offset + 2] >> 4}`);
  }

  return {
    width: png.width,
    height: png.height,
    visibleRatio: pixelCount ? visible / Math.ceil(pixelCount / step) : 0,
    colorBuckets: buckets.size,
  };
}

async function assertPngAsset(relativePath, expectedWidth, expectedHeight) {
  const absolutePath = path.join(repoRoot, relativePath);
  const buffer = await readFile(absolutePath);
  const stats = pixelStats(buffer);
  assert.equal(stats.width, expectedWidth, `${relativePath} width`);
  assert.equal(stats.height, expectedHeight, `${relativePath} height`);
  assert.ok(stats.visibleRatio > 0.08, `${relativePath} should have visible pixels`);
  assert.ok(stats.colorBuckets > 4, `${relativePath} should not be a flat placeholder`);
}

test('viewer icon PNG assets have expected dimensions and nonblank pixels', async () => {
  await assertPngAsset('rumi_viewer/assets/app-icon/rumiviewer-icon.png', 1254, 1254);
  await assertPngAsset('rumi_viewer/src-tauri/icons/32x32.png', 32, 32);
  await assertPngAsset('rumi_viewer/src-tauri/icons/128x128.png', 128, 128);
  await assertPngAsset('rumi_viewer/src-tauri/icons/128x128@2x.png', 256, 256);
  await assertPngAsset('rumi_viewer/src-tauri/icons/icon.png', 512, 512);
});

test('viewer tray icon and splash SVG are wired into Tauri resources', async () => {
  const tauriConfigRaw = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/tauri.conf.json'), 'utf8');
  const tauriConfig = JSON.parse(tauriConfigRaw);
  const splashHtml = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/splash/index.html'), 'utf8');
  const buildRs = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/build.rs'), 'utf8');
  const svgBuffer = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/splash/rumi_viewer_startup_blade_cut.svg'));
  const svg = svgBuffer.toString('utf8');
  const sourceIcon = await readFile(path.join(repoRoot, 'rumi_viewer/assets/app-icon/rumiviewer-icon.png'));
  const generatedIcon = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/icons/icon.png'));
  const ico = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/icons/icon.ico'));
  const icns = await readFile(path.join(repoRoot, 'rumi_viewer/src-tauri/icons/icon.icns'));

  assert.equal(tauriConfig.build.frontendDist, './splash');
  assert.equal(tauriConfig.app.trayIcon.iconPath, 'icons/icon.png');
  assert.equal(tauriConfig.app.trayIcon.iconAsTemplate, false);
  assert.match(splashHtml, /rumi_viewer_startup_blade_cut\.svg/);
  assert.doesNotMatch(splashHtml, /tobkiri/i);
  assert.match(buildRs, /rerun-if-changed=splash\/rumi_viewer_startup_blade_cut\.svg/);
  assert.match(svg, /<(?:[A-Za-z0-9_-]+:)?svg[\s>]/);
  assert.match(svg, /Rumi Viewer startup blade-cut animation/);
  assert.doesNotMatch(svg, /Tobkiri|tobkiri_ideas/i);
  assert.equal(textSha256(svg), expectedSplashSvgSha256);
  assert.equal(sha256(sourceIcon), expectedSourceIconSha256);
  assert.equal(sha256(generatedIcon), expectedGeneratedIconSha256);
  assert.ok(svg.length > 1000, 'splash SVG should not be empty');
  assert.ok(ico.byteLength > 1000, 'Windows icon should not be empty');
  assert.ok(icns.byteLength > 1000, 'macOS icon should not be empty');
});
