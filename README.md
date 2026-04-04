# Rumi AI

Rumi AI is a modular AI runtime and tooling workspace.

The repository keeps the runtime implementation under `rumi_ai_1_10/`, while `rumi_ai/` provides a version-stable Python entrypoint.

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

## Development

```bash
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

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
