# Coding 機能ガイド

## 1. 概要

coding モジュールは defaults の `domain/coding/` に配置されるドメインコードであり、ファイル操作・ターミナル実行・Git 操作の handler を提供する。これらの handler はエージェントや tool から `call_handler` で呼び出される。

coding モジュールはワークスペース内のファイルを対象とする。ワークスペース外のファイルへのアクセスは権限チェックで拒否される。


## 2. ファイル操作

### defaults.coding.file_read

ファイルの内容を読み取る。

権限: `file.workspace.read`

input_data:
```json
{
  "path": "src/main.py",
  "encoding": "utf-8",
  "line_start": 1,
  "line_end": null
}
```

`path` はワークスペースからの相対パス。`line_start` / `line_end` を指定すると部分読み取りになる。

戻り値:
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

ファイルの内容を上書きする。ファイルが存在しない場合は作成する。

権限: `file.workspace.write`

input_data:
```json
{
  "path": "src/main.py",
  "content": "import os\n...",
  "encoding": "utf-8",
  "create_dirs": true
}
```

`create_dirs` が true の場合、中間ディレクトリも作成する。

戻り値:
```json
{
  "success": true,
  "path": "src/main.py",
  "size_bytes": 1234
}
```

### defaults.coding.file_create

新しいファイルを作成する。既存ファイルがあればエラー。

権限: `file.create`

input_data:
```json
{
  "path": "src/new_module.py",
  "content": "# New module\n",
  "create_dirs": true
}
```

戻り値:
```json
{
  "success": true,
  "path": "src/new_module.py",
  "size_bytes": 14
}
```

### defaults.coding.file_delete

ファイルを削除する。

権限: `file.delete`

input_data:
```json
{
  "path": "src/old_module.py"
}
```

戻り値:
```json
{
  "success": true,
  "path": "src/old_module.py"
}
```

### defaults.coding.file_search

ワークスペース内のファイルをテキスト検索（grep 相当）する。

権限: `file.search`

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

戻り値:
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

ディレクトリの内容を一覧する。

権限: `file.list`

input_data:
```json
{
  "path": "src/",
  "recursive": false,
  "include": null,
  "exclude": null
}
```

戻り値:
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


## 3. ターミナル実行

### defaults.coding.terminal_exec

コマンドを実行して完了を待つ。

権限: `terminal.execute`

input_data:
```json
{
  "command": "python -m pytest tests/",
  "cwd": null,
  "timeout_ms": 120000,
  "env": {}
}
```

`cwd` はワーキングディレクトリ（省略でワークスペースルート）。`timeout_ms` はタイムアウト（デフォルト 120000ms = 2分）。`env` は追加の環境変数。

戻り値:
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

コマンドを実行し、出力をストリーミングする。

権限: `terminal.stream`

input_data:
```json
{
  "command": "npm run build",
  "cwd": null,
  "timeout_ms": 300000
}
```

戻り値:
```json
{
  "stream_id": "term-001",
  "status": "started"
}
```

出力はイベント `terminal.output` として emit_event で送出される。完了時に `terminal.completed` イベントが発行される。


## 4. Git 操作

### defaults.coding.git_status

リポジトリの状態を取得する。

権限: `git.status`

input_data:
```json
{}
```

戻り値:
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

差分を取得する。

権限: `git.diff`

input_data:
```json
{
  "path": null,
  "staged": false,
  "commit": null
}
```

`path` で特定ファイルに限定可能。`staged` が true でステージ済みの差分。`commit` でコミットハッシュとの差分。

戻り値:
```json
{
  "diff": "diff --git a/README.md b/README.md\n...",
  "files_changed": 2,
  "insertions": 15,
  "deletions": 3
}
```

### defaults.coding.git_commit

変更をコミットする。

権限: `git.commit`

input_data:
```json
{
  "message": "feat: add new handler",
  "add_all": true,
  "paths": null
}
```

`add_all` が true で全変更を自動ステージ。`paths` で特定ファイルのみステージ。

戻り値:
```json
{
  "success": true,
  "commit_hash": "abc1234",
  "message": "feat: add new handler",
  "files_committed": 3
}
```

### defaults.coding.git_push

リモートにプッシュする。

権限: `git.push`

input_data:
```json
{
  "remote": "origin",
  "branch": null,
  "force": false
}
```

`branch` 省略で現在のブランチ。

戻り値:
```json
{
  "success": true,
  "remote": "origin",
  "branch": "main",
  "commits_pushed": 1
}
```
