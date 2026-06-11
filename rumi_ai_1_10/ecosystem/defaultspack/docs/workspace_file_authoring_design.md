<!-- docs-i18n-links:start -->
[EN](./workspace_file_authoring_design.md) | [JP](./i18n/ja/workspace_file_authoring_design.md) | [KR](./i18n/ko/workspace_file_authoring_design.md) | [CN](./i18n/zh-cn/workspace_file_authoring_design.md)
<!-- docs-i18n-links:end -->

# Workspace File Authoring Design

All paths resolve under a workspace root.

Operations:

- list, read, search, glob
- create, write, patch
- rename, move, delete
- diff preview
- snapshot and restore
- artifact save

Write-like operations return preview metadata and risk classification. Delete, overwrite, and restore require approval.
