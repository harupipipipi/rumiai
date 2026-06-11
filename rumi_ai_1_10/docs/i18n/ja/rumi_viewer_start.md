<!-- docs-i18n-links:start -->
[EN](../../rumi_viewer_start.md) | [JP](./rumi_viewer_start.md) | [KR](../ko/rumi_viewer_start.md) | [CN](../zh-cn/rumi_viewer_start.md)
<!-- docs-i18n-links:end -->

# rumi_viewer Start Guide

`rumi_viewer` は Tauri 製の desktop shell です。開発起動では repo 内の `rumi_ai_1_10/` を自動検出し、Python kernel を起動して panel UI へ接続します。
control panel frontend の source は `rumi_viewer/frontend` が所有し、kernel は build 済み artifact を `rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web` から `/panel/` として配信します。

## これを読むタイミング

- viewer を最短で起動したい
- viewer が kernel を見つけられず止まる
- panel は開くが画面遷移が崩れる
- `defaultspack` の frontend / panel まわりの起動経路を追いたい

## 最短の起動手順

repo ルートで次を実行します。

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

2 回目以降、`rumi_viewer/frontend/node_modules` が残っている場合は次だけで起動できます。

```bash
cd rumi_viewer
cargo tauri dev
```

開発起動では viewer が次を自動で行います。

1. repo 内の `rumi_ai_1_10/` を検出する
2. `~/Library/Application Support/dev.rumiai.app/venv` を用意する
3. `python -m app` で kernel を起動する
4. `http://127.0.0.1:8765/panel/` へ bootstrap する
5. viewer から `Open Defaultspack` を押すと `defaultspack` の独立 UI を開く

## 開発時の承認フロー

- repo checkout を検出しても、それだけでは pack 自動承認は有効になりません
- 開発環境として kernel へ `RUMI_ENVIRONMENT=development` は渡されます
- `RUMI_AUTO_APPROVE_LOCAL=true` を明示して viewer を起動したときだけ、開発用の自動承認が有効になります

例:

```bash
cd rumi_viewer
RUMI_AUTO_APPROVE_LOCAL=true cargo tauri dev
```

この opt-in を付けない通常の開発起動では、modified pack は再承認待ちのままです。

## 起動できたときの見え方

- 正常起動すると Tauri window が開きます
- 初回状態では `/health` が `needs_setup: true` を返すことがあり、その場合は setup 画面から始まります
- setup 完了後は panel UI に遷移します
- panel の Home から `Open Defaultspack` を押すと、viewer が `defaultspack` の browser UI を起動します

## defaultspack との関係

- viewer が直接開くのは kernel の control panel (`/panel/`) です
- frontend source は viewer 側にありますが、配信経路は kernel の `/panel/` のままです
- `defaultspack` 自体は kernel から component として読み込まれます
- `defaultspack` の独立 HTTP frontend は `DEFAULTS_HTTP_PORT` 既定値 `8766` ですが、viewer の初期導線とは別です
- 開発起動 (`cargo tauri dev`) では repo 同梱の `rumi_ai_1_10/ecosystem/defaultspack/` を優先して開きます
- 配布版 / bundle 起動では `rumi_home/user_data/packs/defaultspack/current.json` を見て、移行互換として `app_data_dir/user_data/packs/defaultspack/current.json` も参照します
- そのため setup/更新済みの `Defaultspack v2` が managed pack として切り替わっていれば、配布版 viewer からその実体を開けます

## よくある詰まり方

### `Kernel directory not found`

viewer が bundle 内の `app/` しか見ていないか、repo checkout を検出できていません。開発起動は repo ルート配下で行ってください。

### `panel bootstrap returned 401 Unauthorized`

bootstrap secret がずれているか、古い kernel がポート `8765` を掴んでいる可能性があります。以下で占有を確認します。

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

### Home などを押すと真っ暗になる

panel frontend は `basename="/panel"` 前提です。リンクや `navigate()` で `/panel/...` を二重に付けると `/panel/panel` に飛んでルート不一致になります。frontend 側のルートは `/`, `/packs`, `/flows`, `/settings` のように basename 相対で持たせてください。

## 確認コマンド

kernel が起動しているかを確認:

```bash
curl http://127.0.0.1:8765/health
```

defaultspack 独立 frontend が起動しているかを確認:

```bash
curl http://127.0.0.1:8766/api/health
```

## 関連ファイル

- `rumi_viewer/src-tauri/src/config.rs`
- `rumi_viewer/src-tauri/src/kernel_manager.rs`
- `rumi_viewer/src-tauri/src/lib.rs`
- `rumi_viewer/frontend/src/App.tsx`
- `rumi_viewer/frontend/src/lib/routes.ts`
