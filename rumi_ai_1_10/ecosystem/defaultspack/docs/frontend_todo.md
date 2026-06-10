<!-- docs-i18n-links:start -->
[EN](./frontend_todo.md) | [JP](./i18n/ja/frontend_todo.md) | [KR](./i18n/ko/frontend_todo.md) | [CN](./i18n/zh-cn/frontend_todo.md)
<!-- docs-i18n-links:end -->

# defaultspack Frontend TODO

This TODO is a work memo to make the `defaultspack` standalone frontend into a "shell that is extended by the registry" instead of a "UI that the main body knows everything about".

## Done

- Added `/api/ui/catalog`
- Added `/api/ui/settings`
- Added `/api/ui/conversations/{id}/preview`
- Change right sidebar to backend catalog driven
- Change settings modal to schema driven
- Change preview pane to conversation preview API driven
- Added code/image/widget/unknown fallback to chat renderer

## Next

- `chat_renderers` Completely separate metadata and frontend renderer implementations
- Extract dedicated renderer registry for each widget type into `webapp/src/renderers/`
- Generate preview source directly from tool execution event and stream event as well
- Save settings with validation for each section
- Add JSON schema to frontend extension manifest
- Allow item icon of `RightSidebar` to be specified as manifest
- Introducing lazy load of custom renderer bundle
- Make it possible to reuse the same registry contract on the viewer side panel.

## Nice To Have

- scaffold CLI for `user_data/shared/frontend_extensions/`
- manifest watcher with live reload
- widget renderer error boundary
- preview pane pin/tab/split
- settings change history
