<!-- docs-i18n-links:start -->
[EN](../../ci_build_guide.md) | [JP](./ci_build_guide.md) | [KR](../ko/ci_build_guide.md) | [CN](../zh-cn/ci_build_guide.md)
<!-- docs-i18n-links:end -->

# CI/CD ビルド ガイド — rumi_viewer デスクトップ アプリ

最終更新日: 2026-03-29

rumi_viewer (Tauri v2 デスクトップ アプリ) の CI ビルドおよびリリース手順と過去の失敗記録をまとめたドキュメントです。

---

## 1. 概要

GitHub Actions の `release.yml` は、タグ プッシュをトリガーして 4 つのプラットフォームで同時ビルドを実行し、アーティファクトをドラフトとして GitHub Releases にアップロードします。

|プラットフォーム |ランナー |ターゲット |アーティファクト |
|-----------------|---------|-----------|--------|
| macOS ARM | macos-最新 | aarch64-アップル-ダーウィン | .dmg |
| macOS インテル | macos-15-インテル | x86_64-アップル-ダーウィン | .dmg |
|ウィンドウズ | Windows-最新 | x86_64-pc-windows-msvc | .exe (NSIS) |
|リナックス | ubuntu-最新 | x86_64-不明-linux-gnu | .deb、.AppImage |

---

## 2. 解除手順

### 2.1 通常リリース

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

### 2.2 テストリリース(CI動作確認用)

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

### 2.3 CI結果の確認方法

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

## 3. release.yml の構造

```
.github/workflows/release.yml
```

- **トリガー**: `push.tags: ["v*"]` — `v` で始まるタグプッシュ
- **マトリックス**: 4 つの OS x ターゲットの組み合わせ
- **主な手順**:
  1. チェックアウト
  2. Python / Rust / Nodeのセットアップ
  3. ビルドパネルフロントエンドとdefaultspackフロントエンド
  4. ターゲット プラットフォーム用の `pack-shell` をビルドします。
  5. `rumi_ai_1_10`から`rumi_viewer/src-tauri/gen/app`を作成する
  6. ビルド(`cargo tauri build --target $target`)
  7. リリース アーティファクトのアップロード (`softprops/action-gh-release`)

`rumi_viewer/src-tauri/gen/app` は Git によって管理されません。 CIで
`.github/scripts/prepare_tauri_resources.py` ステージランタイムツールと Tauri
`build.rs` は、同じ除外ルールで `gen/app` も再生成します。世代ターゲットについて
`app.py`、`core_runtime/`、`ecosystem/defaultspack/`、ビルドパネル/デフォルトパックUI、
`bundled/uv`、`bundled/pack-shell`が収録されています。 `.venv`、`node_modules`、
`user_data`、`__pycache__`、`.rumi_snapshots`、`tests/`は配布対象外となります。

PR で配信を確認したい場合は、手動で実行することもできます。
`.github/workflows/desktop-installers.yml`を使用します。 Windows NSIS、macOS DMG、Linux
DEB/AppImage をアクション アーティファクトとしてアップロードします。一般的な出力先は以下のとおりです。

- Windows: `rumi_viewer/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe`
- macOS: `rumi_viewer/src-tauri/target/{target}/release/bundle/dmg/*.dmg`
- Linux: `rumi_viewer/src-tauri/target/x86_64-unknown-linux-gnu/release/bundle/{deb,appimage}/`

### ランナー選択時の注意点

GitHub Actions ランナーは定期的に廃止されます。古いランナーを指定すると、ジョブがキュー内に残り、失敗します。

|時代遅れのランナー |廃止日 |交換 |
|-------------------|--------|------|
| macos-12 | 2024 年後半 | macos-13 → macos-15 |
| macos-13 | 2025-12 | macos-15-インテル |

**確認方法**: https://github.com/actions/runner-images.を参照

---

## 4. アイコンファイルの管理

### 4.1 必要なファイル

Tauri v2 をビルドするには、次のアイコン ファイルが必要です。

```
rumi_viewer/src-tauri/icons/
├── 32x32.png         — 32×32 RGBA PNG
├── 128x128.png       — 128×128 RGBA PNG
├── 128x128@2x.png    — 256×256 RGBA PNG（Retina 用）
├── icon.png          — 512×512 RGBA PNG（アプリアイコン元画像）
├── icon.ico          — Windows 用 ICO（16/32/48/256 サイズ埋め込み）
└── icon.icns         — macOS 用 ICNS（128/256/512 サイズ埋め込み）
```

### 4.2 必ず遵守してください

- **PNG は RGBA (color_type=6)** である必要があります。 Tauri の `generate_context!()` マクロは、RGB (color_type=2) を使用するとコンパイル時にパニックになります。
- **PNG は正方形 (幅 == 高さ)** である必要があります。 AppImage が正方形でない場合、AppImage をバンドルするときに tauri-bundler がパニックを起こす
- **icon.ico は必須です**。 Windows で `build.rs` が存在しない場合コンパイル エラーになる
- **tauri.conf.json の Bundle.icon 内のパスを列挙します**。設定されていない場合は、デフォルトのパスが検索され、見つからない場合はエラーが発生します。

### 4.3 現在のアイコン

プレースホルダー (R=100、G=100、B=200 の青い実線の四角形)。公式アイコンが決まり次第、差し替えさせていただきます。

### 4.4 アイコンの置き換え手順

公式アイコンを準備したら、次のようにします。

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

### 4.5 tauri.conf.json の Bundle.icon 設定

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

icon.png は、bundle.icon (trayIcon.iconPath で使用) に含める必要はありません。

---

## 5. 更新メカニズム

### 5.1 現在のステータス: 未実装

2026 年 3 月 29 日の時点では、アプリの自動更新メカニズムは **実装されていません**。

- `tauri-plugin-updater`はCargo.tomlには含まれていません
- `tauri.conf.json` ～ `plugins.updater` にセクションがありません
- `capabilities/default.json` にはアップデーター権限がありません

更新するには、ユーザーは GitHub リリースから新しいバイナリを手動でダウンロードして再インストールする必要があります。

### 5.2 将来の計画: フェーズ U

roadmap.md 更新計画で実装予定:

- **U-1**: バージョン管理 (現在のバージョンの取得、最新バージョンの取得)
- **U-2**: 更新チェック API (Cloudflare Workers または R2)
- **U-3**: Rust ランチャーの自己更新
- **U-4**: カーネル (Python ソース コード) の更新
- **U-5**: パックのアップデート

### 5.3 Tauri v2 アップデータ プラグイン (参照)

Tauri v2 には公式アップデータ プラグインがあります。実装する手順:

```
1. cargo add tauri-plugin-updater  (Cargo.toml)
2. tauri.conf.json に plugins.updater を追加
3. capabilities/default.json に "updater:default" を追加
4. アップデートサーバー（JSON エンドポイント）を用意
5. Rust 側で updater::Builder を初期化
```

ただし、Rumi AI のアーキテクチャでは Rust ランチャーだけでなく Python カーネルやパックも更新する必要があるため、Tauri の標準アップデータだけでは十分ではありません。フェーズ U では独自の更新フローを設計します。

---

## 6. 失敗記録

### 6.1 v0.1.0-test.1 — 最初の CI 実行 (消滅)

**日付と時刻**: 2026-03-28 19:17 UTC**結果**: 手動キャンセル (4 つのジョブのうち、成功する前にキャンセルされました)**原因**: 3 つの独立した問題が同時に発生しています

#### 問題 1: macOS Intel ランナーが非推奨になりました

- **症状**: `macos-13` ランナーが指定されたジョブがキュー内に残り、続行されません。
- **原因**: GitHub Actions は 2025 年 12 月に `macos-13` ランナーを完全に削除しました
- **根拠**: GitHub 公式ランナー イメージの廃止スケジュール

#### 問題 2: Windows に icon.ico が存在しない

- **症状**: Windows ビルドで `build.rs` コンパイル エラーが発生する
- **原因**: `tauri-build` の `build.rs` には `icons/icon.ico` が必要です。リポジトリには 16×16 `icon.png` の 83 バイトしかありませんでした。
- **根拠**: Tauri v2 の `build.rs` は、Windows バイナリのリソースとして `.ico` を埋め込みます。

#### 問題 3: Linux での AppImage バンドルの失敗

- **症状**: AppImage をバンドルすると `tauri-bundler` がパニックを起こす
- **原因**: `tauri-bundler` がアイコン ディレクトリから正方形 PNG (幅 == 高さ) をフィルタリングしたため、結果が 0 件になりました。既存の `icon.png` は 16×16 でしたが、バンドラーが必要とする最小サイズを満たしていないか、バンドラーが `icon.png` を見つけられなかった可能性があります。
- **注**: deb/rpm バンドルは成功しました。 AppImage のみが失敗する

### 6.2 v0.1.0-test.2 — ランナー修正 + アイコン生成 (RGB バージョン)

**日付と時刻**: 2026-03-28 20:15 UTC**結果**: 4 つのジョブのうち 2 つは失敗し、2 つは成功することが期待されましたが、最終的には全滅しました。

|仕事 |結果 |失敗したステップ |
|--------|------|------------|
| macOS ARM (macos-最新) |失敗 |カーゴタウリで構築する |
| macOS インテル (macos-15-intel) |失敗 |カーゴタウリで構築する |
| Linux (ubuntu-最新) |失敗 |カーゴタウリで構築する |
| Windows (最新の Windows) |失敗 |カーゴタウリで構築する |

**変更点 (v0.1.0-test.2 で適用)**:
- `macos-13` → `macos-15-intel` に置き換え → **ランナーの問題は解決されました** (ジョブが開始され、ビルドが進行しました)
- Python標準ライブラリ(struct + zlib)でPNG/ICO/ICNSを生成 → ファイル生成成功
- `bundle.icon`を`tauri.conf.json`に追加しました。

**新たに発見された問題**:

#### 問題 4: PNG は RGB ですが、Tauri には RGBA が必要です

- **症状**: すべてのプラットフォームで同じエラーが発生する
  ```
  error: proc macro panicked
   --> src/lib.rs:150:14
    |
  150 |         .run(tauri::generate_context!())
    |              ^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = help: message: icon .../icons/32x32.png is not RGBA
  ```
- **原因**: Python によって生成された PNG の color_type は `2` (RGB、3 バイト/ピクセル) でした。 Tauri の `generate_context!()` マクロはコンパイル時に PNG をデコードし、RGBA (color_type=6、4 バイト/ピクセル) でない場合にパニックを起こします。
- **学んだ教訓**:**Tauri のアイコン PNG を必ず RGBA (color_type=6) で生成してください**。 RGB は許可されません

### 6.3 v0.1.0-test.3 — RGBA 修正 (完全成功)

**日付と時刻**: 2026-03-28 22:21 UTC**結果**: 4 つのジョブはすべて成功しました

|仕事 |結果 |ビルド時間 |
|--------|------|-----------|
| macOS ARM (macos-最新) |成功 | ～3分 |
| macOS インテル (macos-15-intel) |成功 | ～5.5分 |
| Linux (ubuntu-最新) |成功 | ～4分 |
| Windows (最新の Windows) |成功 | ～5.5分 |

**変更の詳細**:
- PNG生成の`color_type`を`2`(RGB)→`6`(RGBA)に変更
- ピクセルデータを `bytes([r, g, b])` → `bytes([r, g, b, 255])` に変更しました。
- IHDR color_type=6 チェックを検証ステップに追加しました

**すべてのステップが成功したかどうかを確認します**:
- チェックアウト → Rust のインストール → Tauri CLI のインストール → **Cargo tauri でビルド** →**リリース アーティファクトのアップロード** すべて成功

---

## 7. トラブルシューティング

### 「アイコン ... は RGBA ではありません」エラー

PNG は RGB モードです。 RGBA (アルファ チャネル付き) で再現する必要があります。

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

### ランナーは列に残ったまま進まない

ランナーが廃盤になっている可能性があります。 `runs-on` の `release.yml` を確認してください。

```bash
grep "runs-on\|os:" .github/workflows/release.yml
```

現在入手可能なランナーはhttps://github.com/actions/runner-images.でご覧ください。

### AppImage バンドルでパニック

アイコンディレクトリに正方形（幅==高さ）のPNGが存在しないか、サイズが不足しています。 `ls -la rumi_viewer/src-tauri/icons/`で確認。

### ドラフトリリースは作成されていません

`softprops/action-gh-release@v2` は、`files` パターンに一致するファイルがない場合、リリースを作成できない場合があります。ビルド アーティファクトのパスを確認します。

```
rumi_viewer/src-tauri/target/<target>/release/bundle/
├── dmg/   (macOS)
├── nsis/  (Windows)
├── deb/   (Linux)
└── appimage/ (Linux)
```

---

## 8. 変更履歴

|日付 |目次 |
|------|------|
| 2026-03-29 |初版作成。 v0.1.0-test.1 ～ 3 の障害記録の現状、ビルド手順、アイコン管理、更新の仕組みについて説明します。
