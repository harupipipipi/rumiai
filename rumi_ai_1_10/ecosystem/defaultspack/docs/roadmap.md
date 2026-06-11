<!-- docs-i18n-links:start -->
[EN](./roadmap.md) | [JP](./i18n/ja/roadmap.md) | [KR](./i18n/ko/roadmap.md) | [CN](./i18n/zh-cn/roadmap.md)
<!-- docs-i18n-links:end -->

# rumiai defaults Pack — Roadmap

Last updated: 2026-03-06
Status legend: ✅ Completed / 🔧 Needs modification / ⬜ Not started

---

## Phase 0: Foundation (Complete)

All completed. Operation has been confirmed from startup to browser access to AI chat.

| ID | Content | Status |
|----|------|-----------|
| G0-G3 | Skeleton ~ Chat/Flow layer | ✅ |
| P0 | Normalization | ✅ |
| G4 | Agent / Transport / Frontend | ✅ |
| G5 | AI provider (OpenAI, Anthropic, Google, Genspark) + MCP | ✅ |
| G6 | UX enhancement | ✅ |
| G7 | Tool & Prompt Extension | ✅ |
| G8 | Agent enhancement + all fixes | ✅ |
| G9a/b | Knowledge base + automatic search in flow | ✅ |
| docs | Documentation 24 files + 4 revisions | ✅ |
| startup/boot-fix | setup.py, ecosystem.json, components/ | ✅ |
| Step 0 | Route Registry pattern migration (44→100 route distribution) | ✅ |

---

## Phase 1: Enhancements (T1-T17)

17 Parallel implementation of tasks. Completed with Route Registry without any changes to http.py.

| ID | Content | domain | blocks | Root | Status |
|----|------|--------|--------|--------|-----------|
| T1 | Multiple conversation session management | ✅ session_manager.py | 🔧 blocks/chat/session/ not created | 🔧 not registered | 🔧 |
| T2 | Conversation history editing by AI | ✅ history_editor.py | 🔧 blocks/chat/history/ Not created | 🔧 Not registered | 🔧 |
| T3 | Runtime tool creation | ✅ runtime_creator.py | ✅ Compatible with existing blocks | ✅ | ✅ |
| T4 | Disclaimer agreement tool | ✅ disclaimer_manager.py | ✅ Correspond with existing blocks | ✅ | ✅ |
| T5 | prompt advanced (builder, versioning) | ✅ builder.py | ✅ blocks/prompt/advanced/ | ✅ 8 routes | ✅ |
| T6 | tool/prompt unified template | ✅ unified.py | ✅ blocks/prompt/convert.py | ✅ | ✅ |
| T7 | rumi model (automatic routing) | ✅ model_router.py | ✅ blocks/ai/routing/ | ✅ 10 routes | ✅ |
| T8 | Context display API | ✅ analyzer.py | 🔧 No dedicated blocks | 🔧 Route not registered | 🔧 |
| T9 | dev tool extension | ✅ usage_tracker.py | ✅ Compatible with existing blocks | ✅ | ✅ |
| T10 | Organization agent base | ✅ org_manager.py | ✅ blocks/agent/org/ (11 files) | 🔧 Root not registered | 🔧 |
| T11 | Slack-like AI chat | ✅ channel_manager.py | ✅ blocks/chat/channel/ (10 files) | ✅ 10 routes | ✅ |
| T12 | Scheduled execution agent | ✅ scheduler.py | ✅ blocks/agent/scheduler/ (9 files) | ✅ 9 root | ✅ |
| T13 | Add instructions during task | ✅ interrupt_manager.py | ✅ blocks/agent/interrupt/ (8 files) | ✅ 9 routes | ✅ |
| T14 | Linux environment + coordinate manipulation | ✅ container_manager.py | ✅ blocks/tool/container/ (12 files) | ✅ 13 root | ✅ |
| T15 | Permission management | ⬜ Not implemented | ⬜ Not implemented | ⬜ | ⬜ |
| T16 | CLI complete isolation | ✅ cli.py | ✅ blocks/cli/entry.py | ✅ 2 roots | ✅ |
| T17 | Tab system backend | ⬜ Not implemented | ⬜ Not implemented | ⬜ | ⬜ |

---

## Phase 2: Quality Assurance + Remaining Corrections

### 2-A: P1 Modification (Blocker)

| ID | Contents | Details |
|----|------|------|
| P1-1 | System route 404 correction | Register /api/health, /, /api/context, /static/* to io.http.route. Make it accessible even in Registry mode |
| P1-2 | T15 Implementation of permission management | domain/permission/manager.py, user_store.py, role_store.py, auth.py, audit.py + blocks/permission/ + setup.py Route registration |
| P1-3 | T17 Tab system implementation | domain/frontend/tab_manager.py, tab_presets.py + blocks/frontend/tabs/ + setup.py Route registration |

### 2-B: P2 modification (functional completion)

| ID | Contents | Details |
|----|------|------|
| P2-1 | T10 organization agent route registration | Add org system 11 route to blocks/agent/setup.py |
| P2-2 | T1 session management blocks + route | Create blocks/chat/session/ + add 8 routes to chat/setup.py |
| P2-3 | T2 history editing blocks + route | Create blocks/chat/history/ + add 4 routes to chat/setup.py |
| P2-4 | Root of T8 context API | Register /api/context/conversation/{id}, /api/context/system |
| P2-5 | provides update of ecosystem.json | Reflects new handlers for T10/T12/T13/T14 |

### 2-C: File check

| ID | Contents | Details |
|----|------|------|
| FC-1 | Check def run signature of all blocks | Is def run(input_data, context): unified |
| FC-2 | Import style uniformity check | sys.path.insert(0, pack_root) + from blocks._common import ... |
| FC-3 | pass / TODO / NotImplementedError residual check | Are there any prohibited unimplemented functions |
| FC-4 | setup.py The number of routes and the number of real blocks match | Do all registered route destination modules exist? |
| FC-5 | Delete unnecessary files | transport/uds.py, blocks/frontend/stop.py, etc. |

### 2-D: rumiai kernel rule compliance check

| ID | Contents | Details |
|----|------|------|
| RC-1 | ecosystem.json schema compliant | Compatible with ecosystem.schema.json of kernel W26 |
| RC-2 | Check the presence of components/ manifest.json | Does all 11 components have manifest.json |
| RC-3 | Validity of using setup.py context | Is the use of context["interface_registry"] etc. compliant with the kernel specifications |
| RC-4 | Compliance with KernelFacade API restrictions | Are you calling anything other than get_interface, list_interfaces, or emit? |
| RC-5 | Pack approval flow compatibility | File change → modified status → Does re-approval work correctly? |

### 2-E: Neutrality check as defaults

| ID | Contents | Details |
|----|------|------|
| NC-1 | No favoritism to AI providers | Is a specific provider hard-coded? Is stub/default a fallback |
| NC-2 | No model favoritism | rumi Is model routing fair? Are certain models being given undue priority? |
| NC-3 | Storage neutrality | Is the path of user_data/ not fixed but via the kernel's userdata_manager |
| NC-4 | Minimize external dependencies | Are there any required dependencies other than the standard library (Is Docker SDK optional?) |
| NC-5 | Possibility of overriding settings | Can all behaviors be changed using environment variables or API? Are there any hard-coded settings?

---

## Phase 3: Scalability validation

### 3-A: user_data extensibility

| ID | Contents | Details |
|----|------|------|
| UX-1 | user_data access from other Packs | Can other Packs have their own user_data subdirectories |
| UX-2 | Data migration | Is there a way to migrate when changing the schema of user_data |
| UX-3 | Backup/Restore | Is it possible to export/import user_data in bulk |
| UX-4 | Storage plugin | Is it possible to replace it with a storage backend other than JSON files (SQLite, etc.) |
| UX-5 | Concurrent access safety | Is it safe to write user_data from multiple threads/processes (locking mechanism) |

### 3-B: Inter-pack extensibility

| ID | Contents | Details |
|----|------|------|
| PX-1 | Test for adding routes from other Packs | Create a dummy Pack and register the route in io.http.route, will http.py collect it? |
| PX-2 | Domain replacement from other Pack | Is it possible to replace AIClient etc. with InterfaceRegistry |
| PX-3 | Event hook | Can EventBus hook into defaults pack behavior? |
| PX-4 | Provider Plugin | Is it possible to add a new AI provider from another pack (reproducing the Genspark method) |

---

## Phase 4: Production Preparation

### 4-A: Authority system completed

| ID | Contents | Details |
|----|------|------|
| AUTH-1 | Complete implementation of T15 | Base implementation in Phase 2-A P1-2. Integration testing + edge case support here |
| AUTH-2 | Authority definition for each route | Define required authority for all 100+ routes |
| AUTH-3 | Authentication middleware integration | Insert permission check in _handle_request of http.py |
| AUTH-4 | Default user + initial setup flow | Create admin user on first startup |

### 4-B: Create a set of tools / prompts

| ID | Contents | Details |
|----|------|------|
| TP-1 | Built-in tool set | web_search, calculator, code_exec, file_read, file_write, http_request |
| TP-2 | Built-in prompt templates | general_assistant, coder, analyst, translator, summarizer, creative_writer |
| TP-3 | tool/prompt documentation | Usage, parameters, and examples for each tool/prompt |
| TP-4 | Testing tool/prompt | Checking the operation of each tool/prompt |

### 4-C: Front end set (user responsibility)

| ID | Contents | Details | Person in charge |
|----|------|------|------|
| FE-1 | Large-scale split of shell.html | Split into background, sidebar, input bar, title, chattab, setting | User |
| FE-2 | Tab UI | Browser-like tab (normal, work, coding, agent, max, monitor) | User |
| FE-3 | Session UI | Parallel display of conversation tabs (History 1 / History 2 / History 3) | User |
| FE-4 | Channel UI | Slack-style channel list + message display | User |
| FE-5 | Context Panel | Real-time display of current context information | User |
| FE-6 | Dev panel | Prompt usage, real-time editing | User |
| FE-7 | Permission management UI | User/role/permission management screen | User |
| FE-8 | Disclaimer popup | Consent tool popup display | User |
| FE-9 | Container operation UI | Linux environment operation screen + screenshot display | User |

---

## Phase 5: Desktop application

| ID | Contents | Details |
|----|------|------|
| DA-1 | Electron or Tauri wrapper | Packaging shell.html as a desktop app |
| DA-2 | Native notification | OS notification cooperation (regular execution agent result notification, etc.) |
| DA-3 | Tray icon | Background operation + tray icon |
| DA-4 | Automatic startup settings | Automatically start the kernel + defaults pack when the OS starts |
| DA-5 | Updater | git pull-based automatic updates (or GitHub Releases) |

---

## Phase 6: Compile + Release

| ID | Contents | Details |
|----|------|------|
| CP-1 | Python Bundle | Single Binary Kernel + Defaults Pack with PyInstaller or Nuitka |
| CP-2 | Front-end optimization | minify shell.html + asset bundle |
| CP-3 | Cross-platform build | Build for macOS, Linux, Windows |
| CP-4 | Installer | macOS: .dmg, Linux: .AppImage/.deb, Windows: .msi |
| CP-5 | CI/CD Pipeline | Build + Test + Release Automation with GitHub Actions |
| CP-6 | Release notes | Create release notes for all functions |

---

## Phase 7: Final cleanup

| ID | Contents | Details |
|----|------|------|
| CL-1 | Delete unnecessary files | transport/uds.py, transport/stdio.py (after CLI migration), blocks/frontend/stop.py |
| CL-2 | docs final sync | 24 Document updated for full functionality |
| CL-3 | README.md updated | Installation instructions, feature list, screenshots |
| CL-4 | CHANGELOG.md creation | Full release history |
| CL-5 | LICENSE confirmation | Final confirmation of license file |
| CL-6 | feature/genspark-provider branch deletion | Merged branch cleanup |

---

## Statistics

| Item | Quantity |
|------|------|
| Total number of phases | 8 (0-7) |
| Total number of tasks | Approx. 80 |
| Completed tasks | Approximately 45 |
| Remaining tasks | Approx. 35 |
| Number of Registry routes | 100+ |
| Number of blocks | 100+ |
| domain number of modules | 30+ |
| Document | 24 files |
