<!-- docs-i18n-links:start -->
[EN](./memory.md) | [JP](./i18n/ja/memory.md) | [KR](./i18n/ko/memory.md) | [CN](./i18n/zh-cn/memory.md)
<!-- docs-i18n-links:end -->

# Memory function guide

## 1. Overview

The memory module is a domain code placed in `domain/memory/` of defaults, and provides long-term memory storage and retrieval, project context management, and vector store operations as a handler.

There are two types of memory. Project memory is persistent memory for each workspace and is saved in markdown format in `workspace/.rumi/memory/project.md`. User memory is persistent memory for each user and is stored in `user_data/memory/user.md`.

Short-term memory (conversation history during a session) is managed by the chat and agent modules. It is not covered by the memory module.


## 2. store

### defaults.memory.store

Store content in memory.

Permissions: `memory.long.write`

input_data:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "content": "新しく学んだ情報...",
  "merge_strategy": "append"
}
```

`memory_type` is `"project"` or `"user"`. For `merge_strategy`, select from `"append"` (add to end), `"replace"` (complete replacement), `"smart"` (merge with existing content using AI).

Return value:
```json
{
  "success": true,
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 2500
}
```


## 3. recall

### defaults.memory.recall

Retrieve content from memory.

Authority: `memory.long.read`, `memory.long.search`

input_data:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "query": "認証の実装方針"
}
```

If `query` is an empty string, return the entire memory. If `query` is specified, extract the relevant part from memory and return it.

Return value:
```json
{
  "content": "## 認証の実装方針\nOAuth 2.0 を採用し...",
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "full_content": false
}
```

`full_content` indicates whether the full text or partial extraction is returned.


## 4. project context

### defaults.memory.project_context

Get the entire project memory. `query` Empty text version shortcut for recall.

Permissions: `memory.project.read`

input_data:
```json
{
  "workspace": "/path/to/workspace"
}
```

Return value:
```json
{
  "content": "# Project Memory\n\n## 技術スタック\nPython + FastAPI...\n\n## 設計方針\n...",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 4500,
  "last_updated": 1771056800000
}
```


## 5. vector store / query

### defaults.memory.vector_store

Vectorize the text and save it to the vector store.

Permissions: `memory.vector.store`

input_data:
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

`content` is automatically chunked. `collection` is the vector store collection name. `chunk_size` / `chunk_overlap` are parameters for chunk division.

Return value:
```json
{
  "success": true,
  "chunks_stored": 5,
  "collection": "default",
  "total_tokens": 1200
}
```

### defaults.memory.vector_query

Get chunks similar to a query with vector search.

Permissions: `memory.vector.query`

input_data:
```json
{
  "query": "認証の実装方法",
  "collection": "default",
  "top_k": 5,
  "threshold": 0.7,
  "filter": {}
}
```

`top_k` is the maximum number of results to return. `threshold` is the similarity threshold (0.0 to 1.0). `filter` is a filter based on metadata.

Return value:
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
