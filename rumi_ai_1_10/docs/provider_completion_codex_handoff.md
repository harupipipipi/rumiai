# Provider and coding-agent completion handoff for Codex

Target branch: `soon`

Tracking issues:

- #1032 — complete provider/model coverage
- #1033 — unified runtime model catalog
- #1055 — canonical IDs and duplicate-source cleanup
- #1056 — coverage/drift reports
- #1061 — generic ACP coding-agent backend
- #1063 — Kiro CLI backend

## Important classification rule

Do not put every product that uses an LLM into `llm_provider`.

| Integration kind | Examples | Canonical rumiai category |
|---|---|---|
| Raw model API | OpenAI, Anthropic, Gemini, Groq, Bedrock | `llm_provider` plus model inventory |
| Local model runtime | LM Studio, Ollama, vLLM, llama.cpp | dedicated `llm_provider` with runtime-native discovery |
| Model gateway | OpenRouter, Vercel AI Gateway | scoped `llm_provider` inventory |
| Coding agent | Kiro CLI, Codex CLI, Cursor, Copilot, Gemini CLI, Claude Agent, Cline, OpenCode | `coding_backends` through ACP/native agent protocol |
| Meta/orchestration route | Rumi, multi-model review/fusion | meta-provider or model pack, never a remote vendor inventory |

Kiro is a coding agent. Its selected models are account-scoped agent configuration options, not direct foundation-model API routes.

## This PR's scope

This PR intentionally implements only the read-only Kiro foundation:

1. a `coding_backends/kiro-cli` component manifest;
2. a safe `kiro-cli` installation/auth/model probe;
3. normalization of `kiro-cli chat --list-models --format json` output;
4. a least-privilege headless command planner that never adds `--trust-all-tools`;
5. tests proving Kiro is not added to the LLM provider catalog.

It does **not** yet execute prompts or advertise ACP session support. The manifest keeps `coding_session=false` and `acp=false` until #1061/#1063 are implemented and tested.

## Next PR 1: shared ACP client (#1061)

Create a reusable ACP client rather than a Kiro-only JSON-RPC loop.

Suggested files:

```text
ecosystem/defaultspack/domain/acp/__init__.py
ecosystem/defaultspack/domain/acp/client.py
ecosystem/defaultspack/domain/acp/stdio_transport.py
ecosystem/defaultspack/domain/acp/session.py
ecosystem/defaultspack/domain/acp/permissions.py
```

Required behavior:

- spawn a structured command/argv without `shell=True`;
- newline-delimited JSON-RPC 2.0 over stdio;
- route concurrent request/response IDs correctly;
- handle agent-to-client filesystem and terminal requests;
- implement `initialize`, authentication negotiation, `session/new`, load/resume/list/close/delete, prompt, cancel, mode/config changes;
- consume streamed message, plan, diff, tool-call and permission updates;
- expose unknown extension messages as diagnostics rather than crashing;
- redact secrets from stderr and protocol logs;
- terminate child processes predictably on cancellation or app shutdown.

Do not reuse private MCP transport classes directly. Extract a small shared JSON-RPC stdio transport if that can be done without changing MCP behavior, or implement an ACP-specific transport with equivalent tests.

### Authority boundary

ACP filesystem and terminal methods are requests from an external agent. They must call rumiai's workspace/sandbox/Authority services.

- reads must remain in approved roots;
- writes, patches and deletes require the corresponding permission;
- terminal commands require explicit permission and a structured argv;
- network, git commit/push and credential use require separate permissions;
- a request field saying `approved=true` is never proof of approval;
- permission responses sent back to the agent must reflect the server-side Authority decision.

## Next PR 2: complete Kiro ACP backend (#1063)

Build on the shared ACP client.

1. Start `kiro-cli acp` or `kiro-cli acp --agent <name>`.
2. Initialize only capabilities implemented by rumiai.
3. Create/load a session for the selected workspace.
4. Map Kiro session IDs to rumiai coding-session records.
5. Stream agent messages, tool calls and turn completion into the existing activity/event model.
6. Map Kiro's advertised session model/config options to backend-scoped selectors.
7. Support model and effort changes only when advertised.
8. Preserve `_kiro.dev/*` messages as optional extensions; ignore unknown extensions safely.
9. Add explicit login/device-flow actions; never run login during a background probe.
10. Add headless execution only for explicit automation and derive a minimal `--trust-tools` set from Authority policy.

### Kiro discovery commands

Read-only probes:

```bash
kiro-cli --version
kiro-cli whoami --format json
kiro-cli doctor --all --format json
kiro-cli agent list
kiro-cli chat --list-models --format json
```

Do not read Kiro token files directly. Do not hardcode the public website's model table. The CLI result is scoped by account, plan, region and administrator policy.

## Settings and UX follow-up

Add a `Coding agents` section separate from `Models/API providers`.

For each backend show:

- installed and executable path;
- version;
- authentication/account state;
- current plan or governance restrictions when safely available;
- model/config selectors;
- session capabilities;
- required permissions;
- read-only refresh;
- explicit login/logout/install actions.

If coding-agent routes appear in a model-like selector, group them under `Coding agent routes` and show the backend/account. Never present them as direct API models.

## Additional coding-agent coverage

After Kiro, use the generic ACP backend for at least:

- Codex CLI / ACP adapter
- Gemini CLI
- Claude Agent adapter
- GitHub Copilot ACP
- Cursor ACP
- Cline
- OpenCode
- Kimi CLI
- Qwen Code
- Mistral Vibe
- Goose
- OpenHands
- Augment/Auggie CLI
- Junie
- Factory Droid
- Devin CLI
- Grok Build

The ACP Registry can provide install metadata, but registry entries are untrusted until source/signature policy is checked. Refreshing the registry must never install or execute an agent.

## Validation commands

Run at minimum:

```bash
cd rumi_ai_1_10
pytest -q tests/test_defaultspack_kiro_cli_backend.py
pytest -q tests/test_defaultspack_codex_app_server_backend.py
pytest -q tests/test_defaultspack_provider_components.py
```

After ACP transport is added, include process fixtures that act as fake agents and cover:

- initialization and protocol-version mismatch;
- interleaved notifications and responses;
- file/terminal permission requests;
- model/config changes;
- cancellation and child-process exit;
- malformed JSON and stderr redaction;
- multiple workspaces and process isolation.

## Completion rule

A backend is complete only when its runtime-advertised models/config options are fully represented after refresh and its session actions are governed by Authority. A logo, one sample model, or an untested subprocess command is not provider support; it is decorative YAML with ambitions.
