# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint. The canonical control panel frontend source lives in `rumi_viewer/frontend`; the kernel serves its built artifact at `/panel/`.

## Quick Start (5 minutes)

Get Rumi AI running in 5 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

# 2. Set up Python environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python -m pip install --upgrade pip

# 3. Install dependencies
pip install -r rumi_ai_1_10/requirements.txt
pip install -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

# 4. Run health check
python -m rumi_ai --health

# 5. Start the runtime
python -m rumi_ai
```

After starting, open http://localhost:8080/panel/ in your browser to access the control panel.

## Read This When...

| やりたいこと | まず読む場所 | 補足 |
|---|---|---|
| 目的別にドキュメントを辿りたい | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | 「何をしたいか」から読む順番を案内します |
| 用語の意味を揃えたい | [`rumi_ai_1_10/docs/terminology.md`](./rumi_ai_1_10/docs/terminology.md) | `rule`, `skill`, `team workspace`, `subagent` 互換名の整理です |
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

- `rumi_ai_1_10/`: kernel/runtime/API/backend source tree
- `rumi_ai/`: version-stable Python entrypoint package
- `pack-shell/`: desktop pack launcher
- `rumi_viewer/`: desktop shell and control panel frontend source
- `rumi_mobile/`: Flutter iOS/Android app for trusted-LAN defaultspack access
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/`: browser companion assets bundled with defaultspack

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- uv (`rumi_viewer` を触る場合)
- Rust / Cargo (`rumi_viewer` を触る場合)
- Flutter SDK (`rumi_mobile` を触る場合)

### Clone and install

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt
pip install -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

cd rumi_viewer/frontend
npm install
cd ../..
```

## Start

```bash
source .venv/bin/activate
python -m rumi_ai --health
python -m rumi_ai
```

`--health` はシステムボリューム使用率も確認します。`disk` probe が `DEGRADED` / `DOWN` の場合は、コード不具合ではなく空き容量不足の可能性があります。

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
```

### Runtime startup

```bash
python -m rumi_ai
```

### Viewer development

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

開発用 viewer は repo 内の `rumi_ai_1_10/` を自動検出して kernel を起動します。
`Open Defaultspack` は開発起動では repo 同梱の `defaultspack` を優先して開きます。
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
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`: unpacked Chromium extension for the defaultspack `browser_companion` tool

## Troubleshooting

### Common Issues

#### 1. Health check fails with "disk probe DEGRADED/DOWN"

**Problem**: `python -m rumi_ai --health` shows disk probe as DEGRADED or DOWN.

**Solution**: This is usually a disk space issue, not a code problem.
```bash
# Check disk space
df -h

# Clean up unnecessary files
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r rumi_ai_1_10/requirements.txt
```

#### 2. Port 8080 already in use

**Problem**: `python -m rumi_ai` fails with "Address already in use".

**Solution**: Kill the process using port 8080.
```bash
# Find process using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>
```

#### 3. Viewer shows 401 error

**Problem**: Opening the panel shows 401 Unauthorized.

**Solution**: Check API token configuration.
```bash
# Check if API token is set
echo $RUMI_API_TOKEN

# Set API token if needed
export RUMI_API_TOKEN="your-token-here"
```

#### 4. Frontend build fails

**Problem**: `npm run build` fails in rumi_viewer/frontend.

**Solution**: Clear node_modules and reinstall.
```bash
cd rumi_viewer/frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

#### 5. Python import errors

**Problem**: `ModuleNotFoundError` when running tests.

**Solution**: Ensure you're in the virtual environment and package is installed.
```bash
source .venv/bin/activate
pip install -e ./rumi_ai_1_10
```

### Getting Help

If you encounter issues not covered here:

1. Check the [documentation](./rumi_ai_1_10/docs/README.md)
2. Search existing [GitHub Issues](https://github.com/harupipipipi/rumiai/issues)
3. Create a new issue with:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Error messages/logs

## Contributing

We welcome contributions! Please follow these guidelines:

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `just tooling-test`
5. Run linting: `just lint`
6. Commit your changes: `git commit -m 'Add your feature'`
7. Push to the branch: `git push origin feature/your-feature`
8. Create a Pull Request

### Code Style

- Python: Follow PEP 8, use type hints
- JavaScript/TypeScript: Use ESLint configuration
- Rust: Follow rustfmt defaults

### Testing

- Add tests for new features
- Ensure existing tests pass
- Run focused tests: `python -m pytest tests/test_specific.py -q`

### Pull Request Guidelines

- Use the PR template provided
- Include a clear description
- Reference related issues
- Ensure CI passes

### Security

- Never commit API keys or secrets
- Follow security guidelines in [AGENTS.md](./AGENTS.md)
- Report security issues privately

## License

This project is licensed under the terms specified in [LICENSE](./LICENSE).

For architecture and runtime details, see [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md).

For Codex OSS-inspired coding-tool conventions, see [AGENTS.md](./AGENTS.md) and
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md).