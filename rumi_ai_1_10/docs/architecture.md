<!-- docs-i18n-links:start -->
[EN](./architecture.md) | [JP](./i18n/ja/architecture.md) | [KR](./i18n/ko/architecture.md) | [CN](./i18n/zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Architecture

This is a document that explains the overall design and mechanism. Also see [pack-development.md](./pack-development.md) for Pack developers and [operations.md](./operations.md) for Operators.

---

## Table of Contents

1. [Design principles](#design-principles)
2. [Flow System](#flow-system)
3. [python_file_call](#python_file_call)
4. [Flow Modifier](#flow-modifier)
5. [Security Model](#security-model)
6. [Pack Approval](#pack-approval)
7. [Network Permissions and Egress Proxy](#network-permissions-and-egress-proxy)
8. [Capability System (Trust + Grant)](#capability-system-trust-grant)
9. [UDS Socket Permissions](#uds-socket-permissions)
10. [Hierarchical authority](#hierarchy-authority)
11. [Secrets](#secrets)
12. [Shared Dict](#shared-dict)
13. [lib system](#lib-system)
14. [Introducing pip dependent library](#pip-dependency-library-installation)
15. [Pack Import / Apply](#pack-import--apply)
16. [Component concept](#component-concept)
17. [vocab / converter](#vocab--converter)
18. [Audit Log](#audit-log)
19. [Pending Export](#pending-export)
20. [DI container and service list](#di-container-and-service-list)
21. [Kernel Mixin configuration](#kernel-mixin-configuration)
22. [Observability](#observability)
23. [Common infrastructure module](#common-base-module)
24. [Pack development tools](#pack-development-tools)
25. [Deprecated feature](#deprecated-feature)

---

## Design principles

### No Favoritism

The official core has no domain concepts (chat, tools, prompts, AI clients, frontends, etc.). What the official provides is a general-purpose execution platform.

Officially provided mechanisms are limited to: Flow execution, authorization gate (hash validation), isolated execution (Docker/UDS), Trust + Grant (capability), and audit logs.

### Malicious Assumption (Threat Model)

Pack Always assume the possibility that the author has malicious intent. Pack execution is generally isolated in Docker `--network=none`. External communication and host privileges are mediated by capability (Trust + Grant) and will not work without explicit permission.

### Fail-Soft

Even if one part breaks, the entire OS will not stop. Failed components are disabled and logged in Diagnostics and Audit to continue.

### Single entry point for host privileges

Dangerous things on the host (external communication, file access, update application, etc.) are not executed directly from Pack, but are mediated by capabilities. It won't move unless you give it permission.

---

## Flow System

### Overview

Flow is a YAML file that defines the connections and execution order between Packs. Each Flow consists of phases and steps.

### Flow file format

```yaml
flow_id: ai_response
inputs:
  user_input: string
  context: object
outputs:
  response: string

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true
  on_missing_step: skip

steps:
  - id: load_context
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"

  - id: call_ai
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_response
```

### Flow source

Flows are loaded in the following order: In the case of the same `flow_id`, the one with higher priority wins (a lower source cannot overwrite the Flow of a higher source).

| Priority | Path | Usage | Approval |
|--------|------|------|------|
| 1 | `flows/` | Official Flow (startup/base) | Not required |
| 2 | `user_data/shared/flows/` | Shared Flow placed by user/external tool | Not required |
| 3 | `ecosystem/<pack_id>/backend/flows/` | Flow provided by Pack | Pack approval required |
| 4 | `ecosystem/flows/` (deprecated) | local_pack compatible Flow | Valid only when `RUMI_LOCAL_PACK_MODE=require_approval`. Approval required |

Override rules: Official Flows cannot be overwritten by anyone. Shared Flows cannot override official ones, but they take precedence over Pack-provided Flows. Pack-provided Flows cannot be overwritten, either official or shared. local_pack has the lowest priority and cannot override any other sources.

### Step type

| type | description |
|------|------|
| `handler` | Call Kernel handler |
| `python_file_call` | Run Python file in Pack |
| `set` | Set value in context |
| `if` | Conditional branching (simplified version) |
| `function` | Execute the function registered in FunctionRegistry (Wave 27) |
| `flow` | Call another Flow as a sub-Flow |

### Execution order

Steps are sorted deterministically in the following order:

1. `phase` (`phases` Sort order in array)
2. `priority` (ascending order; smaller is executed first)
3. `id` (Alphabetical order. Tie-break)

### Variable reference

```yaml
input:
  user_id: "${ctx.user.id}"     # ネスト参照
  settings: "${ctx.config}"      # オブジェクト全体
```

If the reference destination does not exist, it will be treated as `null` (fail-soft).

---

## python_file_call

### Overview

Run a Python file in a Pack as a step in a Flow. A "block" that takes input and returns JSON-compatible output.

### Block file format

```python
# ecosystem/<pack_id>/backend/blocks/my_block.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ
        context: 実行コンテキスト
            - flow_id, step_id, phase, ts
            - owner_pack
            - inputs
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> ProxyResponse

    Returns:
        JSON 互換の出力データ
    """
    return {"message": "Hello from my_block!"}
```

### Path resolution

The `file` field in `python_file_call` is resolved relative to pack_subdir. The following candidates are searched in order:

1. `<pack_subdir>/blocks/`
2. `<pack_subdir>/backend/blocks/`
3. `<pack_subdir>/backend/components/` (compatible)
4. `<pack_subdir>/backend/` (Compatible: Direct installation)
5. `<pack_subdir>/<file>` (Final fallback)

All candidates are restricted within the pack_subdir boundary. Files outside the boundary will be refused execution.

### Security check (before execution)

1. `owner_pack` is approved
2. The hashes of `owner_pack` must match (not modified)
3. The file path must be within the pack_subdir boundary

### Handling of principal_id (v1)

In v1, `principal_id` is always forced to be overwritten by `owner_pack`. Even if you specify `principal_id` in the Flow definition, `owner_pack` will be used at runtime. This is a measure to prevent abuse of authority. A warning is recorded in the audit log as `principal_id_overridden`.

---

## Flow Modifier

### Overview

This is a mechanism that allows you to inject, replace, or delete steps into an existing Flow later. Modifiers allow you to plug in functionality even if the packs don't know each other.

### Modifier file format

```yaml
modifier_id: tool_inject
target_flow_id: ai_response
phase: prepare
priority: 50
action: inject_after
target_step_id: load_context

requires:
  capabilities:
    - tool_support
  interfaces:
    - tool.registry

step:
  id: inject_tools
  type: python_file_call
  owner_pack: capability_provider
  file: blocks/capability_selector.py
  input:
    context: "${ctx.context}"
  output: selected_capabilities
```

### Modifier placement path

The Modifier should be placed below with the file name `*.modifier.yaml`:

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/` (if provided by Pack)

### Action

| action | description | target_step_id | step |
|--------|------|----------------|------|
| `inject_before` | Insert before specified step | Required | Required |
| `inject_after` | Insert after specified step | Required | Required |
| `append` | Added to the end of the phase | Not required | Required |
| `replace` | Replace specified step | Required | Required |
| `remove` | Delete specified step | Required | Not required |

### requires condition

```yaml
requires:
  interfaces:
    - "ai.client"           # InterfaceRegistry に登録されているか
  capabilities:
    - "tool_support"        # capability が有効か
```

If the condition is not met, the modifier is skipped (fail-soft).

### Application order

1. `phase` order
2. `priority` Ascending order
3. `modifier_id` Ascending order

### resolve_target (resolve with shared dictionary)

```yaml
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

If `resolve_target: true` is specified, `target_flow_id` will be resolved in the shared dictionary before being applied.

---

## Security model

### Security mode

Set with the environment variable `RUMI_SECURITY_MODE`.

| Mode | Docker | Behavior |
|--------|--------|------|
| `strict` (default) | Required | Reject execution if Docker is not available |
| `permissive` | Not required | Allow host execution with warning (for development) |

### List of protection mechanisms

| Mechanism | Description |
|------|------|
| Approval Gate | No code in unapproved Packs will be executed |
| Hash verification | Automatic invalidation if file is modified after approval |
| HMAC signature | Grant file tampering detected |
| Path restrictions | Deny file execution outside pack_subdir boundary |
| Docker isolation | `--network=none`, `--cap-drop=ALL`, `--read-only` |
| Egress Proxy (UDS) | Control external communication with pack-specific allowlist |
| UDS group-add | Manage socket permissions with dedicated GID |
| Audit log | Records all operations |
| requirements.lock verification | Supply chain attack prevention |
| pack_identity verification | Preventing mix-ups when updating packs |
| DNS rebinding measures | Internal IP inspection of DNS resolution results |

### Threats and countermeasures

| Threats | Countermeasures |
|------|------|
| Malicious code execution | Authorization required + Docker isolation |
| File Tampering | SHA-256 Hash Verification |
| Settings tampering | HMAC signature |
| Invalid external communication | Egress Proxy + allowlist |
| Privilege Escalation | Explicit Grant by Pack |
| Supply Chain Attack | requirements.lock syntax restriction + wheel-only |
| Pack mix-up | Rejected by pack_identity comparison |
| DNS rebinding | Internal IP inspection of resolution results |

---

## Pack approval

### Approval flow

```
Pack 配置 (ecosystem/<pack_id>/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
ユーザー承認
    ↓
全ファイルの SHA-256 ハッシュを記録
    ↓
初めてコード実行可能に
```

### Approval status

| Status | Code Execution | Description |
|------|-----------|------|
| `installed` | ❌ | Placed, unapproved |
| `pending` | ❌ | Waiting for approval |
| `approved` | ✅ | Approved |
| `running` | ✅ | Approved and Running |
| `modified` | ❌ | Detect file changes after approval |
| `blocked` | ❌ | Rejected |
| `error` | ❌ | Error occurred (failure during approval process, etc.) |

Code execution and network permissions are automatically disabled when a file modification results in a `modified` state. Re-authorization required.

### Pack storage path

Packs can be placed in one of the following paths:

| Path | Type | Description |
|------|------|------|
| `ecosystem/<pack_id>/` | **Recommended** | `paths.py` is the top priority for exploration |
| `ecosystem/packs/<pack_id>/` | Legacy | Ignored if it overlaps with the recommended path |

`discover_pack_locations()` of `paths.py` searches `ecosystem/*` first, and then searches `ecosystem/packs/*` as a compatible route. If the same `pack_id` is present in both, `ecosystem/<pack_id>/` takes precedence.

---

## Network permissions and Egress Proxy

### Design

Packs cannot communicate directly externally (Docker `--network=none`). All external communication passes through the Egress Proxy via UDS sockets.

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部 API
                                        ↓
                                  network grant 確認
                                        ↓
                                    監査ログ記録
```

### UDS-based Pack Identification

A UDS socket is created for each pack, and `pack_id` is determined from the socket path. The `owner_pack` field in the request payload is ignored (security measure).

### Network Grant

```json
{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": ["api.openai.com", "*.anthropic.com"],
  "allowed_ports": [443],
  "granted_at": "2024-01-01T00:00:00Z",
  "granted_by": "user",
  "_hmac_signature": "..."
}
```
Domain matching supports exact matches (`api.openai.com`) and wildcards (`*.anthropic.com`). If you want to allow subdomains, please specify them explicitly using wildcard format.

### Egress Proxy defense mechanism

Internal IP prohibition (localhost / private / link-local / CGNAT / multicast, etc.), DNS rebinding measures (reject if the resolution result is an internal IP), redirect limit (3 hops, recheck grant at each hop), request/response size limit (1MB / 4MB), timeout limit (maximum 120 seconds), header number/size limit, method limit (GET, HEAD, POST, PUT, DELETE, PATCH).

### Wave 12–14 Expansion

#### Rate limit (egress_rate_limiter.py)

Added in Wave 12. Provides request rate limiting with per-pack token buckets. Before the Egress Proxy accepts requests, it inspects the bucket and returns `429` when it is depleted.

#### Domain control (egress_domain_controller.py)

Added in Wave 12. In addition to allowlist , it provides fine-grained control on a per-domain basis (blocklists, wildcard patterns).

#### Fine-grained timeout

Added in Wave 12. Connection timeout and read timeout can now be set for each domain. The old global cap (120 seconds) is maintained as a fallback.

#### Module division (Wave 13)

In Wave 13, we divided the Egress Proxy implementation into the following modules. The order in which security checks are performed is also organized and evaluated in the following order: IP inspection → Protocol inspection → Domain inspection → Rate limiting.

| Module | Responsibilities |
|-----------|------|
| `egress_ip.py` | Internal IP inspection, DNS rebinding measures |
| `egress_protocol.py` | Protocol method header inspection |
| `egress_rate_limiter.py` | Pack unit rate limit |
| `egress_domain_controller.py` | Domain allowlist / blocklist control |

#### Duplicate code removal (W14-FIX)

In Wave 14, we removed redundant code (IP inspection logic, etc.) that remained between modules after splitting, and ensured single responsibility.

---

## Capability System (Trust + Grant)

### Overview

This is a mechanism for approving and putting the capability handler provided by the Pack into production, and granting usage rights (grants) to the principal. Trusts and Grants are managed independently.

- **Trust**: allowlist of `handler_id` + `sha256`. Determine whether the contents of handler.py are trusted
- **Grant**: `principal_id` × `permission_id` grant. Manage who can use which capabilities

### Overall flow

```
候補配置 (ecosystem/<pack_id>/share/capability_handlers/<slug>/)
    ↓
scan（候補検出）
    ↓
pending（承認待ち）
    ↓
approve（Trust 登録 + コピー + Registry reload）
    ↓
Grant 付与（principal × permission）
    ↓
使用可能
```

approve only registers Trust. A separate grant is required for actual use.

### Candidate state transition

| Condition | Description |
|------|------|
| `pending` | Candidates detected and waiting for approval |
| `installed` | Approved. Trust registration + copy completed |
| `rejected` | Rejected. Snooze possible after cooldown (1 hour) |
| `blocked` | Silent block with 3 rejects. Not notified until unblock |
| `failed` | Error occurred during approve process |

### candidate_key

Candidate identity is managed in `candidate_key`:

```
{pack_id}:{slug}:{handler_id}:{sha256}
```

By including sha256, if the contents of handler.py change, it will be treated as a different candidate.

### TOCTOU Measures

Recalculate the sha256 of handler.py at approve time and compare it with the value at scan time. If there is a mismatch, approve will fail.

### Copy and overwrite

At the time of approval, the candidates on the `ecosystem/` side are copied to `user_data/capabilities/handlers/<slug>/`. The ecosystem side remains as a distribution and is not moved. If handler already exists at the copy destination and the handler_id or sha256 is different, an error will occur (automatic overwriting prohibited).

### Module division (Wave 13)

In Wave 13, Capability-related models and loaders have been divided into the following modules.

| Module | Responsibilities |
|-----------|------|
| `capability_models.py` | Capability-related data model definition |
| `flow_modifier_models.py` | Flow Modifier related data model definition |
| `flow_modifier_loader.py` | Modifier file loading/parsing |

### Integration with Function systems (Phase A-D)

In Phases A to D, the old `capability_handler_registry.py` was abolished and integrated into `function_registry.py` (`FunctionRegistry`). All functions (Kernel handler, core_pack function, Pack-provided functions) are registered in `FunctionRegistry`, and `capability_executor.py` executes them uniformly.

#### Major changes

`capability_handler_registry.py` has been removed. Alternatively, `core_runtime/function_registry.py` defines the `FunctionRegistry` and `FunctionEntry` data classes. `ManifestRegistry` is an alias for `FunctionRegistry` (Design Decision D-6).

#### Key fields of FunctionEntry

| Field | Type | Description |
|-----------|-----|------|
| `function_id` | `str` | Function ID |
| `pack_id` | `str` | Affiliation Pack ID |
| `qualified_name` | `str` (properties) | `{pack_id}:{function_id}` (colon separated) |
| `calling_convention` | `Optional[str]` | Execution method. Any of 7 species |
| `permission_id` | `Optional[str]` | Grant ID (used for Grant validation) |
| `entrypoint` | `Optional[str]` | Entry point (e.g. `main.py:run`) |
| `risk` | `Optional[str]` | Risk level |
| `is_builtin` | `bool` | Is it a built-in function? |
| `runtime` | `str` | `python` / `binary` / `command` |
| `handler_py_sha256` | `Optional[str]` | SHA-256 in handler.py (for trust verification) |
| `vocab_aliases` | `Optional[List[str]]` | vocab alias (searchable in `resolve_by_alias()`) |
| `grant_config` | `Optional[Dict]` | Grant settings (perform Grant verification when non-None) |

#### calling_convention (7 types)

| calling_convention | Description |
|-------------------|------|
| `kernel` | Run directly as a Kernel handler. Cannot be executed via `capability_executor` |
| `subprocess` | Execute in subprocess (entrypoint specified) |
| `block` | Run via core_pack's DI service |
| `python_host` | Runs in host Python (requires `RUMI_ALLOW_HOST_EXECUTION=1`) |
| `python_docker` | Runs in a Docker container (default) |
| `binary` | Run binary directly |
| `command` | Execute any command |

#### Kernel functions

`kernel.py` defines `_KERNEL_HANDLER_MANIFESTS`. 70 (System 29 + Runtime 41) handlers are registered in `register_kernel_function()`, `pack_id="kernel"`, `calling_convention="kernel"` and `FunctionRegistry`.

#### Execution flow

```
capability_executor.execute(principal_id, request)
    ↓
FunctionRegistry で permission_id を解決（resolve_by_alias）
    ↓
_unified_execute(entry, principal_id, request)
    ↓
Trust チェック（sha256 検証）
    ↓
Grant チェック（grant_config が非 None のとき）
    ↓
calling_convention で分岐実行
```

---

## UDS socket permissions

### Problem

In strict mode, the Pack execution container runs with `--user=65534:65534` (nobody). If the UDS socket is left at the default `0660` (root:root), the container will not be able to connect to the socket.

### Solution

By setting a dedicated GID, you can securely connect while maintaining `0660`.

| Environment variables | Description | Default |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | Egress socket GID | None |
| `RUMI_CAPABILITY_SOCKET_GID` | Capability Socket GID | None |
| `RUMI_EGRESS_SOCKET_MODE` | Egress socket permissions | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | Capability Socket permissions | `0660` |

If a GID is set, `--group-add=<GID>` will be automatically granted at `docker run`.

This can be mitigated with `RUMI_EGRESS_SOCKET_MODE=0666` / `RUMI_CAPABILITY_SOCKET_MODE=0666`, but is deprecated as it allows arbitrary users to connect to the socket.

---

## Hierarchical permissions

### Overview

By changing `pack_id` to `parent__child`, you can express a Pack with a parent-child relationship. If the child is allowed but the parent is not, execution will be denied.

The parent's config sets an upper limit (intersection) on the child. Even if only the lower level is allowed, it will not work if the higher level does not allow it.

---

## Secrets

Securely manage secret values such as API keys.

- `.env` is not used (accident rate reduction)
- Stored in `user_data/secrets/` (1 key = 1 file, tombstone, journal)
- Do not display any secret values in the log (both auditing and diagnostics)
- Don't show secret files directly to Pack
- Obtained via capability (e.g. `secrets.get`)
- API is only list (with mask) / set / delete (no redisplay)

---

## Shared Dict

### Overview

This is a mechanism that allows you to rewrite any `namespace` / `token`. Officials do not interpret the meaning of namespace (the ecosystem is free to decide it).

### Safety features

- **Cycle detection**: Automatically reject cycles like A→B→A
- **Collision detection**: Attempts to register different values for the same token will be rejected
- **Hop limit**: Abort resolution after default 10 hops
- **Audit log**: records all operations

### Persistence

`snapshot.json` (snapshot) and `journal.jsonl` (journal) are saved in `user_data/settings/shared_dict/`.

---

## lib system

### Overview

Manages pack initialization and update processing. It is not resident and is executed only when needed.

### Execution timing

| Condition | File to be executed |
|------|-------------------|
| First introduction (no record) | `lib/install.py` |
| Change hash | `lib/update.py` (if not `install.py`) |
| No change | Do not run |

### Docker isolation

In strict mode, it runs isolated inside a Docker container. `--network=none`, `--cap-drop=ALL`, `--read-only`, `--memory=256m`. RW mounts are limited to `user_data/packs/{pack_id}/` (in containers: `/data`) only.

---

## pip dependent library installation

### Overview

Packs can declare dependencies on PyPI packages by including `requirements.lock`. Once the user authorizes through the API, it is securely downloaded and installed in the builder's Docker container. The host Python environment is not dirty.

### requirements.lock conventions

Only `NAME==VERSION` lines are allowed (comments/blank lines are allowed). The following are prohibited: `-e` (editable), `git+` / `http://` / `https://` (URL/VCS references), `file:` / `../` / `/` (local references), `--` optional lines, `@` direct references.

### State transition

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### Security

wheel-only is the default (`--only-binary=:all:`). If sdist is required, specify `allow_sdist: true` when approving. The builder container (download) runs in `--network=bridge` + `--cap-drop=ALL`, and the builder container (install) runs in `--network=none` (completely offline). From the execution container, site-packages are mounted read-only (`/pip-packages:ro`) and added to `PYTHONPATH`.

### index_url constraints

`https` Only schemes allowed. Rejected if hostname is localhost / 127.0.0.1 / ::1 / private IP / link-local.

---

## Pack Import / Apply

### Import

Bring the Pack from the folder / `.zip` / `.rumipack` (zip compatible) into staging. Protections such as "requires a single top directory" and zip slip/size restrictions apply to the zip structure.

### Apply

Applies from staging to ecosystem. A backup will be created automatically. When applying, both `pack_id` and `pack_identity` (`pack_identity` field of `ecosystem.json`) are compared, and if there is a mismatch with the existing Pack, it will be rejected.

---

## Component Concept

### Overview

`backend_core/ecosystem/registry.py` reads `pack_subdir/components/*/manifest.json` and builds `ComponentInfo`. Component is a unit for lifecycle management (such as setup).

### Relationship with python_file_call

`python_file_call` does not have the function to treat components specially and automatically search for blocks. If you want to run a file located in `components/{component_id}/blocks/`, specify the relative path in the `file` field.

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

---

## vocab / converter

> **Note**: This feature is an advanced feature for compatibility absorption. There is no need to use it in normal Pack development.

### vocab.txt (synonym group)

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

Words written on the same line are treated as synonyms.

### converters

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

### Converter Security Check

#### Problem

`ConverterASTChecker` performs AST parsing of converter scripts and detects and rejects usage of `blocked_imports` (`os`, `subprocess`, `socket`, etc.). However, the current check only targets converter files. If the converter imports a local module like `from .helper import func` or `import local_module`, it will not be able to detect blocked imports even if the imported file contains blocked imports.

```
converter.py          ← 検査される（Level 0）
 └─ import helper     ← helper.py は検査されない
     └─ import os     ← blocked import が素通り
```

#### Inspection level definition

| Level | Inspection scope | Advantages | Disadvantages | Implementation cost |
|--------|---------|----------|-----------|-----------|
| Level 0 (currently) | Single converter file | Implemented, fast, no side effects | Blocked imports can be bypassed via local imports | None |
| Level 1 (recommended) | converter + recursive traversal of `.py` in the same directory | Prevents the most common bypass patterns. Simple implementation | Dependencies outside the same directory are not checked | Low (about 50 lines) |
| Level 2 | Recursive traversal of import graph across pack_subdir | Full dependency tree can be inspected | Complex to implement. Recursion depth management, circulation detection, and path resolution must be considered. With performance cost | Medium to high (approximately 150 lines) |

#### Recommended: Level 1

We recommend implementing Level 1 in the next wave.

- Local dependencies of converter are usually placed in the same directory (pattern of placing helper under `converters/`)
- Path resolution is simple if it is limited to the same directory, and the risk of false positives is low.
- Level 2 assumes that the converter is designed to span multiple directories, but such cases are rare under the current converter rules.

Level 2 will be considered once the use case is confirmed.

#### Level 1 pseudocode

```python
def check_converter_with_locals(
    converter_path: Path,
    blocked: set[str],
) -> list[str]:
    """converter と同一ディレクトリのローカル .py を再帰的に AST 検査する。"""
    violations: list[str] = []
    converter_dir = converter_path.parent
    visited: set[Path] = set()

    def _check(target: Path) -> None:
        if target in visited:
            return                          # 循環 import 防止
        visited.add(target)
        tree = ast.parse(target.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # ast.Import      → [alias.name for alias in node.names]
            # ast.ImportFrom   → node.module（相対 import の場合 None あり）
            for name in _extract_module_names(node):
                if name in blocked:
                    violations.append(f"{target.name}: blocked import '{name}'")
                # 同一ディレクトリに .py があればローカル依存として再帰検査
                local = converter_dir / f"{name.split('.')[0]}.py"
                if local.exists() and local != target:
                    _check(local)

    _check(converter_path)
    return violations
```

> `_extract_module_names()` is a helper that returns a list of module name strings from the `ast.Import` / `ast.ImportFrom` nodes. You can reuse the existing `ConverterASTChecker` logic.

#### Test Plan (Level 1)

| # | Scenario | Expected result |
|---|---------|---------|
| 1 | converter alone `import subprocess` | Reject |
| 2 | converter → `from .helper import x` → `helper.py` to `import os` | Reject (blocked import detection via local dependency) |
| 3 | converter → `from .helper import x` → `helper.py` is clean | allowed |
| 4 | converter → `import requests` (external package, no `.py` locally) | Allow (skip due to no local file) |
| 5 | converter → `helper.py` → `from .utils import y` → `utils.py` to `import socket` | Rejection (detected by recursive scan) |
| 6 | Circular import: converter → helper → converter | Ends normally without infinite loop (prevented by visited set) |
| 7 | Import outside the converter directory (`from ..other import z`) | Skip (outside the inspection scope of Level 1. Supported in Level 2) |

---

## Audit log

### Overview

All important operations are recorded in `user_data/audit/` in JSON Lines format.

### Category

| Category | Contents |
|----------|------|
| `flow_execution` | Flow execution |
| `modifier_application` | Apply Modifier |
| `python_file_call` | Block execution |
| `approval` | Pack approval operation |
| `permission` | Authority operations (including network grant, capability grant) |
| `network` | Network communication |
| `security` | Security event |
| `system` | System events (lib, pip, pending export, etc.) |

### File naming

`{category}_{YYYY-MM-DD}.jsonl`

The date in the file name is determined from the entry's `ts` (timestamp). Even if it crosses midnight, it will be sorted into the file corresponding to `ts` of the entry. If `ts` is invalid, it will fall back to the date at the time of writing.

### Entry structure

```json
{
  "ts": "2024-01-01T00:00:00Z",
  "category": "python_file_call",
  "severity": "info",
  "action": "execute_python_file",
  "success": true,
  "flow_id": "ai_response",
  "step_id": "generate",
  "phase": "generate",
  "owner_pack": "ai_client",
  "execution_mode": "container",
  "details": {
    "file": "blocks/generate.py",
    "execution_time_ms": 150.5
  }
}
```

---

## Pending Export

### Overview

`user_data/pending/summary.json` is automatically generated at startup. External tools can understand the approval status just by reading this file. Officials do not give special treatment to consumers of this file (No Favoritism).

### Output format

```json
{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 1,
    "modified_ids": ["pack_c"],
    "blocked_count": 0,
    "blocked_ids": []
  },
  "capability": {
    "pending_count": 1,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 3
  },
  "pip": {
    "pending_count": 0,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 2
  }
}
```

If each module cannot be imported, its section will contain a `"error"` key (fail-soft).

---

## List of DI containers and services

### Overview

`backend_core/di_container.py` is a lightweight DI (Dependency Injection) container used throughout Rumi AI OS. All services are registered with the container and retrieved by name. Access via `get_container()` as a global singleton.

### DIContainer class

| Method | Description |
|---------|------|
| `register(name, factory)` | Register factory function by name. Instantiated at first `get` (delayed generation) |
| `get(name)` | Get instance. If not registered `KeyError` |
| `get_or_none(name)` | Get instance. If not registered `None` |
| `has(name)` | Determine whether it is registered |
| `reset()` | Clear all registrations |
| `set_instance(name, instance)` | Register an existing instance directly (for testing) |

### Global access

| Function | Description |
|------|------|
| `get_container()` | Get global container (singleton) |
| `reset_container()` | Reset global container (for testing) |

### List of registered services (32 services)

| Wave | Service name |
|------|-----------|
| Wave 1 | `audit_logger`, `hmac_key_manager` |
| Wave 2 | `vocab_registry`, `network_grant_manager`, `store_registry` |
| Wave 3 | `approval_manager`, `permission_manager` |
| Wave 4 | `container_orchestrator`, `host_privilege_manager`, `flow_composer`, `function_alias_registry`, `secrets_store`, `secrets_grant_manager`, `modifier_loader`, `modifier_applier` |
| Wave 5 | `pack_api_server`, `egress_proxy_manager`, `python_file_executor`, `secure_executor`, `lib_executor`, `unit_executor`, `capability_executor` |
| Wave 8 | `diagnostics`, `install_journal`, `interface_registry`, `event_bus`, `component_lifecycle` |
| Wave 15 | `health_checker`, `metrics_collector`, `profiler` |
| Wave 22 | `docker_capability_handler` |
| Wave 24 | `function_registry` |

---

## Kernel mixin configuration

### Overview

`backend_core/kernel.py` constructs a Kernel by composing four Mixin classes. It separates implementations by interest while avoiding single file bloat.

### Mixin list

| Mixin class | File | Responsibilities |
|-------------|---------|------|
| `KernelCore` | `kernel_core.py` | Engine body. Flow loading, context construction, shutdown |
| `KernelFlowExecutionMixin` | `kernel_flow_execution.py` | Flow execution, `depends_on` resolution, condition evaluation |
| `KernelSystemHandlersMixin` | `kernel_handlers_system.py` | Startup/system handlers (init, scan, approve, etc.) |
| `KernelRuntimeHandlersMixin` | `kernel_handlers_runtime.py` | Operation/execution handler (flow execution, capability call, etc.) |

### Synthesis

```python
# kernel.py
class Kernel(
    KernelRuntimeHandlersMixin,
    KernelSystemHandlersMixin,
    KernelFlowExecutionMixin,
    KernelCore,
):
    pass
```

MRO (Method Resolution Order) resolves in the order of Runtime → System → FlowExecution → Core. Each mixin depends on the attributes of `KernelCore` (`self.container`, `self.context`, etc.).

---

## Observability

### Overview

Four modules added in Wave 15 provide structured logs, health checks, metrics, and profiling.

### Structured logging (logging_utils.py)

`backend_core/logging_utils.py` wraps the standard `logging` and provides structured output and context propagation.

| Class/Function | Description |
|--------------|------|
| `StructuredFormatter` | Format logs in JSON or text format |
| `StructuredLogger` | `logging.Logger` Wrapper. Giving key-value context in `bind()` |
| `CorrelationContext` | Thread-safe `correlation_id` Management. Used for per-request tracing |
| `get_structured_logger(name)` | Factory with cache. Calling with the same name returns the same instance |
| `configure_logging()` | Apply global log settings (level, format) at once |

The environment variables `RUMI_LOG_LEVEL` (default `INFO`) and `RUMI_LOG_FORMAT` (`json` or `text`, default `text`) control the behavior.

### Health check (health.py)

`backend_core/health.py` provides a probe-based health checking mechanism. Used from `app.py --health`.

| Class/Function | Description |
|--------------|------|
| `HealthChecker` | Register probes, run in parallel with timeout, and aggregate results |
| `HealthStatus` | 4 states of `UP` / `DOWN` / `DEGRADED` / `UNKNOWN` |
| `probe_disk_space` | Checking free disk space (built-in probe) |
| `probe_memory` | Inspecting memory usage (built-in probe) |
| `probe_file_writable` | Checking whether a file can be written to (built-in probe) |

If all the probes are `UP`, all the probes are also judged as `UP`, if any of them are `DOWN`, it is judged as `DEGRADED`, and if all the probes are `DOWN`, it is judged as `DOWN`.

### Metrics (metrics.py)

`backend_core/metrics.py` provides the foundation for collecting application metrics.

| Method | Description |
|---------|------|
| `increment(name, labels, value)` | Increment counter |
| `set_gauge(name, labels, value)` | Set gauge |
| `observe(name, labels, value)` | Record values in histogram |
| `timer(name, labels)` | Context manager. Automatically record block execution time |
| `snapshot()` | Returns the current values of all metrics in a dictionary |

Labels (dictionaries) allow you to categorize metrics into multiple dimensions. In Wave 15, it has been integrated into `kernel_flow_execution.py` (step execution time), `kernel_handlers_system.py` / `kernel_handlers_runtime.py` (handler invocation count/time).

### Profiling (profiling.py)

`backend_core/profiling.py` provides execution time profiling for functions and blocks.

| Method/Decorator | Description |
|--------------------|------|
| `profile(name)` | Context manager. Record block execution time |
| `profile_func(name)` | Decorator for synchronous functions |
| `profile_async(name)` | Decorator for asynchronous functions |
| `summary()` | Return summary with p50 / p95 / p99 percentiles |

You can set `max_samples` as a memory limit, and older samples will be discarded once the limit is exceeded. It has been integrated into `kernel_flow_execution.py` (Flow execution time, step execution time) in Wave 15.

---

## Common base module

### Overview

A set of utilities added in Wave 12–15 that are shared across packages.

### Common validation (validation.py)

`backend_core/validation.py` provides validation utilities for Pack / Flow / Modifier (Wave 12 added). Centralize common logic such as schema validation, required field validation, and value range validation to eliminate duplication in each module.

### Unified error system (error_messages.py)

`backend_core/error_messages.py` defines a unified error code system across Rumi AI OS.

| Element | Description |
|------|------|
| `ErrorCode` | frozen dataclass. `RUMI-{CAT}-{NNN}` format (e.g. `RUMI-AUTH-001`) |
| Category | `AUTH` (Authentication), `NET` (Network), `FLOW` (Flow), `PACK` (Pack), `CAP` (Capability), `VAL` (Validation), `SYS` (System) |
| `RumiError` | Uniform exception class. Retain `code`, `message`, `details`, `suggestion` |
| `format_error()` | Template expansion helper. Dynamically fill placeholders in messages |

Error codes are managed in the automatic collection registry and are automatically registered in the registry when the module is loaded.

### Type definition (types.py + py.typed)

`backend_core/types.py` aggregates type definitions used throughout the package.

| Type | Definition |
|------|------|
| NewType | `PackId`, `FlowId`, `CapabilityName`, `HandlerKey`, `StoreKey` |
| Type alias | `JsonValue`, `JsonDict` |
| Generic | `Result[T]` (retains success value or error) |
| Enum | `Severity`（`info`, `warn`, `error`, `critical`） |

`py.typed` Marker file (PEP 561) is included to enable type checking with external tools (mypy etc.).

### Deprecation management (deprecation.py)

`backend_core/deprecation.py` provides management and warnings for deprecated APIs.

| Element | Description |
|------|------|
| `DeprecationInfo` | frozen dataclass. Preserve deprecated targets, versions, and alternatives |
| `DeprecationRegistry` | Singleton. Manage deprecation information thread-safely |
| `deprecated()` | Decorator for functions/methods (async compatible). Output warning when calling |
| `deprecated_class()` | Decorator for classes. Output warning when creating instance |

The environment variables `RUMI_DEPRECATION_LEVEL` control the behavior: `warn` (default, prints a warning), `error` (throws an exception), `silent` (ignore), `log` (logs only).

---

## Pack Development Tools

### Overview

`backend_core/pack_scaffold.py` is a CLI tool that generates Pack templates.

### PackScaffold class

Automatically generates the Pack directory structure and files from four types of templates.

| Template | Description |
|------------|------|
| `minimal` | Minimal configuration. `ecosystem.json` + empty `backend/` only |
| `capability` | With Capability handler. Contains `share/capability_handlers/` |
| `flow` | With Flow. Contains `backend/flows/` and `backend/blocks/` |
| `full` | Full set including all elements. Including `lib/`, `converters/`, `modifiers/` etc. |

The generated files are validated with `validation.py` to prevent malformed structures.

### CLI entry point

```bash
python -m backend_core.pack_scaffold --template full --pack-id my_pack --output ecosystem/my_pack
```

Specify `--template` (template name), `--pack-id` (Pack ID), and `--output` (output path).

---

## Deprecated feature

### ecosystem/flows/（local_pack）

This is a compatibility mode that treats Flow/Modifier placed directly in `ecosystem/flows/` as a virtual Pack. By default it is disabled (`RUMI_LOCAL_PACK_MODE=off`). Can be enabled with `RUMI_LOCAL_PACK_MODE=require_approval`, but is not recommended.

Deprecation schedule: Maintained compatibility mode with warnings in v2.0, scheduled for removal in v3.0.

Migration destination: Make it into a pack and place it in `ecosystem/<pack_id>/backend/` or place it in `user_data/shared/flows/`.

### addon_manager

A JSON Patch-based addon mechanism existed in `backend_core/ecosystem/addon_manager.py`, but was removed in Phase 2. It doesn't currently exist in the codebase.

### flow/ directory

The old `flow/` directory is deprecated. Please move to `flows/`, `user_data/shared/flows/`, or `flows/` in a pack.

### Deleted files

The following files/directories have been deleted.

| Target for deletion | Replacement | Reason |
|---------|------|------|
| `capability_handler_registry.py` | `function_registry.py` | Integrated into FunctionRegistry (Phase A to D) |
| `builtin_capability_handlers/` | `core_pack/` | Migrate to core_pack |

# Defaultspack Function Boundary

Defaultspack now treats function manifests as the public operation boundary. HTTP routes are compatibility adapters, AI tools are optional facades, and Flow/function.call invocations all converge on the same defaultspack functions before reaching domain services.
