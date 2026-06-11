<!-- docs-i18n-links:start -->
[EN](./setuptodo.md) | [JP](./i18n/ja/setuptodo.md) | [KR](./i18n/ko/setuptodo.md) | [CN](./i18n/zh-cn/setuptodo.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Setup & Desktop Distribution TODO

> **Legacy planning memo**: History of the implementation plan. Please see [roadmap.md](./roadmap.md) and [docs/README.md](./README.md) for current policies.

Last updated: 2026-03-17

A roadmap based on the Pattern C architecture. The Rust launcher (thin) manages the Kernel process, and the setup UI, control panel, Flow editor, etc. are all Web UI (React) provided by Pack. You are responsible for implementing React UI.

---

## 1. Design decisions

### 1.1 Adopting pattern C

Three-tier architecture: Rust Launcher + Kernel + Pack.

- **Rust Launcher**: Only 5 responsibilities: PBS construction, Kernel process management, health check, tray icon, browser open
- **Kernel**: Python runtime. Flow execution, Pack management, API server
- **Pack**: Provide all UI functions as a pack (React Web UI)

### 1.2 Authentication/Data storage

- **Authentication**: Supabase Auth (OAuth only: Google / GitHub). No email/password authentication
- **Save profile data**: Cloudflare KV (does not save on Supabase)
- **Local Profile**: user_data/settings/profile.json

### 1.3 IPC

Use existing pack_api_server (HTTP localhost:8765). No new IPC required.

### 1.4 UI Policy

- All web UI created with React + TSX
- React UI is in the user's hands. Agent is only Python backend + Flow + API + Rust
- The front end (control panel) of the launcher is also React

### 1.5 Icon Policy

- Only preset icons (user's original icon upload is not supported)
- The icon field stores a preset ID string (e.g. "cat", "avatar_03")
- Image files are saved locally. Receive ID from site and display corresponding image

---

## 2. Architecture overview

```
┌──────────────────────────────────────────────────────────┐
│                    Rust ランチャー                         │
│  (PBS構築 / Kernel起動 / ヘルスチェック / トレイ / open)      │
└───────┬──────────────────────────────────┬────────────────┘
        │ spawn                            │ open browser
        ▼                                  ▼
┌──────────────────────┐        ┌──────────────────────┐
│       Kernel         │        │    ブラウザ (Web UI)    │
│  (Python runtime)    │◄──────►│   React SPA           │
│                      │  HTTP  │   localhost:8765      │
│  ┌────────────────┐  │        └──────────────────────┘
│  │ pack_api_server │  │
│  │ :8765           │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Flow Engine    │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Pack Manager   │  │
│  └────────────────┘  │
└──────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                         Packs                             │
│  ┌──────────────┐ ┌──────────────────┐                   │
│  │ core_setup   │ │ core_control_panel│                   │
│  │ (Phase B)    │ │ (Phase C)         │                   │
│  └──────────────┘ └──────────────────┘                   │
└──────────────────────────────────────────────────────────┘
```

---

## 3. profile.json schema

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-17T12:00:00Z",
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer",
  "setup_completed": true
}
```

| Field | Type | Description |
|-----------|-----|------|
| schema_version | int | schema version |
| initialized_at | string (ISO 8601) | Setup completion date and time |
| username | string | Username (required, up to 100 characters) |
| language | string | Language code (ja, en, zh, ko, es, fr, de, pt, ru, ar) |
| icon | string or null | Preset icon ID |
| occupation | string or null | occupation |
| setup_completed | bool | Setup completed flag |

---

## 4. Progress

### Completed

| Task | Contents |
|--------|------|
| Code review | C+ rank. Identify security architecture issues |
| SEC-1 | secure_executor.py: Docker image digest fixation + _sanitize_context enhancement |
| SEC-2 | python_file_executor.py: Docker image digest fixed |
| APP-1 | app.py: Permissive guard enhancement (whitelist method) |
| Investigation 1 | Python packaging: CONDITIONAL GO with PBS + uv |
| Survey 2 | Control panel + launcher + marketplace concept |
| Investigation 3 | Is it possible to set up with Pack + Flow? → Adopt pattern C |
| Phase B | core_setup Pack Python backend + Flow definition |
| Phase A | Kernel API extensions: /health, /api/setup/status, /api/setup/complete, static file delivery |
| Site deployment | Cloudflare Pages (rumi-setup.pages.dev) |
| Site authentication | Supabase Auth OAuth (Google / GitHub) operation confirmed |

### In progress

| Task | Responsibility | Contents |
|--------|------|------|
| Site finishing | User | Delete dummy form, change to 10 languages, add occupation, implement KV storage |
| App collaboration approval screen | User | /authorize page (design finalized, waiting for implementation) |
| Preset icon creation | User | ID naming + image creation |

### Not started

| Task | Responsibility | Contents |
|--------|------|------|
| R Phase | Agent (Rust) + User (React) | Rust launcher + update mechanism |
| Phase C | Agent (Python) + User (React) | core_control_panel Pack |
| Phase U | Agent | Update Mechanism |
| Phase D/E | Agent + User | Marketplace (last turn) |
| Phase F | Agent | Pack Developer CLI |
| Phase G | Agent | Security enhancement |

---

## 5. Phase configuration

### R Phase: Rust Launcher (Responsible for: Agent + User)

A thin launcher binary made in Rust.

**Agent in charge:**

- R-1: Cargo project initialization + cross-platform build settings
- R-2: PBS download/extract (macOS / Windows / Linux)
- R-3: venv creation + uv pip install
- R-4: Kernel process spawn + stdout/stderr pipe
- R-5: Health check loop (localhost:8765/health, timeout 30s)
- R-6: System tray (tray-icon crate)
- R-7: Browser open (open crate)
- R-8: graceful shutdown (SIGTERM → Kernel stop → process end)

**User Responsible:**

- None (The launcher itself has no UI. UI is core_control_panel React)

### Phase A: Kernel API extension ★Complete

- GET /health — Health check (no authentication required)
- GET /api/setup/status — setup status (no authentication required)
- POST /api/setup/complete — Setup complete (no authentication required)
- Static file distribution middleware
- AppLifecycleManager

### Phase B: core_setup Pack ★Python backend completed

**Complete:**

- ecosystem.json, check_profile.py, save_profile.py, launch_setup_ui.py
- Fixed setup_wizard.flow.yaml, 00_startup.flow.yaml

**Remaining tasks (user responsibility):**

- B-1: Site finishing (dummy form removed, 10 languages added, occupation added)
- B-2: Cloudflare KV profile storage implementation
- B-3: App cooperation approval screen (/authorize)
- B-4: Preset icon creation

### Phase C: core_control_panel Pack (Responsible for: Agent + User)

Dashboard + Pack management + Flow editor + Settings screen + Update confirmation.

**Agent responsible (Python backend):**

- C-1: Create ecosystem.json
- C-2: Dashboard API (Pack list, Flow list, system status)
- C-3: Pack management API (install, uninstall, enable/disable)
- C-4: Flow Editor API (Flow CRUD, step editing, execution)
- C-5: Settings API (edit profile.json, environment settings)
- C-6: Update confirmation API

**User Responsible (React UI):**

- C-7: Dashboard screen
- C-8: Pack management screen (Steam library style)
- C-9: Flow editor screen (React Flow)
- C-10: Settings screen
- C-11: Update screen

### Phase U: Update mechanism (in charge: agent)

- U-1: Version control (current version, get latest version)
- U-2: Update check API (Cloudflare Workers or R2 version file)
- U-3: Rust launcher self-update
- U-4: Kernel (Python) update (source code replacement)
- U-5: Pack update

### Phase D: Marketplace BE (last turn)

Cloudflare Workers + R2 + D1 + Supabase Auth

### Phase E: Marketplace FE (last turn)

Cloudflare Pages + in-launcher integration

### Phase F: Pack Developer CLI

rumi-pack init / validate / build / publish / test

### Phase G: Enhanced security

Pack signature verification, code signing, CSP headers

---

## 6. Dependencies

```
R Phase ──────┐
              ▼
Phase A ★完了  Phase B ★Python完了（React残り）
  │               │
  ▼               ▼
Phase C ──── Phase U
  │
  ▼
Phase F ──── Phase G
  │
  ▼
Phase D ──── Phase E（最後）
```

---

## 7. MVP definition

MVP = R Phase + Phase A + Phase B + Minimum configuration of Phase C + Phase U (update). No marketplace.

---

## 8. App linkage flow

### Setup flow

1. Desktop app opens `https://rumi-setup.pages.dev/authorize?callback=http://localhost:8765/api/setup/complete` in browser
2. Check if you are logged in on the site → /login if not logged in → Approval screen if logged in
3. Approval screen: “Do you want to send your profile information to this app?”
4. Authorize → POST to localhost:8765/api/setup/complete with fetch
5. Save profile.json on the app side → Setup complete

### JSON for POST /api/setup/complete

```json
{
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer"
}
```

---

## 9. Boot sequence

### First launch

1. Start Rust launcher
2. PBS check → If not, download, extract, create venv, install dependencies
3. Kernel spawn → health check → ready
4. startup flow: setup_check → needs_setup: true
5. Open rumi-setup.pages.dev/authorize in your browser
6. User approves → POST to localhost:8765 → Save profile.json
7. Setup complete → Control panel display

### Normal startup

1. Start Rust launcher
2. PBS check → Existence → Skip
3. Kernel spawn → health check → ready
4. startup flow: setup_check → needs_setup: false
5. Display control panel in browser

---

## 10. Infrastructure configuration

| Service | Application |
|----------|------|
| Cloudflare Pages | Site (rumi-setup.pages.dev) |
| Cloudflare KV | Save profile data |
| Cloudflare Workers | Update Check API, Future Marketplace API |
| Cloudflare R2 | PBS/uv distribution, future Pack distribution |
| Cloudflare D1 | Future Marketplace DB |
| Supabase Auth | User authentication (OAuth: Google / GitHub) |

---

## 11. Distribution configuration

### macOS

```
RumiAI.app/Contents/
├── MacOS/rumi-launcher
├── Resources/
│   ├── python/          # PBS
│   ├── rumi_ai_1_10/   # ソースコード
│   └── user_data/       # 初回起動時作成
└── Info.plist
```

### Windows

```
RumiAI/
├── rumi-launcher.exe
├── python/
├── rumi_ai_1_10/
└── user_data/
```

### Linux

```
rumi-ai/
├── rumi-launcher
├── python/
├── rumi_ai_1_10/
└── user_data/
```

---

## 12. Undecided items

- Final list of setup collection items
- Language pack distribution method
- Setup "undo" function
- user_data path on Windows
- Build CI/CD pipeline
- Python version fixed policy
- macOS codesigning / notarization
- Windows code signing
- Web UI delivery method for core_control_panel
- Rust launcher crate selection
- Pack developer CLI language
- Update version file format and distribution method
