<!-- docs-i18n-links:start -->
[EN](./browser_computer_use_optional_design.md) | [JP](./i18n/ja/browser_computer_use_optional_design.md) | [KR](./i18n/ko/browser_computer_use_optional_design.md) | [CN](./i18n/zh-cn/browser_computer_use_optional_design.md)
<!-- docs-i18n-links:end -->

# Browser Computer Use Optional Design

Browser and computer use are optional capabilities.

Operations:

- browser open
- screenshot
- click, type, key, scroll
- extract text
- download
- session save and restore
- window-scoped context and screenshots
- virtual AI cursor for non-disruptive move/click markers
- automatic text/key driver switching:
  - Chrome DOM background entry when explicitly requested
  - foreground keyboard fallback when the user allows overlap
  - normal foreground desktop actions for non-Chrome apps

Network navigation, downloads, and external site interaction require approval and audit. The core catalog describes this capability but does not require any browser provider.
