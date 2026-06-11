<!-- docs-i18n-links:start -->
[EN](./coding.md) | [JP](./i18n/ja/coding.md) | [KR](./i18n/ko/coding.md) | [CN](./i18n/zh-cn/coding.md)
<!-- docs-i18n-links:end -->

# Coding feature guide

## 1. Overview

The coding module is domain code placed in `domain/coding/` of defaults and provides handlers for file operations, terminal execution, and Git operations. These handlers are called by agents and tools with `call_handler`.

The coding module targets files in your workspace. Access to files outside the workspace is denied by permission checks.


## 2. File operations

### defaults.coding.file_read

Read the contents of a file.

Permissions: `file.workspace.read`

input_data:
```json
{
  "path": "src/main.py",
  "encoding": "utf-8",
  "line_start": 1,
  "line_end": null
}
```

`path` is the path relative to the workspace. Specifying `line_start` / `line_end` results in partial reading.

Return value:
```json
{
  "content": "import os\n...",
  "path": "src/main.py",
  "size_bytes": 1234,
  "line_count": 45,
  "encoding": "utf-8"
}
```

### defaults.coding.file_write

Overwrite the contents of the file. Create the file if it does not exist.

Permissions: `file.workspace.write`

input_data:
```json
{
  "path": "src/main.py",
  "content": "import os\n...",
  "encoding": "utf-8",
  "create_dirs": true
}
```

If `create_dirs` is true, intermediate directories will also be created.

Return value:
```json
{
  "success": true,
  "path": "src/main.py",
  "size_bytes": 1234
}
```

### defaults.coding.file_create

Create a new file. Error if there is an existing file.

Permissions: `file.create`

input_data:
```json
{
  "path": "src/new_module.py",
  "content": "# New module\n",
  "create_dirs": true
}
```

Return value:
```json
{
  "success": true,
  "path": "src/new_module.py",
  "size_bytes": 14
}
```

### defaults.coding.file_delete

Delete files.

Permissions: `file.delete`

input_data:
```json
{
  "path": "src/old_module.py"
}
```

Return value:
```json
{
  "success": true,
  "path": "src/old_module.py"
}
```

### defaults.coding.file_search

Perform a text search (equivalent to grep) on files in your workspace.

Permissions: `file.search`

input_data:
```json
{
  "pattern": "def run(",
  "path": "src/",
  "include": "*.py",
  "exclude": "__pycache__",
  "max_results": 50,
  "regex": false
}
```

Return value:
```json
{
  "matches": [
    {
      "path": "src/handler.py",
      "line": 15,
      "content": "def run(params, context):",
      "context_before": ["", "class Handler:"],
      "context_after": ["    result = process(params)"]
    }
  ],
  "total_matches": 3,
  "truncated": false
}
```

### defaults.coding.file_list

List the contents of a directory.

Permissions: `file.list`

input_data:
```json
{
  "path": "src/",
  "recursive": false,
  "include": null,
  "exclude": null
}
```

Return value:
```json
{
  "entries": [
    {"name": "main.py", "type": "file", "size_bytes": 1234},
    {"name": "utils/", "type": "directory"}
  ],
  "path": "src/",
  "total_entries": 2
}
```


## 3. Run terminal

### defaults.coding.terminal_exec

Execute the command and wait for completion.

Permissions: `terminal.execute`

input_data:
```json
{
  "command": "python -m pytest tests/",
  "cwd": null,
  "timeout_ms": 120000,
  "env": {}
}
```

`cwd` is the working directory (workspace root for short). `timeout_ms` is timeout (default 120000ms = 2 minutes). `env` is an additional environment variable.

Return value:
```json
{
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "duration_ms": 3500,
  "timed_out": false
}
```

### defaults.coding.terminal_stream

Run commands and stream output.

Permissions: `terminal.stream`

input_data:
```json
{
  "command": "npm run build",
  "cwd": null,
  "timeout_ms": 300000
}
```

Return value:
```json
{
  "stream_id": "term-001",
  "status": "started"
}
```

The output is emitted as event `terminal.output` with emit_event. A `terminal.completed` event is fired upon completion.


## 4. Git operations

### defaults.coding.git_status

Get the repository status.

Permissions: `git.status`

input_data:
```json
{}
```

Return value:
```json
{
  "branch": "main",
  "ahead": 0,
  "behind": 0,
  "staged": ["src/main.py"],
  "modified": ["README.md"],
  "untracked": ["src/new_file.py"],
  "conflicts": []
}
```

### defaults.coding.git_diff

Get the difference.

Permissions: `git.diff`

input_data:
```json
{
  "path": null,
  "staged": false,
  "commit": null
}
```

Can be limited to specific files with `path`. Staged diff with `staged` true. Difference with commit hash in `commit`.

Return value:
```json
{
  "diff": "diff --git a/README.md b/README.md\n...",
  "files_changed": 2,
  "insertions": 15,
  "deletions": 3
}
```

### defaults.coding.git_commit

Commit your changes.

Permissions: `git.commit`

input_data:
```json
{
  "message": "feat: add new handler",
  "add_all": true,
  "paths": null
}
```

`add_all` is true to autostage all changes. `paths` only stages specific files.

Return value:
```json
{
  "success": true,
  "commit_hash": "abc1234",
  "message": "feat: add new handler",
  "files_committed": 3
}
```

### defaults.coding.git_push

Push to remote.

Permissions: `git.push`

input_data:
```json
{
  "remote": "origin",
  "branch": null,
  "force": false
}
```

`branch` Omit current branch.

Return value:
```json
{
  "success": true,
  "remote": "origin",
  "branch": "main",
  "commits_pushed": 1
}
```
