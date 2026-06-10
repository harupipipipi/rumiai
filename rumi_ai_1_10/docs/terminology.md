<!-- docs-i18n-links:start -->
[EN](./terminology.md) | [JP](./i18n/ja/terminology.md) | [KR](./i18n/ko/terminology.md) | [CN](./i18n/zh-cn/terminology.md)
<!-- docs-i18n-links:end -->

# Terminology

This document defines the preferred user-facing vocabulary for Rumi.

Use these terms consistently in docs, UI copy, and examples. Lower-level runtime
and API names may still use legacy or transport-oriented identifiers where
compatibility matters.

## Preferred Terms

| Term | Use it for | Notes |
|---|---|---|
| `rule` | Always-loaded instruction that applies by default within a scope | This is the main product term for baseline behavior. |
| `skill` | Triggered or on-demand instruction/workflow bundle | Use for focused capability bundles that activate when relevant. |
| `prompt` | Raw model input text assembled at execution time | Treat this as a runtime artifact, not the main user-facing concept. |
| `system prompt` | The low-level system-role prompt payload sent to a model API | Prefer `rule` or `skill` in user-facing explanations unless the transport layer itself is the topic. |
| `team workspace` | One user-facing workspace where multiple agents coordinate | Prefer this over `company workspace` in new docs and UI copy. |
| `team` | A cooperating set of agents | Use when describing the group, not the storage or routing layer. |
| `agent` | A tool-capable runtime actor | This remains the general execution unit. |
| `specialist` | A narrowly scoped agent definition or role | Prefer this over `subagent` when naming reusable worker roles. |
| `delegation` | The act of sending bounded work to another agent | Maps to the canonical `agent.delegate` runtime behavior. |
| `tool` | An external action or integration an agent can call | Keep this meaning narrow and concrete. |
| `pack` | A shipped runtime/package unit that provides code, assets, routes, prompts, tools, or skills | Keep this separate from instruction-layer terms such as `rule`. |

## Compatibility Terms

| Compatibility term | Preferred term | How to talk about it |
|---|---|---|
| `company` / `company workspace` | `team` / `team workspace` | Keep `company` only where runtime APIs, stored identifiers, or legacy docs still use it. |
| `subagent` | `specialist` or `delegated agent` | Keep `subagent` as a compatibility alias for older routes, tools, and docs. |
| `system prompt` as a product concept | `rule` / `skill` | Use `system prompt` only when discussing model transport or provider APIs. |

## Important Disambiguation: `rule` vs `pack_type: "rule"`

Rumi currently has two different uses of the word `rule`.

1. Instruction-layer `rule`
   Use this when you mean an always-loaded instruction for agent behavior.
2. Packaging/runtime `pack_type: "rule"`
   Use this only when you mean an internal pack classification or manifest/runtime concept.

These are related only by name. A packaging/runtime `rule` is not automatically
the same thing as an instruction-layer `rule`, and docs should say which layer is
being discussed whenever ambiguity is possible.

## Writing Guidance

- Prefer `rule = always on`.
- Prefer `skill = triggered or on demand`.
- Prefer `team workspace` for the long-running multi-agent surface.
- Prefer `delegation` for the runtime action and `specialist` for the worker role.
- Reserve `prompt` and `system prompt` for implementation, runtime, or API details.
