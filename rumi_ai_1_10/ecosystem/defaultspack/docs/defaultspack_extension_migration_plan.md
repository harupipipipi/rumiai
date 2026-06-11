<!-- docs-i18n-links:start -->
[EN](./defaultspack_extension_migration_plan.md) | [JP](./i18n/ja/defaultspack_extension_migration_plan.md) | [KR](./i18n/ko/defaultspack_extension_migration_plan.md) | [CN](./i18n/zh-cn/defaultspack_extension_migration_plan.md)
<!-- docs-i18n-links:end -->

# defaultspack Extension Migration Plan (PR integrated version)

## Background and purpose

The following centralized implementation remains in defaultspack.

- Central definition of LLM provider/model (`domain/ai_client/providers/__init__.py` and `model_profiles.py`)
- Duplicate management path for prompt / tool / knowledge / transport
- Huge fallback route table for `transport/http.py`

This change is based on **manifest drive + file drop extension** and creates a foundation that allows for phase transition while maintaining compatibility.

## Implementation policy (scope to be completed with this PR)

1. Define extended categories with fixed strings and specify discovery rules for each category.
2. Add manifest validation and extension registry to start moving away from central hardcode.
3. LLM provider/model is loaded with extension manifest priority, leaving existing logic as a compatibility fallback.
4. OpenRouter does not have a static list and handles it with API synchronization + cache + fallback.
5. Prompt / tool / knowledge / transport does not break the existing manager and brings the extension registry side to the primary source.
6. Existing API/call signature (`AIClient.complete(model, messages, tools, params)`) will be maintained.

## Extension category (foundation)

- `llm_provider`
- `llm_model`
- `prompt`
- `tool`
- `chat_mode`
- `agent_mode`
- `knowledge_backend`
- `transport`
- `ui_surface`
- `policy`

## Directory foundation

```text
ecosystem/defaultspack/extensions/
  llm/providers/<provider_id>/manifest.json
  llm/providers/<provider_id>/models/*.json
  prompts/<prompt_id>/manifest.json
  tools/<tool_id>/manifest.json
  chat_modes/<mode_id>/manifest.json
  agent_modes/<mode_id>/manifest.json
  knowledge_backends/<backend_id>/manifest.json
  transports/<transport_id>/manifest.json
  ui/<surface_id>/manifest.json
  policies/<policy_id>/manifest.json
```

## Detailed TODO (with acceptance criteria)

### A. Foundation

- [x] A1: Create working branch
  - Acceptance: Working with `codex/defaultspack-extension-refactor`
- [x] A2: defaultspack Check baseline for major tests
  - Acceptance: phase5 tests are maintained after adding the extension
- [x] A3: Added this migration plan
  - Acceptance: Purpose, scope, category, compatibility policy, and TODO are specified.
- [x] A4: Extension discovery / manifest validation / registry implementation
  - Acceptance: Can detect manifests by category and get validation errors
- [ ] A5: Eliminate duplication of legacy import path and canonical package path.
  - Acceptance: `domain.*` and `ecosystem.defaultspack.*` no longer conflict when loading manifest entrypoint

### B. LLM / Provider migration (maintaining compatibility)

- [ ] B1: Replace `domain.ai_client.providers.__init__` with extension manifest driven
  - Acceptance: Central `_PROVIDER_REGISTRY` Dependency removed.
- [ ] B2: Added OpenAI compatible generic adapter
  - Acceptance: provider can be added just by setting env/base_url in manifest
- [ ] B3: Added OpenRouter provider (dynamic model synchronization)
  - Acceptance: No hardcoded model list, `GET /api/v1/models` Sync + cache + fallback works
- [ ] B4: Migrate default model selection to manifest / model metadata based
  - Acceptance: Does not depend on fixed stale values (e.g. OpenAI is `gpt-5.4`, Anthropic is Claude 4.6 series, Google is Gemini 2.5 series)
- [ ] B5: Move OpenAI / Anthropic / Google's modern catalog to the manifest side
  - Acceptance: default / fast / large / embedding of `ProfileLoader` is determined by registry origin
- [ ] B6: Separate OpenRouter and generic OpenAI-compatible
  - Acceptance: OpenRouter specific synchronization logic and generic endpoint adapter are now implemented separately.

### C. Prompt / Tool / Knowledge / Transport Connection

- [ ] C1: Connect prompt registry to PromptManager
  - Accepted: extension prompt can list/get/render, user_data prompt editing continues
- [ ] C2: Connect tool registry to ToolRegistry
  - Acceptance: built-in tool is loaded at manifest origin, dynamic tool CRUD continues
- [ ] C3: Connect knowledge backend manifest to backend registry
  - Acceptance: backend can be generated from entrypoint
- [ ] C4: Make chat_mode / agent_mode runner entrypoint resolvable
  - Accept: mode manifest becomes the starting point for runner calls
- [ ] C5: Export fallback route table in transport/http.py
  - Acceptance: Route definitions move closer to transport registry module, `http.py` becomes dispatcher-centric
- [ ] C6: Complete the manifest template for prompt / tool / chat_mode / agent_mode / knowledge_backend / transport / ui / policy
  - Acceptance: All categories appear in discovery results

### D. Test

- [ ] D1: manifest validation test
  - Acceptance: Detects missing required items and mismatched categories
- [ ] D2: extension discovery test
  - Accept: All categories are detected
- [ ] D3: provider/model loading test
  - Acceptance: manifest-driven provider detection/model priority resolution works
- [ ] D4: OpenRouter sync/cache test
  - Acceptance: Cache update on API success, cache fallback on API failure
- [ ] D5: PromptManager / ToolRegistry extension connection test
  - Acceptance: prompt/tool from extension is visible from existing API
- [ ] D6: transport route registration test
  - Acceptance: fallback route definition is built from registry module
- [ ] D7: legacy shim removal test
  - Acceptance: Compatible import of `prompt.prompt_loader` / `tool.tool_loader` is not possible.

## Compatibility policy

- Maintain API surface (`AIClient` call signature unchanged).
- If extension is not placed, fall back to the existing behavior with fail-soft.
- The fallback route table of `transport/http.py` will be left for compatible purposes, but the definition itself will be moved to the registry module side.
- top-level `prompt.*` / `tool.*` legacy shims have been removed; use defaultspack registries and functions.

## Assumptions and assumptions

- `ecosystem/defaultspack` is targeted for refactor, `ecosystem/defaults` is not targeted for this PR.
- OpenRouter model acquisition uses the `/models` endpoint as the primary source, and uses the local cache when the network is unavailable.
- Adding a provider should be done by "adding manifest + specifying adapter if necessary".

## Current Status

- discovery / registry / basic manifests added
- During provider migration, it is necessary to normalize the package import path and organize the model metadata destination.
- The templates for prompt / tool / transport have been added, but the connection to the existing manager / route table is not completed.
- In environments with setup pack selection, backend/frontend extension discovery is
  Narrowed down to `defaultspack` and selected target pack. In a development environment without selection
  Load all sibling packs for compatibility
- The Copilot change included removing a compatibility shim, so this PR will bring back the shim to prioritize compatibility.
## Local-first completion status

This PR fixes the local-first runtime baseline without moving Cloudflare,
Supabase, login, account creation, or user management into defaultspack scope.

Completed in this slice:

- canonical implementation is `rumi_ai_1_10/ecosystem/defaultspack/`;
- old `defaults.*` compatibility should delegate to defaultspack behavior rather
  than becoming a second source of truth;
- `stub/default` is the guaranteed no-key model default;
- cloud provider auto-registration is opt-in through
  `RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS`;
- local providers are treated as no-key providers in backend and frontend
  catalogs;
- sensitive coding HTTP routes pass the local guard;
- write/delete/patch/restore, terminal medium/high-risk execution, git commit,
  and git push require signed one-time approval tokens;
- approval tokens are bound to operation and argument hash;
- local action attempts and outcomes are written to a redacted JSONL audit log;
- frontend model fallback and optional operations-company calls are catalog
  driven;
- `scripts/quality/scan_defaultspack_integrity.py --strict` checks route/block
  parity, frontend/backend route parity, local-first defaults, sensitive route
  guard wiring, and syntax for the new safety modules.

Remaining extension work should stay manifest-driven and should avoid adding
cloud defaults back into the fresh local runtime.
