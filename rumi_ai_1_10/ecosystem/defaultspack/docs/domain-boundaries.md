# Defaultspack domain boundaries

Defaultspack has two different kinds of public contract. Pack contracts are the
runtime-facing manifests and data formats that another pack may consume. Domain
contracts are Python modules that one defaultspack domain may import from
another. Neither contract makes the rest of the owning package public.

## Pack contracts

Packs integrate through declared runtime surfaces: `ecosystem.json` handlers,
functions, capabilities, ports, schemas, and pack-owned data catalogs. A pack
must not import another pack's `domain/`, `backend/`, or handler implementation
as a Python library. Calls through the runtime preserve pack identity, grants,
approval checks, workspace restrictions, and audit behavior; a direct Python
import does not establish those properties.

Changing an implementation module is therefore internal. Changing a declared
manifest, function payload, capability schema, port, or catalog consumed by
other packs is a public-contract change and needs compatibility handling.

## Domain contracts

`domain_boundaries.yaml` is the machine-readable dependency policy for Python
under `defaultspack/domain/`:

- `may_import` permits a source domain to import the named target domain. This
  is retained for edges that have not yet been narrowed.
- `public_imports` permits only the exact module paths listed. It is the
  preferred form for stable interfaces, schemas, and catalogs.
- `exceptions` are file-specific migration debt. Each exception must stay
  narrow and state why the normal dependency direction cannot yet be used.

A `public_imports` entry is exact. Allowing `domain/chat/ir_blocks` does not
allow `domain/chat/store`, `domain/chat`, or a package-import shortcut such as
`from domain import chat`. Add a public module only when its types or behavior
form a genuine cross-domain contract. Convenience access to another domain's
internals is not a reason to widen the policy.

The CI boundary scanner parses absolute and relative imports and fails when a
new edge is absent from the policy or bypasses a public-only edge. It does not
replace runtime authorization: approval, capability trust, local guards, and
audit enforcement remain at their existing execution boundaries.

## Intentional target map

The target is a directed, layered graph, not a frozen copy of today's imports.
Existing broad edges are migrated incrementally without changing pack APIs or
runtime behavior.

| Domain | Owns | Target dependencies and public surface |
| --- | --- | --- |
| `chat` | conversation state, chat IR, run orchestration | May orchestrate `ai_client`, `tool`, prompt/context, and capability queries. Other domains consume explicit chat IR/schema modules; stores and run orchestration are not general-purpose APIs. |
| `tool` | tool protocol, registry, eligibility, execution | May consume approval/policy and host adapters. Its dependency on chat is limited to tool-result IR and tool-selection schema contracts; it must not reach chat stores or run orchestration. |
| `ai_client` | model routing, provider compilation, provider calls | Consumes chat IR conversion contracts and the provider-neutral tool adapter. It may use chat storage only for the currently declared trace contract; provider quirks remain below `provider_compiler/`, not in callers. |
| `capability` | read-only capability catalog | `catalog.py` is its public metadata contract. It does not import chat, tool, AI-client, or UI orchestration. |
| `capabilities` | runtime capability snapshot | Remains independent and authority-neutral; consumers read its snapshot contract rather than adding reverse imports. |
| `frontend` | backend composition for control-panel surfaces | May read domain public catalogs/services, but domain logic must not import frontend. UI composition does not grant execution authority. |
| `ui_surfaces` | declarative surface definitions | Remains dependency-free. It is data/contract vocabulary, not a route into frontend implementation. |
| `agent`, `function_runtime`, `input` | application orchestration | May coordinate lower-level contracts. Lower-level domains must not import these orchestrators to reuse workflow behavior. |
| `tool_policy`, `host_bridge`, `safety` | policy and enforcement support | Dependencies stay narrow; imports must never bypass approval, local guard, capability trust, or audit paths. |

The first enforced narrow edges are `ai_client -> chat`, `tool -> chat`, and
the `chat`/`frontend -> capability` catalog reads. Future tightening should
replace a broad `may_import` edge with exact `public_imports` as soon as its
real cross-domain contract is understood; it should not simply enumerate every
internal module that happens to be imported today.

Run the policy locally with:

```sh
python scripts/quality/scan_defaultspack_boundaries.py
python -m pytest tests/test_defaultspack_boundary_scan.py -q
```
