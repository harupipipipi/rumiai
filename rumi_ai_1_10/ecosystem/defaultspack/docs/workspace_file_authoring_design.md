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
