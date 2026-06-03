# Contributing to Rumi AI

Thanks for taking a look at Rumi AI. The project is most useful when changes are small, reviewable, and respectful of the runtime's local-first security model.

## Good First Contributions

- Improve setup docs after trying the quickstart on a fresh machine.
- Add or simplify examples under `rumi_ai_1_10/docs/examples/`.
- Write focused tests for a single runtime, pack, viewer, or mobile behavior.
- Improve diagnostics, error messages, and recovery notes.
- Add issue reproductions with exact commands, OS, Python/Node/Rust versions, and logs.

## Development Setup

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10
```

For frontend work:

```bash
cd rumi_ai_1_10/ecosystem/defaultspack/webapp
npm ci
npm test
npm run lint
npm run build
```

For desktop viewer work:

```bash
cd rumi_viewer/src-tauri
cargo test
```

## Pull Request Guidelines

- Keep changes scoped to one runtime, pack, viewer, mobile, or docs concern.
- Include focused validation in the PR body.
- Do not bypass approval, workspace jail, local guard, capability trust, audit, or secret-handling paths.
- Treat browser, computer, terminal, git, file-write, and integration behavior as security-sensitive.
- Prefer tests that describe the contract being protected.

## Issue Guidelines

When reporting a bug, include:

- What you expected to happen.
- What happened instead.
- Exact commands or UI steps.
- OS and runtime versions.
- Relevant logs or screenshots, with secrets removed.

Please avoid posting API keys, tokens, private prompts, personal data, or proprietary code in public issues.
