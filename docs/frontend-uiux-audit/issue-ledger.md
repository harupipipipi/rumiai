# Frontend UI/UX issue ledger

**Authoritative tracker:** #1069
**Audit date:** 2026-07-10
**Primary maintained web/viewer target:** `soon`

This document is an index, not a replacement for GitHub issue state. Number gaps can be pull requests or unrelated activity.

## Audit phases

| Phase | Issue area | Focus |
|---|---|---|
| Initial audit | issues opened in and around #899–#969 | Viewer/defaultspack/Search Home/Mobile fundamentals, accessibility, responsive behavior, visual polish |
| Deep code-path audit | #970–#1012 | wrong-resource saves, drafts, shortcuts, modals, storage, approvals, URLs, QR, remote desktop, Prompt Studio, Company |
| Residual surface audit | issues after #1012 | Calendar, Subagent, Ambient, Host Permissions, Tool Preview, Right Sidebar, Mobile QR/models, Adaptive Runtime, Browser Companion |
| Guardrail | this PR and #1069 | quality contract, changed-line scanner, CI, evidence matrix, issue template |

## Highest-priority trust boundaries

The P0 queue includes, among other issues:

- #988 — validate and constrain Search Home destinations;
- #994 — remove long-lived API keys from display QR codes;
- #1001 — stop delivering desktop access keys in URL queries;
- #1005 — never auto-approve MCP connection requests;
- #1006 — remove browser approval tokens from URLs/storage and external destinations;
- #1029 — stop granting authority from untrusted Subagent preview metadata;
- #1034 — do not approve/deny authority from ambient gestures alone;
- #1043 — replace fake UI Precision evidence with real measurements;
- #1050 — treat scanned API/provider QR payloads as untrusted credential imports;
- #1052 — remove legacy PC QR bearer-token connection flow;
- #1058 — harden Tool Preview URL/HTML rendering and sandbox boundaries.

These should be resolved before cosmetic consolidation because they define whether users can trust what the UI says happened.

## Latest residual findings

| Issue | Area | Finding |
|---|---|---|
| #1059 | Calendar a11y | complete month-grid keyboard/screen-reader model |
| #1060 | Calendar time | explicit IANA zone and DST policy for Agent schedules |
| #1062 | Adaptive Runtime | remove or implement enabled no-op actions |
| #1064 | Calendar persistence | reconcile local items and backend schedules transactionally |
| #1065 | Adaptive Runtime state | keep toggles/profile drafts aligned with server revisions |
| #1067 | Browser Companion | transactional Save/Poll and actionable connection status |
| #1068 | Adaptive Runtime a11y | complete tabs, filters, evidence, and status semantics |

## Cross-cutting remediation workstreams

### 1. State and persistence

- loaded revision versus local intent;
- dirty/pending/committed/failed/offline/stale/conflict states;
- no silent storage failure or optimistic divergence;
- no background refresh overwriting edits;
- idempotent mutation settlement and reconnect reconciliation.

### 2. Approval, credentials, and external content

- requester and approver separated;
- exact consequence/target/scope/persistence shown;
- no credentials in URL, browser storage, QR, logs, diagnostics, screenshots, or clipboard;
- centralized link/navigation/media policy;
- unknown or untrusted content fails closed.

### 3. Keyboard, focus, and semantics

- complete component pattern rather than visual role fragments;
- pointer-equivalent keyboard operations;
- guaranteed exit from remote/canvas/application modes;
- exact opener/nearest-item focus restoration;
- stable live-region and repeated-action context.

### 4. Responsive and visual finish

- 320 px, short height, on-screen keyboard, 200%/400% zoom;
- consistent typography, density, spacing, iconography, radius, elevation, and status color;
- removal of gratuitous gradient/glow/blur/nested-card “AI template” styling;
- all interaction states and no hover-only actions;
- long Japanese, IDs, URLs, code, empty/dense/error states.

## Closure rule

Do not close an issue because the happy path looks improved. Close it when the acceptance criteria, regression tests, and applicable runtime evidence in `manual-test-matrix.md` are attached and reviewed.
