# Settings Control Center UI Spec

## Layout

```txt
SettingsControlCenter
├─ Header
│  ├─ title
│  ├─ search
│  └─ active profile switcher
├─ Sidebar
│  └─ section nav + status counts
├─ MainPanel
│  └─ cards/forms per section
└─ HelpPanel
   ├─ section explanation
   ├─ setup status
   └─ changed settings summary
```

## Visual density

- Large modal or full settings route.
- Cards grouped by intent.
- Status badges always visible.
- Primary action is obvious.
- Secondary actions are present but less loud.

## Card pattern

```txt
[Title]                         [Status]
Description in one sentence.

Details or current value.

[Primary action] [Secondary action]
```

## Empty states

Bad:

```txt
No provider config.
```

Good:

```txt
Cloudflare is not connected yet.
Connect Cloudflare to let Rumi continue tasks in your Cloudflare account when this computer is offline.

[Connect Cloudflare]
[Configure self-host OAuth]
```

## Copy rules

- Every setting explains why it exists.
- Exact scopes/permissions are shown before OAuth.
- Errors say the next action.
- Internal names live in Advanced details, not primary UI.

## Accessibility

- Sidebar is keyboard navigable.
- Cards have semantic headings.
- Badges are not color-only; include text.
- ESC closes modal only when no nested confirmation is active.
