<!-- docs-i18n-links:start -->
[EN](../../memory.md) | [JP](../ja/memory.md) | [KR](./memory.md) | [CN](../zh-cn/memory.md)
<!-- docs-i18n-links:end -->

# 메모리 기능 안내

## 1. 개요

메모리 모듈은 기본값의 `domain/memory/`에 배치되는 도메인 코드로, 핸들러로서 장기 메모리 저장 및 검색, 프로젝트 컨텍스트 관리, 벡터 저장 작업을 제공합니다.

메모리에는 두 가지 유형이 있습니다. 프로젝트 메모리는 각 작업 공간의 영구 메모리이며 `workspace/.rumi/memory/project.md`에 마크다운 형식으로 저장됩니다. 사용자 메모리는 각 사용자를 위한 영구 메모리이며 `user_data/memory/user.md`에 저장됩니다.

단기 기억(세션 중 대화 기록)은 채팅 및 에이전트 모듈에서 관리됩니다. 메모리 모듈로 덮여 있지 않습니다.


## 2. 매장

### defaults.memory.store

콘텐츠를 메모리에 저장합니다.

권한: `memory.long.write`

입력_데이터:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "content": "新しく学んだ情報...",
  "merge_strategy": "append"
}
```

`memory_type`는 `"project"` 또는 `"user"`입니다. `merge_strategy`의 경우 `"append"`(끝에 추가), `"replace"`(완전 대체), `"smart"`(AI를 사용하여 기존 콘텐츠와 병합) 중에서 선택합니다.

반환 값:
```json
{
  "success": true,
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 2500
}
```


## 3. 회상

### defaults.memory.recall

메모리에서 콘텐츠를 검색합니다.

권한: `memory.long.read`, `memory.long.search`

입력_데이터:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "query": "認証の実装方針"
}
```

`query`이 빈 문자열인 경우 전체 메모리를 반환합니다. `query`이 지정된 경우 메모리에서 해당 부분을 추출하여 반환합니다.

반환 값:
```json
{
  "content": "## 認証の実装方針\nOAuth 2.0 を採用し...",
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "full_content": false
}
```

`full_content`은 전체 텍스트 또는 부분 추출이 반환되는지 여부를 나타냅니다.


## 4. 프로젝트 컨텍스트

### defaults.memory.project_context

전체 프로젝트 메모리를 가져옵니다. `query` 회수를 위한 빈 텍스트 버전 바로가기.

권한: `memory.project.read`

입력_데이터:
```json
{
  "workspace": "/path/to/workspace"
}
```

반환 값:
```json
{
  "content": "# Project Memory\n\n## 技術スタック\nPython + FastAPI...\n\n## 設計方針\n...",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 4500,
  "last_updated": 1771056800000
}
```


## 5. 벡터 저장/쿼리

### defaults.memory.Vector_store

텍스트를 벡터화하고 벡터 저장소에 저장합니다.

권한: `memory.vector.store`

입력_데이터:
```json
{
  "content": "保存するテキスト...",
  "metadata": {
    "source": "project.md",
    "section": "技術スタック",
    "timestamp": 1771056800000
  },
  "collection": "default",
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

`content`은 자동으로 청크됩니다. `collection`은 벡터 저장소 컬렉션 이름입니다. `chunk_size` / `chunk_overlap`는 청크 분할을 위한 매개변수입니다.

반환 값:
```json
{
  "success": true,
  "chunks_stored": 5,
  "collection": "default",
  "total_tokens": 1200
}
```

### defaults.memory.Vector_query

벡터 검색을 통해 쿼리와 유사한 청크를 가져옵니다.

권한: `memory.vector.query`

입력_데이터:
```json
{
  "query": "認証の実装方法",
  "collection": "default",
  "top_k": 5,
  "threshold": 0.7,
  "filter": {}
}
```

`top_k`은 반환할 최대 결과 수입니다. `threshold`은 유사성 임계값(0.0~1.0)입니다. `filter`는 메타데이터를 기반으로 한 필터입니다.

반환 값:
```json
{
  "matches": [
    {
      "content": "OAuth 2.0 を採用し、JWT トークンで...",
      "score": 0.92,
      "metadata": {
        "source": "project.md",
        "section": "技術スタック"
      }
    },
    {
      "content": "認証ミドルウェアは FastAPI の Depends で...",
      "score": 0.85,
      "metadata": {
        "source": "auth.py",
        "section": "implementation"
      }
    }
  ],
  "total_matches": 2,
  "collection": "default"
}
```


## 6. Memory2 내구성 있는 백엔드

이 PR은 `domain/memory2`을 추가하고 기존 `MemoryStore` API를 손상하지 않고 SQLite + Markdown에 미러링합니다.

추가 저장 대상:

```text
user_data/shared/memory/state.db
user_data/shared/memory/MEMORY.md
user_data/shared/memory/USER.md
user_data/shared/memory/daily/YYYY-MM-DD.md
user_data/shared/memory/DREAMS.md
user_data/shared/memory/wiki/
```

추가 블록:

```text
defaults.memory.add
defaults.memory.search
defaults.memory.get
defaults.memory.update
defaults.memory.delete
defaults.memory.flush
defaults.memory.status
```
