# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

![Test](https://github.com/harupipipipi/rumiai/actions/workflows/test.yml/badge.svg)
![Release](https://github.com/harupipipipi/rumiai/actions/workflows/release.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint. The canonical control panel frontend source lives in `rumi_viewer/frontend`; the kernel serves its built artifact at `/panel/`.

## Why Rumi AI

Rumi AI is a local-first runtime for building modular AI tools with explicit approval, audit, and pack boundaries. It is designed for workflows where users need AI-assisted coding, chat, browser/computer control, and custom tools without treating every extension as trusted code.

Key properties:

- Pack-based extensibility: application behavior lives in ecosystem packs, not in a privileged monolith.
- Approval-aware execution: host, file, terminal, browser, computer, git, and secret-handling paths are guarded.
- Auditability: security-sensitive paths are designed to leave operational traces.
- Cross-surface clients: Python runtime, Tauri desktop viewer, and Flutter mobile client live in one workspace.
- CI coverage: Python, frontend, Rust, Windows, macOS, installer, and security-audit lanes are represented in GitHub Actions.

## Read This When...

| やりたいこと | まず読む場所 | 補足 |
|---|---|---|
| 目的別にドキュメントを辿りたい | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | 「何をしたいか」から読む順番を案内します |
| とにかく起動したい | [`README.md`](./README.md) の `Start` | 最短の起動コマンドだけを載せています |
| 初回環境で成功判定したい | [`docs/first-run-check.md`](./docs/first-run-check.md) | `--health` の期待出力と失敗時の確認場所 |
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
| 参加・報告・セキュリティ連絡をしたい | [`CONTRIBUTING.md`](./CONTRIBUTING.md) / [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) / [`SECURITY.md`](./SECURITY.md) | Issue、PR、脆弱性報告の入口です |

## Repository Layout

- `rumi_ai_1_10/`: kernel/runtime/API/backend source tree
- `rumi_ai/`: version-stable Python entrypoint package
- `pack-shell/`: desktop pack launcher
- `rumi_viewer/`: desktop shell and control panel frontend source
- `rumi_mobile/`: Flutter iOS/Android app for trusted-LAN defaultspack access

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- Rust / Cargo (`rumi_viewer` を触る場合)
- Flutter SDK (`rumi_mobile` を触る場合)

### Clone and install

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

cd rumi_viewer/frontend
npm install
cd ../..
```

## Start

```bash
source .venv/bin/activate
python -m rumi_ai --health
rumi-ai --health
python -m rumi_ai
```

`--health` はシステムボリューム使用率も確認します。`disk` probe が `DEGRADED` / `DOWN` の場合は、コード不具合ではなく空き容量不足の可能性があります。
The editable install is rooted at the repository, so both `python -m rumi_ai --health` and `rumi-ai --health` work from outside the checkout after installation.
For first-run validation on a new machine, see [docs/first-run-check.md](./docs/first-run-check.md).

## Common Tasks

### Just shortcuts

If you have `just` installed, common checks are available from the repo root:

```bash
just -l
just tooling-test
just integrity
```

### Backend health check

```bash
python -m rumi_ai --health
rumi-ai --health
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
起動後は Home の `Open Defaultspack` から、managed current pointer で選択されている `Defaultspack v2` UI まで進めます。
起動時の詰まり方を含めたガイドは [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) を参照してください。

## Development

```bash
source .venv/bin/activate
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
- `rumi_ai_1_10`: kernel, runtime, API, backend, and docs
- `pack-shell`: launches desktop packs and brokers token/bootstrap flow
- `rumi_viewer`: viewer-side application shell and canonical panel frontend source
- `rumi_mobile`: mobile remote client for the bearer-auth Kernel Pack API

For architecture and runtime details, see [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md).

For Codex OSS-inspired coding-tool conventions, see [AGENTS.md](./AGENTS.md) and
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md).

## Community

Rumi AI is early but actively maintained. The best places to help are:

- Reproduce and minimize setup, viewer, or pack-runtime issues.
- Add small example packs that exercise one capability at a time.
- Improve docs for first-time users and pack authors.
- Review approval, audit, and capability-boundary changes carefully.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the contribution flow and [SECURITY.md](./SECURITY.md) for private vulnerability reports.
If you try the first-run health check, please share the outcome with a [setup feedback issue](https://github.com/harupipipipi/rumiai/issues/new?template=setup_feedback.yml).
For release work, see [docs/release-checklist.md](./docs/release-checklist.md).
For feedback and usage evidence tracking, see [docs/user-feedback-evidence.md](./docs/user-feedback-evidence.md).
For a short public demo outline, see [docs/demo-script.md](./docs/demo-script.md).
