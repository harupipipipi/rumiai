# Changelog - defaultspack v2.0.0

## [2.0.0] - 2026-04-05

### Added

#### Core Infrastructure
- **ModuleStateManager**: Full lifecycle state machine for all modules
  - States: enabled, disabled, degraded, error_disabled, experimental
  - Auto-disable on consecutive failures with cooldown
  - Manual retry, rollback support
  - Event emission on all state transitions (module.enabled, module.disabled, module.degraded, module.error_disabled, module.recovered)
- **DependencyManager**: Module dependency graph with topological sort
  - Required/optional dependency tracking
  - Transitive impact analysis
  - Load order resolution (Kahn's algorithm)
  - Dependency catalog with provides/requires
- **EcosystemLoader**: Orchestrated module initialization
  - Dependency-ordered loading
  - Failure containment (one module failure doesn't crash others)
  - Hot reload, rollback per module
  - Full catalog with timing information

#### Pack System
- **SetupPackManager**: Pack installation infrastructure
  - Pack enumeration during setup with display name, description, risk, recommended flag
  - `defaultspack` gets `ALL_OK` permission; other packs get `STANDARD`
  - Audit logging for install/revoke/reset
  - Auto-discovery from ecosystem/ directory
- **PackModifier**: Two modification modes
  - `request_extension` mode (slot-based, conflict-checked)
  - `forced_patch` mode (override with rollback data)
  - Both require user approval
  - Slot conflict resolution, rollback support, audit trail

#### Backend Modules
- **ai_client**: Provider-agnostic AI completion client
  - BaseProvider abstract interface
  - StubProvider for testing
  - ModelProfile with UUID, icon, settings schema, advanced settings
  - ModelRouter for task-based routing
  - ErrorPolicy with retry/failover
  - Token counting per provider/model
- **prompt**: Prompt management system
  - UUID-based registry with icon, metadata
  - Template rendering with variables
  - Prompt mixing with preview
  - Version tracking on updates
  - Metadata index generation
- **tool**: Tool management with consent
  - UUID-based registry with icon, on/off toggle
  - Consent check/grant workflow
  - MCP connection/disconnection/listing
  - Metadata index JSON generation
- **plugin**: Plugin bundle management
  - Manifest with UUID, version, dependencies
  - Atomic install/uninstall
  - Dependency checking (blocks install if deps missing, blocks uninstall if depended on)
- **supporter**: AI support services framework
- **memory**: Multi-type memory system
  - 10 memory types: conversation, project, user, knowledge, typo_tendency, romaji_tendency, response_style, work_type, personality, emotion
  - Hypothesis-only predictions (safe design)
  - Per-entry disable, per-type enable/disable
  - User model aggregation
- **knowledge**: Knowledge base with relevance search
  - CRUD operations
  - Token overlap-based relevance scoring
  - Error/solution pair storage
- **chat**: Conversation management
  - Create/get/list/delete conversations
  - Message queuing (AI can receive next message while streaming)
  - Stream start/stop control
  - History compaction (keep last N)
  - Export to JSON
- **agent**: Multi-agent orchestration
  - Role-based agents (coder, reviewer, PM, etc.)
  - Task lifecycle (pending, running, completed, failed, paused, escalated)
  - Checkpoint/resume for long tasks
  - Channel-based messaging (AI Slack style)
  - PM escalation route
- **coding**: File operations, git ops, terminal
- **media**: Screenshot, image read
- **sandbox**: Linux sandbox with GUI control, click, type, screenshot

#### Frontend
- **FrontendManager**: UI component management
  - Component registration
  - Layout save/load
  - Settings injection (category + HTML)

#### CLI
- **CLIManager**: Command-line interface
  - Command registration and dispatch
  - Session sharing with web UI

#### Migration
- **MigrationManager**: Old defaults data migration
  - user.csv to user.json conversion
  - Old config format conversion
  - Deprecation logging
  - Rollback support
  - Old data detection

### Architecture Decisions
- **Function-first**: All capabilities registered as functions, not direct block imports
- **Modular**: Every module independently enable/disable/reload/rollback
- **Failure containment**: One broken module doesn't crash the system
- **Loader-based**: root code accesses ecosystem through loaders, not direct imports
- **No block direct import**: transport/frontend never `from blocks... import run`
- **No production stubs**: All stub/fallback code is test-only

### Test Coverage
- 78 tests covering all modules
- Unit tests: ModuleStateManager, DependencyManager, SetupPackManager, PackModifier
- Integration tests: EcosystemLoader, all backend managers
- Migration tests: CSV-to-JSON, config migration, deprecation, rollback
- All 78 tests passing
- 233 pre-existing tests still passing (no regressions)
