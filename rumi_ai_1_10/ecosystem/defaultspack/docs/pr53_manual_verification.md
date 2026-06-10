<!-- docs-i18n-links:start -->
[EN](./pr53_manual_verification.md) | [JP](./i18n/ja/pr53_manual_verification.md) | [KR](./i18n/ko/pr53_manual_verification.md) | [CN](./i18n/zh-cn/pr53_manual_verification.md)
<!-- docs-i18n-links:end -->

# PR #53 Follow-up Manual Verification

Use the browser UI after starting the defaultspack webapp.

- Narrow width and normal width: the composer `+` menu opens, stays within the viewport, and closes from the backdrop.
- File attachment: selecting a file adds an attachment chip in the composer.
- Slash command: typing `/coding` switches into the coding flow/mode when that command is available.
- Coding footer: branch, workspace root, and selected files are visible in the coding footer.
- Coding footer: target folder can be changed, branches can be selected, and a new branch can be created from the footer.
- Coding `@file`: in `/coding`, type `@README.md` and select the file. The mention remains in the input and a workspace attachment chip/card appears.
- Workspace attachments: sending a selected text file stores the file body in backend user message content; binary or metadata-only attachments remain metadata-only.
- Attachment-only send: attach a text file, leave the text input empty, and send. The message is accepted and the backend user content includes the attachment text.
- Sidebar drag/drop:
  - `tool_toggle` widgets that declare `composer.toggle_chip` become composer chips and can be toggled on/off.
  - `button` widgets that declare `composer.action_button` become composer action chips; safe same-origin `/api/` actions with `requires_approval: false` show their result in preview.
  - `panel` widgets that declare `composer.open_panel` become composer chips and open the matching sidebar panel.
  - `selector` widgets that declare `composer.selector_chip` are accepted as selector chips; current minimal behavior can open a panel/action target.
  - Unsupported widget kinds, missing capabilities, external endpoints, and approval-required actions are ignored or blocked.
- Selected tools: selected tool ids are resolved through `ToolRegistry` before provider tool adaptation; raw strings should not appear in provider `tools`.
