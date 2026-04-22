# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint.

## Read This When...

| やりたいこと | まず読む場所 | 補足 |
|---|---|---|
| 目的別にドキュメントを辿りたい | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | 「何をしたいか」から読む順番を案内します |
| とにかく起動したい | [`README.md`](./README.md) の `Start` | 最短の起動コマンドだけを載せています |
| runtime / kernel の全体像を知りたい | [`rumi_ai_1_10/README.md`](./rumi_ai_1_10/README.md) | アーキテクチャと主要ディレクトリの説明があります |
| コードを読まずに仕組みを理解したい | [`rumi_ai_1_10/docs/concepts/system-mechanism.md`](./rumi_ai_1_10/docs/concepts/system-mechanism.md) | 起動・Flow・承認・Grant の流れを文章で追えます |
| まず動作確認したい（チュートリアル） | [`rumi_ai_1_10/docs/tutorials/runtime-quickstart.md`](./rumi_ai_1_10/docs/tutorials/runtime-quickstart.md) | `--health` から `/panel/` まで最短手順です |
| `rumi_viewer` を起動したい / viewer の詰まり方を見たい | [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) | 起動手順、`401`, 黒画面, `defaultspack` との関係をまとめています |
| viewer 側を直したい | [`rumi_viewer/src-tauri/src/config.rs`](./rumi_viewer/src-tauri/src/config.rs) と [`rumi_viewer/src-tauri/src/kernel_manager.rs`](./rumi_viewer/src-tauri/src/kernel_manager.rs) | viewer は Tauri shell、kernel 起動は Rust 側が担当です |
| pack / defaultspack を触りたい | [`rumi_ai_1_10/ecosystem/defaultspack/README.md`](./rumi_ai_1_10/ecosystem/defaultspack/README.md) | chat, ai_client, tool などの pack 側実装です |
| defaultspack の frontend 拡張方法を知りたい | [`rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md`](./rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md) | 右バー追加、設定追加、chat renderer 拡張、preview feed 追加の入り口です |
| API キーや secrets の扱いを知りたい | [`rumi_ai_1_10/docs/operations.md`](./rumi_ai_1_10/docs/operations.md) の Secrets 節 | `user_data/secrets/` と API 経路の説明があります |
| Pack の作り方を知りたい | [`rumi_ai_1_10/docs/pack-development.md`](./rumi_ai_1_10/docs/pack-development.md) | ecosystem.json, routes, permissions の作法をまとめています |
| 運用・監査の考え方を知りたい | [`rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`](./rumi_ai_1_10/docs/quality_pack/philosophy_memo.md) | 継続開発と回帰確認の前提を整理しています |

## Repository Layout

- `rumi_ai_1_10/`: current kernel/runtime source tree
- `rumi_ai/`: version-stable Python entrypoint package
- `pack-shell/`: desktop pack launcher
- `rumi_viewer/`: viewer application

## Start

```bash
python -m rumi_ai --health
python -m rumi_ai
```

## Common Tasks

### Backend health check

```bash
python -m rumi_ai --health
```

### Runtime startup

```bash
python -m rumi_ai
```

### Viewer development

```bash
cd rumi_viewer/src-tauri
cargo tauri dev
```

開発用 viewer は repo 内の `rumi_ai_1_10/` を自動検出して kernel を起動します。
起動時の詰まり方を含めたガイドは [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) を参照してください。

## Development

```bash
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## Quality Pack

継続開発・監査・回帰確認の運用パックは以下を参照:

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`

## HMAC Migration

```bash
python -m rumi_ai migrate-hmac
```

## Components

- `rumi_ai`: stable CLI and module entrypoint
- `rumi_ai_1_10`: kernel, runtime, frontend, and docs
- `pack-shell`: launches desktop packs and brokers token/bootstrap flow
- `rumi_viewer`: viewer-side application shell

For architecture and runtime details, see [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md).
