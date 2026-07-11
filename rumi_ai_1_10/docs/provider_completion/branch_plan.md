# Provider Completion Branch Plan

Target: `soon`  
Program issue: #1171

## Active and completed work

| Branch / PR | Scope | Action |
|---|---|---|
| PR #1077 / `agent/lmstudio-native-model-discovery` | LM Studio native inventory | Merged; retain regression coverage and remove remaining stale fallback claims |
| PR #1155 / `agent/provider-routing-complete-v2` | OpenRouter, Vercel, Settings, `/provider`, gateway `/fast` | Repair current CI and complete before merge |
| `agent/ollama-native-model-discovery-v2` | Early Ollama implementation | Stale; do not merge wholesale |
| `agent/provider-routing-complete` | Early gateway implementation | Stale; do not merge wholesale |

## Required PR sequence

### 1. Gateway routing and catalog

```text
branch: agent/provider-routing-complete-v2
PR: #1155
issue: #1139
```

Complete OpenRouter live/LKG catalog, Vercel public/account catalog, dedicated Vercel adapter registration, versioned gateway settings, separate gateway slug namespaces, `/provider`, gateway-native `/fast`, full template preservation, no-network tests and all required CI.

### 2. Direct-provider performance

```text
branch: agent/provider-performance-v3
base: latest soon after #1155
issue: #1171 child or #1139 follow-up
```

Complete the central success timing hook, provider-reported output-token usage, TTFT, generation TPS, EWMA and recent median, endpoint/account isolation, direct-provider `/fast`, privacy tests and Windows concurrency tests.

### 3. Ollama

```text
branch: agent/ollama-native-model-discovery-v3
base: latest soon
issue: #1042
```

Port behavior, not stale history, from v2: `/api/tags`, `/api/show`, `/api/ps`, digest-keyed detail cache, chat/embedding typing, running/VRAM/context/expiry, zero-model state, no discovery side effects and removal of fixed static defaults.

### 4. vLLM

```text
branch: agent/vllm-served-inventory-v1
issue: #1044
```

Inventory means models served by that endpoint, including aliases and adapters. It does not mean every checkpoint on disk.

### 5. llama.cpp

```text
branch: agent/llamacpp-native-inventory-v1
issue: #1045
```

Support both single-model server and router mode. Load/unload is explicit only.

### 6. Generic OpenAI-compatible connections

```text
branch: agent/openai-compatible-connections-v1
issue: #1046
```

Support configurable list URL/paths/auth/pagination and honest manual inventory when no list API exists.

### 7. Direct hosted providers

```text
branch: agent/provider-catalog-direct-cloud-v1
issues: #1035, #1036, #1048
```

Split into smaller provider-family PRs if the diff becomes large: first-party native APIs, OpenAI-compatible hosted APIs, search-specific providers and embeddings/rerank providers.

### 8. Enterprise control planes

```text
branch: agent/provider-catalog-enterprise-v1
issue: #1049
```

Deployment/project/region identifiers are part of invocation identity. Do not force these providers into a global model-ID-only contract.

### 9. Hosted expansion

```text
branch: agent/provider-catalog-hosted-expansion-v1
issue: #1051
```

Implement task-specific endpoints rather than exposing every model as chat.

### 10. Self-hosted expansion

```text
branch: agent/provider-catalog-selfhosted-expansion-v1
issue: #1053
```

Separate installed, served, loaded and healthy states.

### 11. Gateway expansion

```text
branch: agent/provider-gateway-expansion-v1
issue: #1171 child
```

Add Cloudflare AI Gateway, LiteLLM Proxy, Portkey and Helicone through a shared gateway policy interface where their official contracts support it.

### 12. Task-specific providers

```text
branch: agent/provider-task-specific-v1
issue: #1171 child
```

Add speech and media providers as task providers, not fake chat providers.

### 13. Coverage gate

```text
branch: agent/provider-coverage-gate-v1
issues: #1033, #1055, #1056, #1171
```

Make the matrix and authoritative fixture comparisons required CI.

## Stacked PR policy

A stacked PR is allowed only when a child implementation requires an unmerged parent contract. The PR body must name its temporary base. After the parent merges, rebase onto `origin/soon`, retarget the PR and rerun all checks.

## Branch cleanup

Delete stale branches only after their useful behavior is ported, no open PR references them, new tests cover the port, the issue records the replacement branch and the replacement PR has merged.

## Coding backends

Separate sequence:

```text
agent/codex-app-server-backend   -> #1140
agent/claude-agent-sdk-backend   -> #1141
```

Kiro, Kilo Code, Cursor, Cline and similar agents are not included in LLM-provider completion. They require a later coding-backend/ACP program.
