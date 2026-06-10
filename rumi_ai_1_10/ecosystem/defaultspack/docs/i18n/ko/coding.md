<!-- docs-i18n-links:start -->
[EN](../../coding.md) | [JP](../ja/coding.md) | [KR](./coding.md) | [CN](../zh-cn/coding.md)
<!-- docs-i18n-links:end -->

# Coding 기능 가이드

## 1. 개요

coding 모듈은 defaults의 `domain/coding/`에 배치되는 도메인 코드이며, 파일 조작, 터미널 실행, Git 조작의 handler를 제공한다. 이러한 handler는 에이전트나 tool로부터 `call_handler`로 호출된다.

coding 모듈은 작업 공간의 파일을 대상으로합니다. 작업 공간 외부의 파일에 대한 액세스는 권한 검사로 거부됩니다.


## 2. 파일 조작

### defaults.coding.file_read

파일의 내용을 읽습니다.

권한: `file.workspace.read`

input_data:
```json
{
  "path": "src/main.py",
  "encoding": "utf-8",
  "line_start": 1,
  "line_end": null
}
```

`path`는 작업 공간에서 상대 경로입니다. `line_start` / `line_end`를 지정하면 부분 읽기가 된다.

반환값:
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

파일의 내용을 덮어씁니다. 파일이 존재하지 않는 경우는 작성한다.

권한: `file.workspace.write`

input_data:
```json
{
  "path": "src/main.py",
  "content": "import os\n...",
  "encoding": "utf-8",
  "create_dirs": true
}
```

`create_dirs`이 true이면 중간 디렉토리도 작성합니다.

반환값:
```json
{
  "success": true,
  "path": "src/main.py",
  "size_bytes": 1234
}
```

### defaults.coding.file_create

새 파일을 만듭니다. 기존 파일이 있으면 오류.

권한: `file.create`

input_data:
```json
{
  "path": "src/new_module.py",
  "content": "# New module\n",
  "create_dirs": true
}
```

반환값:
```json
{
  "success": true,
  "path": "src/new_module.py",
  "size_bytes": 14
}
```

### defaults.coding.file_delete

파일을 삭제합니다.

권한: `file.delete`

input_data:
```json
{
  "path": "src/old_module.py"
}
```

반환값:
```json
{
  "success": true,
  "path": "src/old_module.py"
}
```

### defaults.coding.file_search

작업 공간의 파일을 텍스트 검색 (grep에 해당)합니다.

권한: `file.search`

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

반환값:
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

디렉토리의 내용을 나열합니다.

권한: `file.list`

input_data:
```json
{
  "path": "src/",
  "recursive": false,
  "include": null,
  "exclude": null
}
```

반환값:
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


## 3. 터미널 실행

### defaults.coding.terminal_exec

명령을 실행하여 완료를 기다립니다.

권한: `terminal.execute`

input_data:
```json
{
  "command": "python -m pytest tests/",
  "cwd": null,
  "timeout_ms": 120000,
  "env": {}
}
```

`cwd`는 작업 디렉토리(생략적으로 작업공간 루트)입니다. `timeout_ms` 는 타임아웃(기본값 120000ms = 2분). `env`는 추가 환경 변수입니다.

반환값:
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

명령을 실행하고 출력을 스트리밍합니다.

권한: `terminal.stream`

input_data:
```json
{
  "command": "npm run build",
  "cwd": null,
  "timeout_ms": 300000
}
```

반환값:
```json
{
  "stream_id": "term-001",
  "status": "started"
}
```

출력은 `terminal.output` 이벤트로 emit_event로 전달됩니다. 완료시 `terminal.completed` 이벤트가 발행됩니다.


## 4. Git 조작

### defaults.coding.git_status

리포지토리의 상태를 가져옵니다.

권한: `git.status`

input_data:
```json
{}
```

반환값:
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

차이를 얻는다.

권한: `git.diff`

input_data:
```json
{
  "path": null,
  "staged": false,
  "commit": null
}
```

`path`에서 특정 파일로 제한 가능. `staged`이 true이고 스테이지된 차이. `commit`에서 커밋 해시와의 차이.

반환값:
```json
{
  "diff": "diff --git a/README.md b/README.md\n...",
  "files_changed": 2,
  "insertions": 15,
  "deletions": 3
}
```

### defaults.coding.git_commit

변경 사항을 커밋합니다.

권한: `git.commit`

input_data:
```json
{
  "message": "feat: add new handler",
  "add_all": true,
  "paths": null
}
```

`add_all` 가 true 로 모든 변경을 자동 스테이지. `paths`에서 특정 파일만 스테이지.

반환값:
```json
{
  "success": true,
  "commit_hash": "abc1234",
  "message": "feat: add new handler",
  "files_committed": 3
}
```

### defaults.coding.git_push

원격으로 푸시합니다.

권한: `git.push`

input_data:
```json
{
  "remote": "origin",
  "branch": null,
  "force": false
}
```

`branch` 생략하고 현재 브랜치.

반환값:
```json
{
  "success": true,
  "remote": "origin",
  "branch": "main",
  "commits_pushed": 1
}
```
