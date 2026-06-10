<!-- docs-i18n-links:start -->
[EN](./ci_build_guide.md) | [JP](./i18n/ja/ci_build_guide.md) | [KR](./i18n/ko/ci_build_guide.md) | [CN](./i18n/zh-cn/ci_build_guide.md)
<!-- docs-i18n-links:end -->

# CI/CD build guide — rumi_viewer desktop app

Last updated: 2026-03-29

A document that summarizes CI build and release procedures for rumi_viewer (Tauri v2 desktop app) and past failure records.

---

## 1. Overview

`release.yml` of GitHub Actions triggers a tag push to perform a simultaneous build on 4 platforms, and uploads the artifact as a draft to GitHub Releases.

| Platform | Runner | Target | Artifact |
|-----------------|---------|-----------|--------|
| macOS ARM | macos-latest | aarch64-apple-darwin | .dmg |
| macOS Intel | macos-15-intel | x86_64-apple-darwin | .dmg |
| Windows | windows-latest | x86_64-pc-windows-msvc | .exe (NSIS) |
| Linux | ubuntu-latest | x86_64-unknown-linux-gnu | .deb, .AppImage |

---

## 2. Release procedure

### 2.1 Regular release

```bash
# 1. バージョンを更新（tauri.conf.json と Cargo.toml の version）
#    tauri.conf.json: "version": "0.2.0"
#    Cargo.toml:      version = "0.2.0"

# 2. コミット
git add rumi_viewer/src-tauri/tauri.conf.json rumi_viewer/src-tauri/Cargo.toml
git commit -m "release: v0.2.0"

# 3. tag push（これが CI トリガー）
git tag v0.2.0
git push origin master
git push origin v0.2.0

# 4. GitHub Actions が自動で 4 プラットフォームビルド
#    → GitHub Releases に draft release が作られる

# 5. GitHub の Releases ページで draft を確認 → 公開
```

### 2.2 Test release (for CI operation check)

```bash
# test tag はインクリメントする（v0.1.0-test.1, .2, .3, ...）
# 既存の test tag を確認
git tag -l "v0.1.0-test*"

# 次の番号で tag push
git tag v0.1.0-test.4
git push origin v0.1.0-test.4

# CI の結果を確認
# https://github.com/harupipipipi/rumiai/actions
```

### 2.3 How to check CI results

```bash
# ブラウザで確認
# https://github.com/harupipipipi/rumiai/actions

# API で確認（ログイン不要）
curl -s https://api.github.com/repos/harupipipipi/rumiai/actions/runs?per_page=3 \
  | python3 -c "
import json, sys
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"{r['head_branch']:20s} {r['status']:12s} {r['conclusion'] or '':10s} {r['created_at']}\")
"

# ジョブ単位の確認
curl -s https://api.github.com/repos/harupipipipi/rumiai/actions/runs/<RUN_ID>/jobs \
  | python3 -c "
import json, sys
jobs = json.load(sys.stdin)['jobs']
for j in jobs:
    print(f\"{j['name']:50s} {j['status']:12s} {j['conclusion'] or '':10s}\")
"
```

---

## 3. Structure of release.yml

```
.github/workflows/release.yml
```

- **Trigger**: `push.tags: ["v*"]` — tag push starting with `v`
- **Matrix**: combination of 4 os x target
- **Main steps**:
  1. Checkout
  2. Set up Python / Rust / Node
  3. Build panel frontend and defaultspack frontend
  4. Build `pack-shell` for the target platform
  5. Prepare `rumi_viewer/src-tauri/gen/app` from `rumi_ai_1_10`
  6. Build (`cargo tauri build --target $target`)
  7. Upload release artifacts (`softprops/action-gh-release`)

`rumi_viewer/src-tauri/gen/app` is not managed by Git. In CI
`.github/scripts/prepare_tauri_resources.py` stages runtime tools and Tauri
`build.rs` also regenerates `gen/app` with the same exclusion rules. For generation target
`app.py`, `core_runtime/`, `ecosystem/defaultspack/`, built panel/defaultspack UI,
`bundled/uv`, `bundled/pack-shell` are included. `.venv`, `node_modules`,
`user_data`, `__pycache__`, `.rumi_snapshots`, `tests/` are excluded from the distribution.

If you want to check the distribution on PR, you can also run it manually.
Use `.github/workflows/desktop-installers.yml`. Windows NSIS, macOS DMG, Linux
Upload DEB/AppImage as Actions artifact. Typical output destinations are below.

- Windows: `rumi_viewer/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe`
- macOS: `rumi_viewer/src-tauri/target/{target}/release/bundle/dmg/*.dmg`
- Linux: `rumi_viewer/src-tauri/target/x86_64-unknown-linux-gnu/release/bundle/{deb,appimage}/`

### Notes on runner selection

GitHub Actions runners are periodically retired. Specifying an obsolete runner causes the job to remain in the queue and fail.

| Obsolete Runner | Obsolescence Date | Replacement |
|-------------------|--------|------|
| macos-12 | Late 2024 | macos-13 → macos-15 |
| macos-13 | 2025-12 | macos-15-intel |

**How to check**: See https://github.com/actions/runner-images.

---

## 4. Icon file management

### 4.1 Required files

Building Tauri v2 requires the following icon files:

```
rumi_viewer/src-tauri/icons/
├── 32x32.png         — 32×32 RGBA PNG
├── 128x128.png       — 128×128 RGBA PNG
├── 128x128@2x.png    — 256×256 RGBA PNG（Retina 用）
├── icon.png          — 512×512 RGBA PNG（アプリアイコン元画像）
├── icon.ico          — Windows 用 ICO（16/32/48/256 サイズ埋め込み）
└── icon.icns         — macOS 用 ICNS（128/256/512 サイズ埋め込み）
```

### 4.2 Must be observed

- **PNG must be RGBA (color_type=6)**. Tauri's `generate_context!()` macro panics at compile time when using RGB (color_type=2)
- **PNG must be square (width == height)**. tauri-bundler panics when bundling AppImage if it is non-square
- **icon.ico is required**. Compile error with `build.rs` on Windows if it does not exist
- **Enumerate paths in bundle.icon of tauri.conf.json**. If not set, the default path will be searched, and if not found, an error will occur.

### 4.3 Current icon

Placeholder (solid blue square with R=100, G=100, B=200). Once the official icon is decided, it will be replaced.

### 4.4 Icon replacement procedure

After preparing the official icon:

```bash
# 方法 1: cargo tauri icon コマンド（Tauri CLI がインストール済みの場合）
# 1024x1024 以上の正方形 RGBA PNG を用意
cargo tauri icon path/to/new_icon.png

# 方法 2: 手動で各サイズを生成
# 画像編集ソフトで 32x32, 128x128, 256x256, 512x512 の RGBA PNG を書き出し
# ICO と ICNS は専用ツールで生成

# 差し替え後は必ず test tag で CI 確認
git add rumi_viewer/src-tauri/icons/
git commit -m "chore: update app icons"
git push origin master
git tag v0.x.y-test.1
git push origin v0.x.y-test.1
```

### 4.5 bundle.icon settings in tauri.conf.json

```json
{
  "bundle": {
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

icon.png does not need to be included in bundle.icon (used in trayIcon.iconPath).

---

## 5. Update mechanism

### 5.1 Current status: Not implemented

As of 2026-03-29, the automatic update mechanism for the app is **not implemented**.

- `tauri-plugin-updater` is not included in Cargo.toml
- No section in `tauri.conf.json` to `plugins.updater`
- No updater permission on `capabilities/default.json`

To update, users must manually download and reinstall new binaries from GitHub Releases.

### 5.2 Future Plan: Phase U

Scheduled to be implemented in roadmap.md update plan:

- **U-1**: Version control (get current version, get latest version)
- **U-2**: Update check API (Cloudflare Workers or R2)
- **U-3**: Rust launcher self-update
- **U-4**: Kernel (Python source code) update
- **U-5**: Pack update

### 5.3 Tauri v2 updater plugin (reference)

Tauri v2 has an official updater plugin. Steps to implement:

```
1. cargo add tauri-plugin-updater  (Cargo.toml)
2. tauri.conf.json に plugins.updater を追加
3. capabilities/default.json に "updater:default" を追加
4. アップデートサーバー（JSON エンドポイント）を用意
5. Rust 側で updater::Builder を初期化
```

However, Rumi AI's architecture requires updating not only the Rust launcher but also the Python Kernel and Packs, so Tauri's standard updater alone is not sufficient. Design your own update flow in Phase U.

---

## 6. Failure record

### 6.1 v0.1.0-test.1 — First CI run (annihilation)

**Date and time**: 2026-03-28 19:17 UTC
**Result**: Manual cancellation (out of 4 jobs, canceled before success)
**Cause**: Three independent issues occurring at the same time

#### Issue 1: macOS Intel runner deprecated

- **Symptom**: `macos-13` A job with a runner specified remains in the queue and does not proceed.
- **Cause**: GitHub Actions permanently removed the `macos-13` runner in December 2025
- **Rationale**: GitHub official runner image retirement schedule

#### Problem 2: icon.ico missing on Windows

- **Symptom**: `build.rs` compile error on Windows build
- **Cause**: `build.rs` of `tauri-build` requires `icons/icon.ico`. The repository only had 83 bytes of 16×16 `icon.png`
- **Rationale**: `build.rs` in Tauri v2 embeds `.ico` as a resource in Windows binaries.

#### Issue 3: AppImage bundle failure on Linux

- **Symptom**: `tauri-bundler` panics when bundling AppImage
- **Cause**: `tauri-bundler` filtered square PNGs (width == height) from the icons directory, resulting in 0 results. The existing `icon.png` was 16×16, but it may not have met the minimum size required by the bundler, or the bundler could not find the `icon.png`
- **Note**: deb/rpm bundle was successful. Only AppImage fails

### 6.2 v0.1.0-test.2 — Runner fix + icon generation (RGB version)

**Date and time**: 2026-03-28 20:15 UTC
**Result**: Out of 4 jobs, 2 failed, 2 were expected to be successful, but in the end they were wiped out.

| Job | Result | Failed Step |
|--------|------|------------|
| macOS ARM (macos-latest) | failure | Build with cargo tauri |
| macOS Intel (macos-15-intel) | failure | Build with cargo tauri |
| Linux (ubuntu-latest) | failure | Build with cargo tauri |
| Windows (windows-latest) | failure | Build with cargo tauri |

**Modifications (applied in v0.1.0-test.2)**:
- `macos-13` → Replaced with `macos-15-intel` → **Runner problem solved** (Job started and progressed to build)
- Generate PNG/ICO/ICNS with Python standard library (struct + zlib) → File was generated successfully
- Added `bundle.icon` to `tauri.conf.json`

**Newly discovered issues**:

#### Problem 4: PNG is RGB and Tauri requires RGBA

- **Symptom**: Same error on all platforms
  ```
  error: proc macro panicked
   --> src/lib.rs:150:14
    |
  150 |         .run(tauri::generate_context!())
    |              ^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = help: message: icon .../icons/32x32.png is not RGBA
  ```
- **Cause**: The color_type of PNG generated by Python was `2` (RGB, 3 bytes/pixel). Tauri's `generate_context!()` macro decodes PNG at compile time and panics if it is not RGBA (color_type=6, 4 bytes/pixel)
- **Lesson learned**: **Be sure to generate Tauri's icon PNG in RGBA (color_type=6)**. RGB not allowed

### 6.3 v0.1.0-test.3 — RGBA fix (full success)

**Date and time**: 2026-03-28 22:21 UTC
**Result**: All 4 jobs successful

| Job | Results | Build Time |
|--------|------|-----------|
| macOS ARM (macos-latest) | success | ~3 min |
| macOS Intel (macos-15-intel) | success | ~5.5 min |
| Linux (ubuntu-latest) | success | ~4 min |
| Windows (windows-latest) | success | ~5.5 min |

**Modification details**:
- Changed `color_type` of PNG generation to `2` (RGB) → `6` (RGBA)
- Changed pixel data from `bytes([r, g, b])` → `bytes([r, g, b, 255])`
- Added IHDR color_type=6 check to validation step

**Check success of all steps**:
- Checkout → Install Rust → Install Tauri CLI → **Build with cargo tauri** → **Upload release artifacts** All success

---

## 7. Troubleshooting

### "icon ... is not RGBA" error

PNG is in RGB mode. Must be reproduced in RGBA (with alpha channel).

```bash
# 確認方法
python3 -c "
import struct
with open('rumi_viewer/src-tauri/icons/32x32.png', 'rb') as f:
    f.read(8)  # signature
    f.read(4)  # IHDR length
    f.read(4)  # 'IHDR'
    data = f.read(13)
    w, h, depth, ctype = struct.unpack('>IIBB', data[:10])
    print(f'{w}x{h} depth={depth} color_type={ctype}')
    # color_type=6 なら RGBA、2 なら RGB（NG）
"
```

### Runner stays in queue and doesn't progress

The runner may be obsolete. Check `runs-on` of `release.yml`.

```bash
grep "runs-on\|os:" .github/workflows/release.yml
```

See currently available runners on https://github.com/actions/runner-images.

### Panic on AppImage bundle

There is no square (width == height) PNG in the icons directory, or the size is insufficient. Confirmed in `ls -la rumi_viewer/src-tauri/icons/`.

### Draft release not created

`softprops/action-gh-release@v2` may not create a release if there are no files matching the `files` pattern. Check the build artifact path:

```
rumi_viewer/src-tauri/target/<target>/release/bundle/
├── dmg/   (macOS)
├── nsis/  (Windows)
├── deb/   (Linux)
└── appimage/ (Linux)
```

---

## 8. Change history

| Date | Contents |
|------|------|
| 2026-03-29 | First edition created. Describes the current status of failure records, build procedures, icon management, and update mechanism for v0.1.0-test.1 to 3 |
