# Manual and runtime verification matrix

Static analysis is the entry gate. This matrix supplies the evidence static code cannot provide.

## Required viewport and text checks

| Check | Minimum evidence |
|---|---|
| Narrow mobile | 320×568 CSS px and 360×800 CSS px |
| Tablet | portrait and landscape around 768 px |
| Desktop | 1024, 1440, and a wide/high-density layout |
| Short height | primary workflow at ≤500 CSS px height |
| Browser zoom | 200% without two-dimensional scrolling for normal content |
| Reflow/text | 400% or equivalent large-text mode where applicable |
| On-screen keyboard | focused input, validation, submit, and error recovery visible |
| Safe areas | iOS/Android cutout and bottom gesture area |

## Platform coverage

Use the platforms relevant to the changed surface:

- Chromium and Firefox desktop;
- Safari/WebKit where web behavior is shipped;
- Windows, macOS, and Linux for Viewer/defaultspack desktop workflows;
- iOS VoiceOver and Android TalkBack for Rumi Mobile;
- Tauri/WebView behavior for native windows, dialogs, permissions, and external navigation;
- Browser Companion installed, disabled, reloaded, revoked, offline, and bridge-unavailable states.

## Keyboard walkthrough

Record a complete task without a pointer:

1. enter the surface from the previous logical control;
2. reach every required control without excessive Tab stops;
3. operate menus, dialogs, tabs, grids, lists, drag/move alternatives, and editors;
4. cancel and recover from mistakes;
5. complete the primary action;
6. verify focus after insert, delete, move, refresh, error, close, and navigation;
7. verify no global shortcut conflicts in inputs, selects, code editors, contenteditable, IME, and dialogs.

## Screen-reader evidence

Verify at least:

- surface/dialog title and description;
- control names, roles, values, selected/current/expanded/busy/invalid state;
- repeated action context;
- relationships between tabs/panels, labels/fields/errors, grids/cells, lists/items, and status/details;
- loading, result count, mutation success/failure, approval settlement, and dynamic updates announced once;
- decorative images/icons hidden and meaningful images named;
- no raw IDs or implementation payloads as primary speech.

## State matrix

Exercise all applicable states, not only success:

- first load and slow load;
- empty data;
- one item and many items;
- partial/malformed response;
- offline before action and disconnect during action;
- unauthorized/expired/revoked credential;
- validation failure;
- conflict/external update;
- timeout before commit and timeout after commit;
- repeated activation/key repeat;
- retry success and retry failure;
- stale data and reconnect;
- storage denial/quota/corruption;
- deleted/missing target;
- unsupported capability/platform;
- long localization and extreme content.

## Trust and privacy evidence

For links, remote content, approvals, credentials, diagnostics, file attachments, browser/desktop control, QR, and external integrations, attach evidence that:

- normalized target and consequence are shown before authority-bearing action;
- unsafe schemes/origins/private-network targets are blocked or explicitly reviewed;
- credentials and private content do not enter URLs, storage, logs, analytics, diagnostics, screenshots, or clipboard;
- redaction works on failure paths;
- replay, stale settlement, wrong recipient, wrong resource, and duplicate submission fail closed;
- imported/history content does not trigger unapproved network activity.

## Visual evidence

Provide before/after captures for:

- default, hover, focus-visible, pressed/selected, disabled, loading, success, warning, and error;
- empty and dense content;
- narrow and zoomed layouts;
- light/dark/high-contrast modes where supported;
- reduced motion;
- long Japanese and mixed Japanese/Latin/code content.

Inspect alignment, control heights, icon baselines, line length, truncation, scrollbars, sticky/fixed collisions, nested card density, and layout shift.

## Performance evidence

For large lists, canvases, streaming chat/activity, images, and dashboards:

- capture interaction responsiveness and scroll behavior;
- verify async replacement does not reset focus/scroll;
- verify images/fonts/panels do not produce avoidable layout shift;
- verify polling pauses or degrades appropriately when hidden/offline;
- verify no unbounded DOM, event-listener, object-URL, timer, or retained-state growth.

## Evidence block for issues and PRs

```markdown
### Runtime evidence
- Surface/build:
- Platform/browser/device:
- Viewports/zoom/text size:
- Keyboard result:
- Screen-reader result:
- Reduced-motion/high-contrast result:
- Failure/offline/conflict result:
- Trust/privacy result:
- Performance result:
- Screenshots/recording:
- Automated tests:
- Residual risk:
```
