# Frontend UI/UX, Accessibility, Privacy, and Trust Audit Baseline

**Audit date:** 2026-07-10  
**Primary target:** `soon`  
**Additional inspected target:** `master` for Rumi Mobile  
**Repository:** `harupipipipi/rumiai`

## Purpose

This document turns the repository-wide frontend audit into a reviewable engineering baseline. It records the concrete issue backlog, release-blocking boundaries, deduplication decisions, and the small fail-closed mitigations included in this change.

It is intentionally not a claim that static review can prove the entire product defect-free. A surface is complete only after the relevant issue acceptance criteria, automated checks, keyboard/screen-reader checks, narrow/zoom checks, native-device checks, and adversarial runtime tests pass.

## Coverage status

The code-first audit reached its static saturation point against the maintained source available on 2026-07-10:

- every concrete source-level finding identified in the inspected surfaces has a dedicated issue or is explicitly deduplicated into an existing issue;
- the initial audit set (`#899–#969`), deep code-path set (`#970–#1012`), residual surface issues, and latest saturation pass are coordinated through tracker #1069;
- number gaps can be pull requests or unrelated repository activity and are not assumed to be audit issues;
- remaining evidence is runtime/device/browser/assistive-technology validation, not an assertion that further defects are impossible.

## Method

The review inspected frontend source and shared UI primitives across:

- Rumi Viewer;
- defaultspack chat, composer, activity preview, Right Sidebar, Company, Subagent Team, Kanban, Prompt Studio, Coding Cockpit, Desktops, Host Permissions, pairing, approvals, Settings, extensions, and Ambient surfaces;
- Search Home;
- standalone Setup;
- Browser Companion;
- Rumi Mobile.

The review classified findings by user consequence rather than by cosmetic severity:

- **P0:** authorization, credential, navigation, execution, identity, privacy, or trust boundary can be bypassed or materially misrepresented;
- **P1:** data loss, wrong-resource mutation, inaccessible core workflow, ambiguous destructive action, or high-impact recovery failure;
- **P2:** incomplete semantics, target size, localization, layout, discoverability, or non-blocking UX debt.

## Release-blocking P0 boundaries

The following issues should be treated as release blockers until their enforcement path is corrected:

| Issue | Boundary |
|---|---|
| #988 | Search Home navigates to backend/restored destinations without a centralized URL policy. |
| #994 | Long-lived provider API keys are encoded in reusable plaintext QR images. |
| #1001 | Desktop access keys are delivered in URL query parameters. |
| #1005 | The MCP requester silently approves its own approval request. |
| #1006 | Browser approval credentials are accepted from URLs, persisted, and could be appended to external destinations. |
| #1029 | Subagent Team presents local preview toggles as if they were authoritative approvals. |
| #1034 | Ambient gestures can settle approvals without request/revision binding and intentional confirmation. |
| #1043 | Static mock scenarios are presented as measured, fair model-comparison evidence. |
| #1050 | Scanned API QR data can persist and activate an attacker-controlled provider endpoint. |
| #1052 | Legacy mobile PC QR imports carry reusable bearer credentials. |
| #1058 | Tool Preview auto-fetches untrusted URLs and executes untrusted HTML with scripts/forms/popups enabled. |
| #1071 | `rumi_local_auth` could be appended to external or malformed URLs. |
| #1078 | Self-declared renderer trust can execute extension JavaScript in the full application origin and blank the shell on failure. |
| #1089 | A temporary secure-storage read failure can silently create a new mobile device signing identity. |

## Audit issue index

The authoritative complete index is tracker #1069. The sections below record the deep and residual source findings carried by this baseline; the initial visual/UI set remains linked from the tracker.

### Rumi Viewer

- #970 — keep Flow selection and loaded graph identity atomic; protect unsaved edits.
- #971 — scope Flow keyboard shortcuts to the canvas and platform conventions.
- #972 — provide a non-pointer interaction model for Flow nodes, ports, and connections.
- #973 — make startup-profile edit, preview, save, and launch use one explicit revision.
- #974 — associate startup-profile fields, groups, statuses, and repeated actions.
- #975 — split shared Popover into correct popover/menu/dialog primitives.
- #976 — correct toast urgency, lifetime, dismissal, and live-region behavior.
- #977 — keep confirmation dialogs open and show recoverable mutation failures inline.
- #978 — replace the raw-error reload boundary with truthful, draft-safe recovery.
- #979 — do not erase completed setup state when verification is temporarily unavailable.
- #980 — harden shared Switch/Input/Button handler, ID, loading, and naming contracts.

### defaultspack shared surfaces

- #981 — make Conversation Spotlight a real modal search/combobox experience.
- #982 — implement a complete combobox contract for `ModelSearchPicker`.
- #983 — standardize modal focus, inertness, close policy, and nested layers.
- #984 — make the application crash boundary truthful, redacted, and draft-safe.
- #985 — reconcile offline Kanban drafts instead of silently replacing them.
- #986 — make Kanban cards, columns, drag/drop, and actions keyboard/screen-reader complete.
- #998 — make closing a pairing review explicitly cancel, reject, or keep pending.
- #999 — do not silently persist terminal commands and output in `localStorage`.
- #1000 — provide an explicit enter/exit contract for remote-desktop keyboard capture.
- #1001 — stop delivering desktop access keys in URL query parameters.
- #1002 — make desktop lifecycle confirmations single-submit and outcome-aware.
- #1003 — protect unsaved Prompt Studio drafts across context changes.
- #1004 — give Prompt Studio fields, filters, tabs, status, and version actions complete semantics.
- #1005 — never auto-approve MCP server connection requests.
- #1006 — remove browser approval tokens from URLs/persistent storage and external destinations.
- #1007 — do not auto-load untrusted remote image URLs from chat content.
- #1008 — do not render unknown chat blocks as raw JSON by default.
- #1009 — preview and validate assistant-provided links before leaving chat.
- #1057 — keep Right Sidebar keyboard-operable by default with one focus/menu model.
- #1058 — isolate Tool Preview URLs and active HTML behind a hardened artifact boundary.

### Search Home

- #987 — render and preserve successful AI answers instead of discarding the response.
- #988 — validate and constrain every routed destination before navigation.
- #989 — stop broadcasting full route queries/candidate URLs with wildcard `postMessage`.
- #990 — scope route hotkeys to an explicit candidate-review state.

### Mobile

- #991 — stop presenting conversation changes as saved when persistence failed.
- #992 — confirm or undo conversation deletion and preserve focus/context.
- #993 — reconcile optimistic PC model/thinking/mode/tool controls after command failure.
- #994 — do not encode long-lived raw API keys in reusable display QR codes.
- #1010 — apply the full approval contract to inline mobile tool requests.
- #1011 — make tool activity understandable, expandable, and recoverable.
- #1050 — treat scanned API/provider QR payloads as untrusted before saving/activation.
- #1052 — remove legacy `rumi_pc` QR imports carrying reusable bearer tokens.
- #1054 — explain model availability and expose selected/search state semantically.

### Setup and Browser Companion

- #995 — do not auto-select opaque heuristic pack bundles as “Recommended”.
- #996 — make core Setup status, selection, errors, and debug details accessible/localized.
- #997 — replace the long-lived manually stored Browser Companion bearer pairing token.

### Company and Subagent Team

- #1012 — give Company mutations per-action acknowledgement, draft protection, and race-safe refresh.
- #1025 — fix silent Right Sidebar placement persistence failure.
- #1026 — route Company writes through approval and audit policy.
- #1027 — disambiguate duplicate Company names and provide lifecycle management.
- #1028 — make Company tabs, forms, tree, menus, and status fully operable.
- #1029 — do not present Subagent Team preview toggles as real approvals.
- #1030 — make Subagent Team messages transactional, retryable, and honest about preview-only state.
- #1031 — give Subagent Team channels, DMs, trees, activity, and composer a coherent interaction model.

### Ambient and Host Permissions

- #1034 — bind gesture approvals to one reviewed request and intentional confirmation.
- #1037 — review/edit/confirm captured audio and transcript before dispatch.
- #1039 — reconcile Host Permissions after returning from OS Settings.
- #1041 — give Host Permissions a semantic table/status and accessible recovery flow.

### Trust and attachments

- #1043 — do not present hard-coded UI Precision scenarios as measured model comparisons.
- #1047 — detect/review secrets and sensitive files before attachment dispatch.

### Latest static-saturation pass

- #1071 — never append `rumi_local_auth` credentials to external or malformed URLs.
- #1072 — do not persist or broadcast full Ambient AI answers as browser-global state.
- #1073 — make Coding diff/checkpoint refresh real and restore reviewable/outcome-bound.
- #1074 — stop swallowing mobile secure-storage failures across credentials/settings/knowledge.
- #1076 — validate and save Mobile Settings as one atomic, recoverable transaction.
- #1078 — replace self-declared trusted renderers with verified isolation and per-region fallback.
- #1079 — redact and bound global client diagnostics before reporting errors.
- #1080 — treat HTML placement manifests as untrusted active content.
- #1081 — make Coding Cockpit and Rumi Review one coherent keyboard/screen-reader workspace.
- #1082 — bind every Rumi Review mutation to an explicit review revision.
- #1083 — treat client approval-settlement events/return parameters as untrusted hints.
- #1085 — validate OAuth destinations and review credential imports before connection changes.
- #1086 — consolidate duplicated model pickers into one complete async combobox contract.
- #1087 — make Composer voice input explicit, reviewable, locale-aware, and recoverable.
- #1088 — make mobile pairing, pickup, ACK, cancellation, and unpair one lifecycle.
- #1089 — never rotate/lose the mobile signing identity because storage was temporarily unreadable.

## Immediate mitigations in this change

### Browser approval-token transport

`authorityApprovalBrowserToken.ts` now:

- rejects external, protocol-relative, malformed, and ambiguous destinations before token transformation;
- omits external `return_to` values;
- stops reading or writing the credential through persistent `localStorage`;
- removes legacy local-storage values during migration;
- retains only the minimum same-origin compatibility path while #1006 remains open.

This is emergency containment, not the complete #1006 design. The final architecture still needs a request-bound, short-lived, authenticated channel that carries no reusable approval credential in a URL.

### Defaultspack local-auth URL containment

`defaultspackLocalAuth.ts` now:

- parses and validates the destination before adding any credential;
- accepts only same-origin HTTP(S) destinations;
- rejects protocol-relative, cross-origin, non-HTTP(S), embedded-credential, control-character, and malformed destinations;
- removes the parse-failure fallback that concatenated `rumi_local_auth` to arbitrary strings;
- remains fail-closed outside a browser by accepting only unambiguous root-relative paths.

This prevents the concrete external/malformed exfiltration path but does not close #1071. The reusable credential still needs to leave URLs and Web Storage entirely in favor of a one-time, audience-bound authenticated exchange.

### Attachment Markdown boundary

`buildAttachmentSnippet()` now:

- normalizes control characters and line breaks in filenames before interpolation;
- chooses a backtick or tilde fence longer than every matching delimiter run in the attachment;
- prevents attachment content containing Markdown fences from escaping the wrapper.

This prevents delimiter breakout but does not solve prompt injection or secret exfiltration. Structured attachment data, sensitivity review, destination policy, and server-side enforcement remain tracked by #1047.

### Regression enforcement

The dedicated `UI Security Guardrails` workflow fails when:

- approval tokens are read from or written to persistent `localStorage`;
- approval/local-auth tokenized URLs can return arbitrary absolute destinations;
- parse failures append credentials to unvalidated strings;
- local-auth destination policy loses protocol, origin, userinfo, or HTTP(S) checks;
- attachment snippets regress to a fixed Markdown fence;
- attachment filenames lose normalization.

Focused Node tests cover external/protocol-relative/non-HTTP(S)/userinfo/malformed destination rejection, same-origin compatibility, return-target filtering, credential non-leakage, and non-colliding attachment fences.

## Required remediation sequence

1. **Contain P0 credential, identity, and execution paths:** #1005, #1006, #1050, #1052, #1058, #1071, #1078, #1089, #994, #1001.
2. **Unify approval semantics and enforcement:** #977, #1010, #1026, #1029, #1034, #1083.
3. **Stop data loss, wrong-resource writes, and silent persistence:** #970, #973, #985, #991, #993, #1003, #1012, #1073, #1074, #1076, #1082, #1088.
4. **Adopt shared modal/menu/combobox/status primitives:** #975, #976, #980, #981, #982, #983, #1086.
5. **Complete keyboard/screen-reader task models:** #972, #986, #1000, #1028, #1031, #1041, #1054, #1057, #1081, #1087.
6. **Harden content/navigation/artifact/extension presentation:** #988, #1007, #1008, #1009, #1047, #1058, #1078, #1079, #1080, #1085.
7. **Run visual and localization validation:** 200%/400% zoom, large text, narrow viewport/height, forced colors/high contrast, reduced motion, long localization, RTL readiness, touch targets, native WebViews, and supported browsers/OS versions.

## Verification

From `rumi_ai_1_10/ecosystem/defaultspack/webapp`:

```bash
node scripts/check-ui-security-guardrails.mjs
npx tsx --test \
  src/lib/authorityApprovalBrowserToken.test.ts \
  src/lib/defaultspackLocalAuth.test.ts \
  src/lib/attachments.test.ts
npm test
npm run lint
npm run build
```

## Completion criteria

A finding is not complete merely because an issue exists. It is complete only when:

- enforcement and UI use the same authoritative state/revision;
- pending, committed, rejected, stale, offline, and ambiguous outcomes are modeled;
- destructive and approval actions are idempotent and audited;
- secrets and untrusted destinations fail closed;
- drafts survive failure and context changes;
- the full task is keyboard, screen-reader, touch, zoom, and localization operable;
- automated tests cover success, failure, stale response, duplicate action, and adversarial input;
- native/browser/device behavior has runtime evidence where static source cannot prove it;
- the corresponding issue acceptance checklist is demonstrably satisfied.
