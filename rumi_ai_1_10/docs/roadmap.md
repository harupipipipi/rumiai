<!-- docs-i18n-links:start -->
[EN](./roadmap.md) | [JP](./i18n/ja/roadmap.md) | [KR](./i18n/ko/roadmap.md) | [CN](./i18n/zh-cn/roadmap.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Roadmap

## 🚀 Phase V: Rumi Viewer + Pack Desktop application [Most important/top priority]

> **This phase takes precedence over all other tasks. **
> Most important milestone to enable Rumi to be distributed as a "terminal-free desktop app".

### Architecture Overview

**Contents of the installer (distributed to users):**

1. **Rumi Console** (rumi-launcher, Rust)—Resident in tray. Kernel process management. Users are usually not aware of this.
2. **Rumi Viewer** (Tauri) — A general-purpose WebView app that displays the Pack front end. The main app that users use on a daily basis.
3. **bundled/uv** — For building a Python environment.
4. **app/** (rumi_ai_1_10/) — Kernel source code.

**What is Rumi Viewer:**
- General-purpose WebView application created with Tauri
- Display the frontend (HTML/CSS/JS) declared by Pack in `web_mount`
- Can only connect to Kernel API (localhost:8765). I can't go to external sites
- Pack just passes the front end file. Do not touch the host environment (sandbox WebView)
- Pack backend runs isolated in a Docker container
- Double isolation with "frontend = sandbox WebView" + "backend = Docker isolation"

**Security model:**
- `viewer:display` capability is required to display something in the Viewer (capability-based permission management)
- Viewer can be used in any pack as long as you have the privileges
- `core_viewer_capability` has the same position as `core_docker_capability` and `core_communication_capability`
- It is possible for Packs to provide their own desktop apps (Tauri/Electron, etc.), but this will be treated as a "risky permission" (`desktop_app.execute`) and will require explicit user approval.
- Most Packs should use the secure Viewer route.

**User Experience:**
1. User installs with installer (.dmg/.exe)
2. Double-click Rumi Viewer
3. Rumi Console starts automatically → Kernel starts in the background
4. Control Panel is displayed in Viewer
5. Install the Pack → Pack's front end such as AI chat will be displayed in the Viewer.
6. Don't touch the terminal at all

**Startup flow:**
```
Rumi Viewer 起動
  → Kernel ヘルスチェック（localhost:8765/health）
  → 未起動なら Rumi Console を自動起動
  → Kernel ready を待機
  → Viewer が localhost:8765/panel/ を WebView に表示
  → ユーザーが Pack を選択 → Pack のフロントエンドに遷移
```

**Conflict/Error Handling:**
- Conflicts and startup errors can be displayed and dealt with using Rumi Console (tray icon)
- Viewer is only for displaying

### TODO (in order of implementation)

**Phase V-1: Create new Rumi Viewer (Tauri)** [Most important/top priority]
- [ ] `rumi_viewer/` Create a new Tauri project
- [ ] Kernel health check + autostart (via Rumi Console)
- [ ] Display localhost:8765/panel/ in WebView
- [ ] Pack switching UI (navigation in Viewer)
- [ ] Allow only requests to Kernel API (external URL block)
- [ ] Window management (multiple packs can be opened at the same time)

**Phase V-2: core_viewer_capability new creation**
- [ ] `core_runtime/core_pack/core_viewer_capability/` Create new
- [ ] `viewer:display` capability definition
- [ ] Grant management for Pack to display frontend in Viewer
- [ ] pack_token issuance API for Viewer (`/api/viewer/token`)

**Phase V-3: Installer integration**
- [ ] Add Rumi Viewer to Packager.toml
- [ ] update release.yml (add viewer build)
- [ ] Include all Rumi Console + Rumi Viewer + bundled/uv + app/ in the installer
- [ ] macOS: Include both apps in .dmg
- [ ] Windows: Install both with NSIS + Start menu registration

**Phase V-4: Pack desktop app compatible (optional)**
- [ ] Added `desktop_app` section to ecosystem.json
- [ ] Arbitrary commands can be declared with `desktop_app.command`
- [ ] `desktop_app.execute` capability (dangerous authority, requires explicit authorization)
- [ ] pack-shell binary (Kernel auto-start + token acquisition + command execution)
- [ ] .app / .lnk generation (PackAppRegistrar)

**Phase V-5: Documents + Templates**
- [ ] `docs/pack_desktop_app_guide.md` Create new
- [ ] Tauri Pack template project
- [ ] Sample Pack (AI chat front end)

---


Last updated: 2026-02-24

This is a complete roadmap that includes design concepts and past plans. See [architecture.md](./architecture.md) for the complete design.

---

## 0. North Star (Vision)

- **Foundation without infrastructure**: The official version has no domain concept (chat/tools/prompts/UI, etc.) and only provides OS-like mechanisms such as "execution, approval, isolation, audit, and authority."
- The ecosystem is assumed to be created by a third party (malicious assumption), and the core is **Approval required**, **Docker isolation (strict recommended)**, **Fail-soft**, and **Audit log**.

---

## 1. Design Principles

### 1.1 No Favoritism

The official core does not interpret the meaning of "API key", "tool", "chat", etc. Officially provided generic mechanisms: Flow execution, authorization gate (hash validation), isolated execution (Docker/UDS), Trust + Grant (capability), audit log.

### 1.2 Malice premise (Threat model)

Pack Always assume the possibility that the author has malicious intent. Pack execution is basically Docker `--network=none`. External communication and host privileges are assigned to capability (Trust + Grant).

### 1.3 Fail-soft

Even if one part breaks, the entire OS does not stop. Visualize and continue with diagnostics and audits.

### 1.4 Single entry point for host privileges

Dangerous things on the host (external communication, file access, update application, terminal, etc.) are not done directly by Pack, but are mediated by capabilities, and cannot be done without permission.

---

## 2. Concept organization

### 2.1 Pack / principal / capability

- **principal**: Subject of authority determination. v1 is based on pack_id units to simplify operation.
- Capability is requested with `permission_id` and granted with Trust (sha256) and Grant (principal × permission).

### 2.2 pack in pack (layering)

As in `parent__child`, the hierarchy is expressed by pack_id, and the higher level restricts the lower level (the lower level will not move unless the higher level allows it).

Purpose: Bundle distribution, integrated management of operations, parent-child permission constraints.

> Note: Directory hierarchy ≠ security boundary. Enforcement power is ensured by the ``host side gate (capability / execution device)''.

### 2.3 Store / Unit (shared area and reuse unit)

A shared area (Store) that users/ecosystems can create arbitrarily and a reusable unit (Unit) within that area are valuable as a general-purpose platform. Unit can be `data / python / binary` etc. The execution unit is based on Pack approval + Unit Trust (sha256 allowlist).

Execution modes can be selected (not corrected) depending on privileges: pack container, host capability, dedicated sandbox (in the future).

---

## 3. List of official core foundations

### 3.1 Dependency (pip) introduction

Pack includes `requirements.lock`. wheel-only is the default (sdist is approved as an exception). In the builder container, download → install (install is offline). At runtime, show site-packages with RO mount + PYTHONPATH (container maintains network=none).

### 3.2 capability handler candidate introduction (approval workflow)

Candidates are included in the ecosystem. scan → pending → approve/reject → blocked (rejected 3 times). approve Trust registration + copy + registry reload. cooldown 1h, blocked is not notified until unblocked.

### 3.3 Secrets (Save API key)

Avoid `.env` (reduce accident rate). Store in `user_data/secrets/`, do not output value to log. Don't show your secret files to Pack. Acquisition is basically via capability (e.g. `secrets.get`).

### 3.4 Pack distribution format

Input 3 format: Folder / `.zip` / `.rumipack` (zip compatible). Recommended: one pack root on top. Can be expanded to multi-pack archive (pack in pack) in the future.

### 3.5 Update application (auto update prohibited)

The official version does not auto-update. Get → staging → apply separation. Since apply is dangerous, I would like to move it to capability (`pack.update`) (v1 can also be used as an operational API). Start by applying a single pack_id.

### 3.6 Execution (Python/Binary)

Normal execution of Pack is established in Docker isolation, so it is OK even if the host does not have Python (as long as it has Docker). For things that run on the host (capability handler, etc.), in the future it will be necessary to either make Rumi itself a single executable file (Python included) or to make handler a binary for each OS (both are possible).

---

## 4. Implementation status

In this roadmap, each item is managed in the following states.

| Symbol | Meaning |
|------|------|
| ✅ | Done (implemented/operational) |
| 🟡 | Partial (foundation is present/improvement required) |
| 🧩 | Planned (planned/not implemented) |
| 🧪 | Experimental (experiment/firm specifications later) |

> Note: Automatic verification of the real repository state is not performed here. Make a checklist later if necessary.

---

## 5. v1 (current to recent): Completion of an operational OS (official core)

### 5.1 Secure execution/approval/audit (foundation)

- ✅ Pack approval (hash verification, modified detection, blocked)
- ✅ Audit log (jsonl by category)
- ✅ Docker isolation (strict recommended, permissive is a warning)

### 5.2 pip dependency introduction (requirements.lock)

- ✅ scan → approve → download/install with builder
- ✅ site-packages RO mount + PYTHONPATH
- 🟡 Audit clarification of sdist exception (allow_sdist) operation (continuous improvement)

### 5.3 capability (Trust + Grant + Candidate introduction)

- ✅ Candidate introduction flow (pending / approve / reject / blocked / cooldown)
- ✅ Trust store / Grant manager / Executor / Proxy（UDS）
- ✅ Grant management by principal (HMAC signature)
- 🟡 Multiplatform binaries (trust extensions) are mid-term

### 5.4 Secrets (plain text OK, accident rate reduction)

- ✅ user_data/secrets（1 key = 1 file、tombstone、journal）
- ✅ API is only list(mask) / set / delete (no redisplay)
- ✅ Do not output values to logs (both auditing and diagnostics)
- ✅ `secrets.get` rate_limit=60 (accident prevention)
- ✅ get_secret() helper function (rumi_capability.py) — Wave 2 #32
- 🧩 v1.1: OS keychain (keyring / DPAPI etc.) will be postponed

### 5.5 Pack import (folder / zip / rumipack)

- ✅ Import folder/zip/rumipack
- ✅ Zip structure requires "top single directory"
- ✅ Protection against zip slip / size restrictions etc.
- ✅ staging → apply (with backup)
- ✅ pack_identity mismatch replacement prevention (accident prevention)

### 5.6 Hierarchical permissions (host > parent > child)

- ✅ Resolve parent chain assuming pack_id `parent__child`
- ✅ Even if the child is allowed, it will be rejected if the parent is not allowed.
- ✅ Intersection of parent config to child

### 5.7 Flow Execution Alignment

- ✅ Unified resolution of `kernel:*` for async routes and pipeline routes
- ✅ Corrected consistency of packs_dir etc. in startup flow
- ✅ _eval_condition parser improvements (supports == / != in values) — Wave 1 #16
- ✅ _resolve_value Recursion depth limit (MAX_RESOLVE_DEPTH=20) — Wave 1 #70
- ✅ Flow Chain Depth Limit (MAX_FLOW_CHAIN_DEPTH=10) — Wave 1 #58

### 5.8 Security enhancement (Wave 1)

- ✅ Require cryptography (remove base64 fallback) — #1
- ✅ API Server Bind Address Limit (default 127.0.0.1) — #3
- ✅ Host execution timeout (ThreadPoolExecutor, 120s) — #4
- ✅ Unified pack_id validation (^[a-zA-Z0-9_-]{1,64}$) — #9
- ✅ Store root_path path traversal prevention — #5, #12
- ✅ Container name UUID (collision avoidance) — #10
- ✅ Docker stdout size limit (4MB) — #14
- ✅ Docker availability cache (60s TTL) — #17
- ✅ DNS rebinding mitigation (egress_proxy) — #13
- ✅ egress_proxy ThreadPool — #33
- ✅ HMAC Signature Logic Integration (HMACSigner) — #65
- ✅ HMAC key file atomic write — #34
- ✅ Wildcard domain warning — #31
- ✅ API error message concealment — #35
- ✅ File name validation (secure_executor) — #57
- ✅ pack_import path traversal prevention — #30
- ✅ DELETE route conflict resolution — #59

### 5.9 Strengthening ecosystem infrastructure (Wave 1)

- ✅ Flow Modifier wildcard warning/dry-run mode — #7, #40
- ✅ Default behavior when Modifier phase is not specified — #8
- ✅ Duplicate pack_id detected — #15
- ✅ connectivity requires unsatisfied warning — #20
- ✅ Wildcard Modifier Audit Log — #61
- ✅ No Favoritism: Delete dead code (initializer.py), neutralize docstring — NF1-3

### 5.10 Internal quality/development platform (Wave 12-14)

- ✅ Test enrichment: test_egress_proxy(91+), test_capability_installer(44+), test_flow_modifier_regression(32+), test_pack_api_server(53+), test_store_registry(49+) — Wave 12
- ✅ egress_proxy enhancement (rate limiting/domain control/fine-grained timeout) — Wave 12
- ✅ validation.py (common validation platform) — Wave 12
- ✅ logging_utils.py (Structured logging: StructuredFormatter, StructuredLogger, CorrelationContext, get_structured_logger, configure_logging) — Wave 12
- ✅ egress module division: egress_ip.py, egress_protocol.py, egress_rate_limiter.py, egress_domain_controller.py — Wave 13
- ✅ capability/modifier module division: capability_models.py, flow_modifier_models.py, flow_modifier_loader.py — Wave 13
- ✅ health.py (HealthChecker: disk_space / memory / file_writable probe) — Wave 13
- ✅ metrics.py (MetricsCollector: Counter / Gauge / Histogram / Timer) — Wave 13
- ✅ error_messages.py (ErrorCode, RumiError, error code system RUMI-{CAT}-{NNN}) — Wave 13
- ✅ egress_proxy.py duplicate removal + test patch fix — Wave 14
- ✅ profiling.py (Profiler: context manager/decorator, p50/p95/p99, memory limitations) — Wave 14
- ✅ types.py + py.typed（NewType: PackId / FlowId / CapabilityName / HandlerKey / StoreKey, Result Generic, Severity enum, PEP 561）— Wave 14
- ✅ pack_scaffold.py (PackScaffold CLI: 4 template minimal/capability/flow/full, validation.py integration) — Wave 14
- ✅ deprecation.py (deprecated decorator, DeprecationRegistry, deprecated_class, RUMI_DEPRECATION_LEVEL environment variable) — Wave 14

### 5.11 Kernel integration/DI extension (Wave 15)

- ✅ kernel_core.py: logging→get_structured_logger, deprecated applied, types.py applied
- ✅ kernel_flow_execution.py: logging→get_structured_logger, Flow measurement with Profiler, step measurement with MetricsCollector
- ✅ kernel_handlers_system.py: logging→get_structured_logger, MetricsCollector measurement addition
- ✅ kernel_handlers_runtime.py: logging→get_structured_logger, MetricsCollector measurement addition
- ✅ di_container.py: Factory registration of health_checker / metrics_collector / profiler (32 services in total)
- ✅ app.py: configure_logging() call, --health flag added

> New environment variables: RUMI_LOG_LEVEL, RUMI_LOG_FORMAT, RUMI_DEPRECATION_LEVEL. New CLI flags: --health, --validate.

---

## 6. v1.5 to v2 (mid-term): Development to prevent breakage even when expanded

### 6.1 Store / Unit (shared area and reuse unit)

- ✅ Store registry (multiple stores, no fixed path) — `core_runtime/store_registry.py` Implemented
- ✅ Unit registry (data / python / binary) — `core_runtime/unit_registry.py` Implemented
- ✅ Unit trust store (sha256 allowlist) — `core_runtime/unit_trust_store.py` Implemented
- 🟡 Unit execution gate (only host_capability mode is implemented. pack container / sandbox is not implemented) — `core_runtime/unit_executor.py`
- ✅ Store Compare-And-Swap (store.cas) — fcntl.flock based — Wave 2 #6
- ✅ store.list pagination (limit / cursor / prefix) — Wave 2 #18
- ✅ store.batch_get (maximum 100 keys, 900KB limit) — Wave 2 #19
- ✅ Declarative Store creation (stores field in ecosystem.json) — Wave 2 #62
- ✅ Store sharing between packs (SharedStoreManager, manual approval) — Wave 2 #21
- 🧩 Operational maintenance of "Pack approval is required, unit individual approval depends on unit setting (pack can be requested)"

> The word "assets" is not used here. If an ecosystem creates a ``store for compatible reuse,'' it will be established.

### 6.2 Enhancement of binary support for capability (realization of operation without Python)

- 🧩 handler.json supports artifacts (by OS/arch)
- 🧩 Trust store extension (handler_id → multiple sha256)
- 🧩 Direct binary execution of executor (stdin JSON / stdout JSON)
- 🧩 Comparison study with “Converting Rumi itself to a single executable file” (UX/Operation)

### 6.3 Full update application capability

- 🧩 `pack.update` Standardization of permission (though the meaning is not officially interpreted, but as a "frame for dangerous operations")
- 🧩 Apply operation via capability and minimize direct access to API
- 🧩 Version history/rollback (staging/backup standard operation)

### 6.4 Capability Expansion (Wave 2)

- ✅ flow.run Capability (synchronous Flow-to-Flow calls, cycle detection, depth limits) — Wave 2 #5
- ✅ Batch Capability Grant (up to 50, best-effort) — Wave 2 #63
- ✅ Scheduler time zone support (zoneinfo, UTC fallback) — Wave 2 #60

### 6.5 component output key normalization with vocab (Pack compatibility layer)

- 🧩 Output key automatic normalization by component type
- 🧩 Integrate synonym group + converter in vocab_registry into Flow execution path
- 🧩 Standardization of normalization timing (before storing ctx vs when referencing)
- 🧩 Developing recommended patterns for synonym declaration using vocab.txt on the Pack side

#### Background

Issues discovered in third-party pack development. _execute_handler_step_async of kernel_core stores the return value of the Flow step as is in ctx[step["output"]]. In other words, if the default Pack has a structure that returns {"content": "...", "model": "gpt-4"} and the Flow references ${ctx.ai_response.content}, the moment you replace it with a Pack that returns {"text": "...", "model_name": "..."} like another Pack, content becomes null in all Flow steps and breaks.

vocab_registry already has a mechanism to solve this problem, but it lacks "automatic application in the Flow execution path".

#### Proposed implementation plan

**Method A (normalization during storage - recommended)**: Convert to preferred term in vocab_registry before storing ctx in kernel_core. Existing mechanisms can be utilized by changing a few lines.

**Method B (normalization on reference)**: Synonym fallback with _resolve_value. The stored data is not changed, but the resolution path is complicated.

**Method C (opt-in normalization)**: Normalize: true flag in Flow step or declare output_vocab_group in component manifest. There is no impact on existing products, but Pack authors need to be aware of this.

### 6.6 Internal refactoring (P3 pending)

- 🟡 Global singleton → DI container migration (kernel integration/32 services registered) — Wave 15
- 🧩 Store backend to SQLite (migration option from file-based)
- 🧩 large-scale handler split of pack_api_server.py (currently ~80KB)
- 🧩 Docker execution logic commonality (python_file_executor / secure_executor integration)

---

## 7. v3 (long-term): Outside that should be realized in the ecosystem

> Items in v3 are not to be implemented in the official core, but as an ecosystem (Pack).
> Must be provided by a third party. The formula is to realize these functions.
> We have already provided general-purpose mechanisms (API server, Store, Capability, etc.).

### 7.1 Management UI
- Management UI can be implemented as a Pack (front-end Pack that calls the pack_api_server API)
- Officially provided HTTP API. UI is an ecosystem area

### 7.2 External authentication linkage
- Authentication for Supabase etc. can be achieved by Pack via Secrets + capability
- Officials do not enforce authentication mechanisms

---

## 8. Addon (obsolete)

The JSON Patch-based addon mechanism that existed in `backend_core/ecosystem/addon_manager.py` has been removed. Flow Modifier takes over that role.

---

## 9. Rules/Operations (Runbook Key Points)

- strict is recommended for production (Docker required)
- secrets never logs value
- capability is a two-tier combination of Trust + Grant
- pip dependency is basically wheel-only, sdist is exception approval
- Updates are not applied automatically (user interaction required)
- Track skips/denials with audit + diagnostics

---

## 10. Future issues (clarify undecided matters)

- To what extent will the official standardize the operation and maintenance of Store / Unit (just a frame vs. a little thicker)?
- Unit's individual approval UX (designed to avoid too many pending items)
- Pack container / sandbox mode implementation of Unit execution gate
- Shortest route for distribution without Python (unification of main body vs. binaryization of handler)
- config upper limit of hierarchical authority (definition of intersection: list is intersection set, ports is minimum, etc.)
- Scope of output key normalization using vocab (all steps vs opt-in vs component type only)
- vocab synonym conflict resolution (Pack A is content = body, Pack B is content = entire HTML)
- Execution security of converter (Does Trust need to be set because arbitrary Python runs?)
- Provides uniformity of patterns (schema is ^[a-z][a-z0-9_]*$, but pack-development.md example is ai.client and dot-separated — which is correct?)
- defaults_pack integration (in progress by another team)
- Compilation → Application (single executable file distribution)
- Documentation maintenance (in progress in Wave 16)

---

## Appendix: Important anti-patterns (don't do it)

- Mount secrets on the container and have Pack read it (immediately NG)
- Officials have fixed concepts such as tool / chat (violation of No Favoritism)
- auto update (rewrites the ecosystem without explicit user operation)
- Emit secret values and decryptable information in audit logs
