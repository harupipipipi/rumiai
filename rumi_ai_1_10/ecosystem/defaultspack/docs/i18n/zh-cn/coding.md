<!-- docs-i18n-links:start -->
[EN](../../coding.md) | [JP](../ja/coding.md) | [KR](../ko/coding.md) | [CN](./coding.md)
<!-- docs-i18n-links:end -->

# 编码功能指南

## 1. 概述

编码模块是放置在默认值`domain/coding/`中的域代码，并提供文件操作、终端执行和 Git 操作的处理程序。这些处理程序由具有`call_handler`的代理和工具调用。

编码模块以工作区中的文件为目标。权限检查会拒绝访问工作区之外的文件。


## 2.文件操作

### defaults.coding.file_read

读取文件的内容。

权限：`file.workspace.read`

输入数据：
```json
{
  "path": "src/main.py",
  "encoding": "utf-8",
  "line_start": 1,
  "line_end": null
}
```

`path` 是相对于工作空间的路径。指定 `line_start` / `line_end` 会导致部分读取。

返回值：
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

覆盖文件的内容。如果该文件不存在，则创建该文件。

权限：`file.workspace.write`

输入数据：
```json
{
  "path": "src/main.py",
  "content": "import os\n...",
  "encoding": "utf-8",
  "create_dirs": true
}
```

如果`create_dirs`为真，中间目录也将被创建。

返回值：
```json
{
  "success": true,
  "path": "src/main.py",
  "size_bytes": 1234
}
```

### defaults.coding.file_create

创建一个新文件。如果存在现有文件，则出错。

权限：`file.create`

输入数据：
```json
{
  "path": "src/new_module.py",
  "content": "# New module\n",
  "create_dirs": true
}
```

返回值：
```json
{
  "success": true,
  "path": "src/new_module.py",
  "size_bytes": 14
}
```

### defaults.coding.file_delete

删除文件。

权限：`file.delete`

输入数据：
```json
{
  "path": "src/old_module.py"
}
```

返回值：
```json
{
  "success": true,
  "path": "src/old_module.py"
}
```

### defaults.coding.file_search

对工作区中的文件执行文本搜索（相当于 grep）。

权限：`file.search`

输入数据：
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

返回值：
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

列出目录的内容。

权限：`file.list`

输入数据：
```json
{
  "path": "src/",
  "recursive": false,
  "include": null,
  "exclude": null
}
```

返回值：
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


## 3. 运行终端

### defaults.coding.terminal_exec

执行命令并等待完成。

权限：`terminal.execute`

输入数据：
```json
{
  "command": "python -m pytest tests/",
  "cwd": null,
  "timeout_ms": 120000,
  "env": {}
}
```

`cwd`是工作目录（简称工作空间根）。 `timeout_ms` 是超时（默认 120000 毫秒 = 2 分钟）。 `env` 是一个附加环境变量。

返回值：
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

运行命令并流输出。

权限：`terminal.stream`

输入数据：
```json
{
  "command": "npm run build",
  "cwd": null,
  "timeout_ms": 300000
}
```

返回值：
```json
{
  "stream_id": "term-001",
  "status": "started"
}
```

输出作为事件`terminal.output`与emit_event一起发出。 `terminal.completed` 事件在完成后被触发。


## 4.Git操作

### defaults.coding.git_status

获取存储库状态。

权限：`git.status`

输入数据：
```json
{}
```

返回值：
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

得到差异。

权限：`git.diff`

输入数据：
```json
{
  "path": null,
  "staged": false,
  "commit": null
}
```

可以使用`path` 限制为特定文件。阶段性差异，`staged` true。与`commit`中提交哈希的差异。

返回值：
```json
{
  "diff": "diff --git a/README.md b/README.md\n...",
  "files_changed": 2,
  "insertions": 15,
  "deletions": 3
}
```

### defaults.coding.git_commit

提交您的更改。

权限：`git.commit`

输入数据：
```json
{
  "message": "feat: add new handler",
  "add_all": true,
  "paths": null
}
```

`add_all` 是真实的自动暂存所有更改。 `paths` 仅暂存特定文件。

返回值：
```json
{
  "success": true,
  "commit_hash": "abc1234",
  "message": "feat: add new handler",
  "files_committed": 3
}
```

### defaults.coding.git_push

推送到远程。

权限：`git.push`

输入数据：
```json
{
  "remote": "origin",
  "branch": null,
  "force": false
}
```

`branch` 省略当前分支。

返回值：
```json
{
  "success": true,
  "remote": "origin",
  "branch": "main",
  "commits_pushed": 1
}
```
