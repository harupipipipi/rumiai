# Handoff: defaultspack Function/Flow Runtime

This handoff is self-contained. Assume the next engineer only knows the
repository name, `rumiai`, and has not read the prior conversation.

## Repository And Branch

- Repository: `rumiai`
- Local workspace used for this checkpoint:
  `/Users/haru/Desktop/puroguramukei/rumi_ai_mac`
- Main package directory: `tobkiri_runtime`
- Branch: `codex/defaultspack-function-flow`
- Remote: `origin` at `https://github.com/harupipipipi/rumiai.git`
- Checkpoint commit before this handoff file:
  `776178f2 WIP: canonicalize defaultspack function flow runtime`

Continue work on the same branch and put all remaining work into one PR.
Do not split this into multiple PRs unless the user explicitly changes scope.

## User Goal

The user wants `defaultspack` to become the canonical runtime and wants the
implementation to match these architecture rules:

- `defaultspack` is canonical runtime.
- `defaults` remains only as a thin compatibility shim.
- Tools are implemented as function/capability facades.
- Tool safety must not depend on `write_action: true`.
- Untrusted user/pack code must run inside Docker isolation.
- Host access, network access, file editing, terminal, git, browser, and
  computer control must go through trusted default functions/capability grants.
- Normal chat input should go through declarative YAML flow plus a Python flow
  engine.
- Flow is orchestration only; real logic belongs in functions.
- Prompt is passive context, not executable tool logic.
- AI providers should be manifest-first, with OpenAI-compatible providers
  addable by manifest/model definitions where possible.
- Frontend HTTP/SSE/widget contracts should remain compatible while backend
  internals move to route registry + flow/function.

The final desired outcome is one PR that fully implements and verifies this
direction.

## Architecture Decisions To Preserve

- Canonical runtime: `ecosystem/defaultspack`.
- Legacy compatibility: `ecosystem/defaults` delegates to `defaultspack`.
- Flow implementation: YAML declarations plus Python engine.
- Allowed authorable tool execution types:
  - `rumi_function`
  - `capability`
  - `mcp`
- Legacy execution types such as `local`, `handler`, `dynamic`, and `prompt`
  are not authorable for untrusted tools. Existing first-party compatibility
  paths may remain temporarily but should fail closed for untrusted tools.
- Capability taxonomy currently used:
  - `file.read`
  - `file.write`
  - `terminal.exec`
  - `git.read`
  - `git.write`
  - `network.read`
  - `network.send`
  - `browser.control`
  - `computer.control`
- `write_action` is metadata only. Permission and risk decisions must come
  from risk class, approval policy, execution type, trusted pack identity, and
  capability grants.
- Strict Docker policy should reject host fallback if Docker is unavailable.

## What Is Already Implemented In The Checkpoint

### Tool Security And Functionization

- Added `ecosystem/defaultspack/domain/tool/security.py`.
- Updated `ecosystem/defaultspack/domain/tool/registry.py` to normalize risk,
  reject unsupported untrusted legacy execution types, expose capability
  grants, and preserve UI/extension compatibility where the tool is visible
  but still unexecutable by security policy.
- Updated `ecosystem/defaultspack/domain/tool/executor.py` to enforce
  function/capability-first execution and reject unsupported untrusted paths.
- Migrated `ecosystem/rumi_default_tools_pack/tools/*/manifest.json` toward
  function/capability facade metadata, including coding/file/git/terminal and
  network/browser/computer tools.
- Added tests in `tests/test_defaultspack_tool_security.py`.

### Docker / Capability Boundary

- Updated `core_runtime/capability_executor.py` so strict Docker policy denies
  host fallback when Docker is unavailable.
- Added tests in `tests/test_capability_executor_security.py`.

### Flow Runtime And Chat Ingress

- Expanded `ecosystem/defaultspack/domain/flow/engine.py`.
- Added declarative validation and execution support for:
  - `function`
  - `subflow`
  - `branch`
  - `parallel`
- Updated `ecosystem/defaultspack/flows/chat_turn.flow.yaml` as canonical
  normal chat ingress.
- Added `ecosystem/defaultspack/flows/chat_stream_turn.flow.yaml`.
- Updated tests in `tests/test_defaultspack_chat_turn_flow_contract.py`.

### Chat Persistence

- Updated `ecosystem/defaultspack/blocks/chat/persist_turn.py` so persistence
  goes through canonical `ChatStore` semantics rather than being only a JSONL
  append path.
- JSONL-style audit should remain separate from canonical message persistence.

### Transport / Route Registry

- Updated `ecosystem/defaultspack/transport/registry.py` to describe routes
  through flow/function specs.
- Updated `ecosystem/defaultspack/transport/http.py`, `cli.py`, and `stdio.py`
  to route normal chat through canonical flow/function paths while preserving
  public contracts where possible.
- Converted `ecosystem/defaults/transport/{http,cli,stdio,uds}.py` into thin
  compatibility shims.
- Added/updated route tests in:
  - `tests/test_defaultspack_route_integration.py`
  - `tests/test_defaults_mcp_transport.py`

### Prompt

- Added `ecosystem/defaultspack/domain/prompt/effective.py`.
- Updated prompt loading/resolution so effective prompt returns source chain
  and resolved content.
- Added dispatcher entries for:
  - `prompt_validate_template`
  - `prompt_resolve_for_conversation`
- Disabled prompt-to-tool authoring as executable prompt logic.
- Updated prompt template/unified conversion to generate passive/function
  facade metadata instead of executable `execution.type = prompt`.
- Added tests:
  - `tests/test_defaultspack_prompt_effective.py`
  - `tests/test_defaultspack_prompt_passive.py`

### AI Client / Provider

- Added/updated `ecosystem/defaultspack/domain/ai_client/gateway.py`.
- Moved chat/AI blocks toward `LLMGateway` instead of direct `AIClient`
  orchestration, while preserving legacy monkeypatch compatibility in
  `blocks/chat/send.py` through gateway-level re-export.
- Updated `ecosystem/defaultspack/domain/ai_client/providers/__init__.py` for
  manifest-first OpenAI-compatible provider metadata.
- Added `tests/test_defaultspack_provider_manifest_first.py`.

### Browser / Computer Stability

- Updated
  `ecosystem/rumi_default_tools_pack/domain/tool/browser_computer.py` to avoid
  custom test artifact roots reusing stale shared selected-window state from
  `browser_sessions.json`.
- This fixed the browser/computer state-sensitive failures seen during a full
  pytest run.

### Documentation

Updated documentation around:

- flow spec
- prompt authoring
- provider authoring
- tool authoring
- transport
- AI providers/client
- prompt/tool conversion

Important docs changed include:

- `docs/flow_spec.md`
- `docs/prompt_authoring.md`
- `docs/provider_authoring.md`
- `ecosystem/defaultspack/docs/ai_client.md`
- `ecosystem/defaultspack/docs/prompt.md`
- `ecosystem/defaultspack/docs/tool-prompt-conversion.md`
- `ecosystem/defaultspack/docs/transport.md`
- `ecosystem/defaultspack/docs/writing-tools.md`

## Verification Already Run

These passed before the checkpoint commit:

```bash
cd tobkiri_runtime
python -m pytest tests/test_defaultspack_chat_turn_flow_contract.py \
  tests/test_defaultspack_route_integration.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_tool_security.py -q
```

Result: 42 passed.

```bash
cd tobkiri_runtime
python -m pytest tests/test_*flow*.py tests/test_*route*.py \
  tests/test_defaults_mcp_transport.py \
  tests/test_defaultspack_tool_security.py \
  tests/test_defaultspack_tool_policy.py \
  tests/test_defaultspack_tool_components.py \
  tests/test_defaultspack_tool_executor_rumi_function.py \
  tests/test_defaultspack_external_send_tool.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_prompt_components.py \
  tests/test_defaultspack_provider_expansion.py \
  tests/test_defaultspack_provider_foundation.py \
  tests/test_defaultspack_backend_foundation.py \
  tests/test_capability_executor_security.py -q
```

Result: 403 passed, 1 existing warning.

```bash
cd tobkiri_runtime
python -m pytest tests/test_defaultspack_agent_service_plan.py -q
```

Result: 182 passed.

```bash
cd tobkiri_runtime
python -m pytest tests/test_browser_computer_seat_delegation.py \
  tests/test_computer_desktop_action_delegation.py \
  tests/test_computer_move_drag_delegation.py \
  tests/test_defaultspack_agent_service_plan.py::test_computer_click_physical_true_operates_visible_action -q
```

Result after browser/computer state fix: 18 passed.

```bash
git diff --check
```

Result: passed.

## Full Test Status

Full test command:

```bash
cd tobkiri_runtime
python -m pytest -q
```

What happened:

1. A full run before the browser/computer state fix reached:
   `4373 passed, 19 skipped, 7 failed`.
2. All 7 failures were browser/computer physical action delegation tests where
   stale selected-window state made actions return `executed=False`.
3. The state fix was added and the relevant 18-test subset passed.
4. A new full run was started and had passed the previously failing
   browser/computer section, but the user asked to move environments, so it was
   intentionally stopped before completion.

Next engineer must run the full test suite again from a clean process.

## Immediate Next Steps

1. Fetch and checkout the branch:

```bash
git fetch origin
git checkout codex/defaultspack-function-flow
cd tobkiri_runtime
```

2. Run full tests:

```bash
python -m pytest -q
```

3. If failures appear, fix them without reverting the checkpoint architecture.

4. Re-run focused tests around the touched area, then run full tests again.

5. Inspect for design regressions:

```bash
rg -n 'execution\\.type.*prompt|"type": "prompt"|type: prompt|execution.*dynamic|execution.*handler' \
  ecosystem/defaultspack docs ecosystem/rumi_default_tools_pack
```

Treat legitimate prompt component metadata separately; executable prompt tools
should not return as an authoring path.

6. Inspect direct AI client imports:

```bash
rg -n 'from domain\\.ai_client\\.client import AIClient|from ecosystem\\.defaultspack\\.domain\\.ai_client\\.client import AIClient' \
  ecosystem/defaultspack/blocks ecosystem/defaultspack/domain
```

Only allowed legacy/import compatibility locations should remain.

7. When complete, create one PR from `codex/defaultspack-function-flow` into
   `master`.

## Acceptance Criteria For The Final PR

- Full `python -m pytest -q` passes or any remaining failures are clearly
  unrelated and documented.
- Normal chat flows through `defaultspack.chat_turn`.
- Streaming chat flows through `defaultspack.chat_stream_turn` or equivalent
  route-registry function/flow path.
- Existing frontend HTTP paths, JSON shapes, SSE event names, and widget
  shapes stay compatible.
- `defaults` still works as a compatibility shim.
- Untrusted legacy execution types are not authorable/executable.
- Function/capability tool manifests expose risk, approval, and grants.
- Host/network/file/git/browser/computer access goes through trusted default
  functions/capabilities.
- Prompt remains passive; no executable prompt tool authoring path is restored.
- Manifest-only OpenAI-compatible provider addition remains covered.
- Docs match runtime behavior.

## Cautions

- Do not revert the large `defaults` transport shim changes unless replacing
  them with an equivalent route-registry delegation.
- Do not reintroduce `execution.type = prompt` as an executable tool path.
- Do not rely on `write_action` as the permission decision. It is metadata.
- Do not make Docker strict mode silently fall back to host execution.
- Be careful with browser/computer tests on macOS. Shared
  `browser_sessions.json` can retain selected window state between tests.
- Keep this as one PR unless the user explicitly asks to split it.
