<!-- docs-i18n-links:start -->
[EN](../../ci_build_guide.md) | [JP](../ja/ci_build_guide.md) | [KR](../ko/ci_build_guide.md) | [CN](./ci_build_guide.md)
<!-- docs-i18n-links:end -->

# CI/CD 构建指南 — rumi_viewer 桌面应用

最后更新: 2026-03-29

总结了rumi_viewer（Tauri v2桌面应用程序）的CI构建和发布过程以及过去的失败记录的文档。

---

## 1. 概述

GitHub Actions 的`release.yml` 触发标签推送以在 4 个平台上执行同时构建，并将工件作为草稿上传到 GitHub Releases。

|平台|跑步者 |目标|神器|
|-----------------|---------|-----------|--------|
| macOS ARM | macOS 最新 | aarch64-苹果-达尔文 | .dmg |
| macOS 英特尔 | macos-15-英特尔 | x86_64-苹果-达尔文 | .dmg |
|窗户 | Windows 最新 | x86_64-pc-windows-msvc | x86_64-pc-windows-msvc | x86_64-pc-windows-msvc .exe (NSIS) |
| Linux | ubuntu-最新 | x86_64-未知-linux-gnu | .deb、.AppImage |

---

## 2. 发布流程

### 2.1 定期发布

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

### 2.2 测试发布（用于CI运行检查）

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

### 2.3 如何查看 CI 结果

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

## 3.release.yml的结构

```
.github/workflows/release.yml
```

- **触发器**：`push.tags: ["v*"]` — 以`v`开头的标签推送
- **矩阵**：4 个操作系统 x 目标的组合
- **主要步骤**：
  1. 结账
  2. 设置Python/Rust/Node
  3. 构建面板前端和defaultspack前端
  4. 为目标平台构建`pack-shell`
  5. 从`rumi_ai_1_10`中准备`rumi_viewer/src-tauri/gen/app`
  6. 构建（`cargo tauri build --target $target`）
  7. 上传发布工件（`softprops/action-gh-release`）

`rumi_viewer/src-tauri/gen/app` 不由 Git 管理。在 CI 中
`.github/scripts/prepare_tauri_resources.py`阶段运行时工具和Tauri
`build.rs` 也使用相同的排除规则重新生成`gen/app`。对于生成目标
`app.py`、`core_runtime/`、`ecosystem/defaultspack/`，内置面板/defaultspack UI，
包括`bundled/uv`、`bundled/pack-shell`。 §鲁米§2§，§鲁米§3§，
`user_data`、`__pycache__`、`.rumi_snapshots`、`tests/` 不包括在分发范围内。

如果你想检查PR上的分布情况，也可以手动运行。
使用`.github/workflows/desktop-installers.yml`。 Windows NSIS、macOS DMG、Linux
上传 DEB/AppImage 作为操作工件。典型的输出目的地如下。

- 窗户：`rumi_viewer/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe`
- macOS：`rumi_viewer/src-tauri/target/{target}/release/bundle/dmg/*.dmg`
- Linux：`rumi_viewer/src-tauri/target/x86_64-unknown-linux-gnu/release/bundle/{deb,appimage}/`

### 跑步者选择注意事项

GitHub Actions 运行者会定期退役。指定过时的运行程序会导致作业保留在队列中并失败。

|过时的跑步者 |过时日期 |更换|
|-------------------|--------|------|
| macOS-12 | 2024 年末 | macos-13 → macos-15 |
| macOS-13 | 2025 年 12 月 | macos-15-英特尔 |

**如何检查**：参见https://github.com/actions/runner-images.

---

## 4.图标文件管理

### 4.1 所需文件

构建 Tauri v2 需要以下图标文件：

```
rumi_viewer/src-tauri/icons/
├── 32x32.png         — 32×32 RGBA PNG
├── 128x128.png       — 128×128 RGBA PNG
├── 128x128@2x.png    — 256×256 RGBA PNG（Retina 用）
├── icon.png          — 512×512 RGBA PNG（アプリアイコン元画像）
├── icon.ico          — Windows 用 ICO（16/32/48/256 サイズ埋め込み）
└── icon.icns         — macOS 用 ICNS（128/256/512 サイズ埋め込み）
```

### 4.2 必须遵守

- **PNG 必须是 RGBA (color_type=6)**。使用 RGB (color_type=2) 时，Tauri 的 `generate_context!()` 宏会在编译时出现混乱
- **PNG 必须是正方形（宽度 == 高度）**。如果 AppImage 是非方形的，tauri-bundler 在捆绑 AppImage 时会出现恐慌
- **需要 icon.ico**。如果 Windows 上的 `build.rs` 不存在，则编译错误
- **枚举tauri.conf.json的bundle.icon中的路径**。如果不设置，会搜索默认路径，如果没有找到，就会出错。

### 4.3 当前图标

占位符（实心蓝色方块，R=100、G=100、B=200）。官方图标一旦确定，将会被更换。

### 4.4 图标更换流程

准备好官方图标后：

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

### 4.5 tauri.conf.json 中的bundle.icon 设置

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

icon.png 不需要包含在bundle.icon（在trayIcon.iconPath 中使用）中。

---

## 5.更新机制

### 5.1 目前状态：未实施

截至2026年3月29日，该应用程序的自动更新机制**未实现**。

- `tauri-plugin-updater` 未包含在 Cargo.toml 中
- `tauri.conf.json`至`plugins.updater`中没有章节
- `capabilities/default.json` 没有更新者权限

要更新，用户必须从 GitHub Releases 手动下载并重新安装新的二进制文件。

### 5.2 未来计划：U 阶段

预定在roadmap.md更新计划中实现：

- **U-1**：版本控制（获取当前版本，获取最新版本）
- **U-2**：更新检查 API（Cloudflare Workers 或 R2）
- **U-3**：Rust 启动器自我更新
- **U-4**：内核（Python 源代码）更新
- **U-5**：包更新

### 5.3 Tauri v2 更新插件（参考）

Tauri v2 有一个官方更新插件。实施步骤：

```
1. cargo add tauri-plugin-updater  (Cargo.toml)
2. tauri.conf.json に plugins.updater を追加
3. capabilities/default.json に "updater:default" を追加
4. アップデートサーバー（JSON エンドポイント）を用意
5. Rust 側で updater::Builder を初期化
```

然而，Rumi AI 的架构不仅需要更新 Rust 启动器，还需要更新 Python 内核和包，因此仅 Tauri 的标准更新器是不够的。在 U 阶段设计您自己的更新流程。

---

## 6.失败记录

### 6.1 v0.1.0-test.1 — 第一次 CI 运行（消灭）

**日期和时间**：2026-03-28 19:17 UTC
**结果**：手动取消（共4个作业，成功前取消）
**原因**：三个独立问题同时发生

#### 问题 1：macOS Intel runner 已弃用

- **症状**：`macos-13` 指定运行程序的作业保留在队列中并且不继续。
- **原因**：GitHub Actions 于 2025 年 12 月永久删除了`macos-13` 运行程序
- **理由**：GitHub 官方跑步者图像退役时间表

#### 问题 2：Windows 上缺少 icon.ico

- **症状**：Windows 版本上的`build.rs` 编译错误
- **原因**：`tauri-build` 中的`build.rs` 需要`icons/icon.ico`。该存储库只有 83 字节的 16×16 `icon.png`
- **基本原理**：Tauri v2 中的`build.rs` 将`.ico` 作为 Windows 二进制文件中的资源嵌入。

#### 问题 3：Linux 上的 AppImage 捆绑失败

- **症状**：捆绑 AppImage 时`tauri-bundler` 出现恐慌
- **原因**：`tauri-bundler`从图标目录中过滤了方形PNG（宽度==高度），导致0个结果。现有的`icon.png`为16×16，但可能未满足捆绑器要求的最小尺寸，或者捆绑器找不到`icon.png`
- **注意**：deb/rpm 捆绑成功。只有 AppImage 失败

### 6.2 v0.1.0-test.2 — 跑步者修复 + 图标生成（RGB 版本）

**日期和时间**：2026-03-28 20:15 UTC
**结果**：4个工作中，2个失败，2个预计成功，但最终被消灭。

|工作 |结果 |失败的步骤|
|--------|------|------------|
| macOS ARM（macos 最新）|失败|用货物构建Tauri |
| macOS 英特尔 (macos-15-intel) |失败|用货物构建Tauri |
| Linux（ubuntu-最新）|失败|用货物构建Tauri |
| Windows（Windows 最新）|失败|用货物构建Tauri |

**修改（在 v0.1.0-test.2 中应用）**：
- `macos-13` → 替换为 `macos-15-intel` → **跑步者问题已解决**（工作开始并进展到构建）
- 使用Python标准库（struct + zlib）生成PNG/ICO/ICNS → 文件已成功生成
- 添加了`bundle.icon`至`tauri.conf.json`

**新发现的问题**：

####问题4：PNG是RGB，Tauri需要RGBA

- **症状**：所有平台上都有相同的错误
  ```
  error: proc macro panicked
   --> src/lib.rs:150:14
    |
  150 |         .run(tauri::generate_context!())
    |              ^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = help: message: icon .../icons/32x32.png is not RGBA
  ```
- **原因**：Python 生成的 PNG color_type 为 `2`（RGB，3 字节/像素）。 Tauri 的 `generate_context!()` 宏在编译时解码 PNG，如果它不是 RGBA（color_type=6，4 字节/像素），则会出现恐慌
- **经验教训**：**务必以 RGBA 格式生成 Tauri 的图标 PNG (color_type=6)**。不允许 RGB

### 6.3 v0.1.0-test.3 — RGBA 修复（完全成功）

**日期和时间**：2026-03-28 22:21 UTC
**结果**：所有 4 项工作均成功

|工作 |结果 |构建时间 |
|--------|------|-----------|
| macOS ARM（macos 最新）|成功|约 3 分钟 |
| macOS 英特尔 (macos-15-intel) |成功| 〜5.5 分钟 |
| Linux（ubuntu-最新）|成功|约 4 分钟 |
| Windows（Windows 最新）|成功| 〜5.5 分钟 |

**修改详情**：
- 将 PNG 生成的`color_type` 更改为`2` (RGB) → `6` (RGBA)
- 更改了`bytes([r, g, b])`→`bytes([r, g, b, 255])`的像素数据
- 在验证步骤中添加了 IHDR color_type=6 检查

**检查所有步骤是否成功**：
- 签出→安装Rust→安装Tauri CLI→**使用货物tauri构建**→**上传发布工件**全部成功

---

## 7. 故障排除

### “图标...不是 RGBA”错误

PNG 为 RGB 模式。必须以 RGBA 格式再现（带 Alpha 通道）。

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

### 跑步者留在队列中并且没有进步

跑步者可能已过时。检查`runs-on`或`release.yml`。

```bash
grep "runs-on\|os:" .github/workflows/release.yml
```

查看https://github.com/actions/runner-images.上当前可用的跑步者

### AppImage 捆绑包出现恐慌

icon目录下没有正方形（宽==高）PNG，或者尺寸不够。在`ls -la rumi_viewer/src-tauri/icons/`中确认。

### 未创建草稿版本

如果没有与`files`模式匹配的文件，`softprops/action-gh-release@v2`可能不会创建版本。检查构建工件路径：

```
rumi_viewer/src-tauri/target/<target>/release/bundle/
├── dmg/   (macOS)
├── nsis/  (Windows)
├── deb/   (Linux)
└── appimage/ (Linux)
```

---

## 8. 更改历史记录

|日期 |内容 |
|------|------|
| 2026-03-29 |第一版已创建。描述 v0.1.0-test.1 至 3 的失败记录、构建过程、图标管理和更新机制的当前状态 |
