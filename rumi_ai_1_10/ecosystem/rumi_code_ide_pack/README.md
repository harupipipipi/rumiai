# Rumi Code IDE Pack

`rumi_code_ide_pack` is an optional ecosystem pack for advanced code, CLI, and IDE workflows. It is inspired by modern coding agents such as Claude Code, Gemini CLI, Cline, Codex, and local-first assistants, but it does not copy their runtimes or replace Rumi's default coding tools.

## What It Provides

- Coding-focused runtime profiles for CLI, IDE pairing, and terminal review sessions.
- System prompts for scoped repository editing, command-recipe execution, and review-first workflows.
- Presets that tune existing defaultspack graphs toward patch loops, discovery-heavy CLI sessions, and local-first pair programming.
- Declarative command recipes for common repository tasks such as orientation, bug fixing, tests, refactors, and PR prep.
- Tool scope metadata that describes allowed, approval-gated, and excluded tool families.
- Overlap and conflict notes for `defaultspack`, `rumi_default_tools_pack`, and `rumi_local_agent_pack`.

## What It Does Not Provide

- No new runtime handlers, routes, stores, or executable tools.
- No replacement for defaultspack's basic file, terminal, git, prompt, memory, or graph primitives.
- No secrets, credentials, API keys, remote tokens, or provider configuration.
- No automatic destructive command execution policy.

## Docs

Start with [docs/README.md](docs/README.md), then read [docs/architecture.md](docs/architecture.md), [docs/interfaces.md](docs/interfaces.md), and [docs/operations.md](docs/operations.md).
