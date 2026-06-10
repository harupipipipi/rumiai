<!-- docs-i18n-links:start -->
[EN](../../memory.md) | [JP](../ja/memory.md) | [KR](../ko/memory.md) | [CN](./memory.md)
<!-- docs-i18n-links:end -->

# 记忆功能使用指南

## 1. 概述

内存模块是放置在默认值`domain/memory/`中的域代码，并提供长期内存存储和检索、项目上下文管理以及作为处理程序的向量存储操作。

记忆有两种类型。项目内存是每个工作区的持久内存，并以 Markdown 格式保存在`workspace/.rumi/memory/project.md`中。用户内存是每个用户的持久内存，存储在`user_data/memory/user.md`中。

短期记忆（会话期间的对话历史记录）由聊天和代理模块管理。它不被内存模块覆盖。


## 2. 商店

### 默认值.内存.存储

将内容存储在内存中。

权限：`memory.long.write`

输入数据：
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "content": "新しく学んだ情報...",
  "merge_strategy": "append"
}
```

`memory_type` 是`"project"` 或`"user"`。对于`merge_strategy`，从`"append"`（添加到末尾）、`"replace"`（完全替换）、`"smart"`（使用 AI 与现有内容合并）中进行选择。

返回值：
```json
{
  "success": true,
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 2500
}
```


## 3.回忆

### defaults.memory.recall

从内存中检索内容。

权威：`memory.long.read`，`memory.long.search`

输入数据：
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "query": "認証の実装方針"
}
```

如果`query`是空字符串，则返回整个内存。如果指定了`query`，则从内存中提取相关部分并将其返回。

返回值：
```json
{
  "content": "## 認証の実装方針\nOAuth 2.0 を採用し...",
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "full_content": false
}
```

`full_content`表示是否返回全文或部分提取。


## 4. 项目背景

### defaults.memory.project_context

获取整个项目内存。 `query` 用于调用的空文本版本快捷方式。

权限：`memory.project.read`

输入数据：
```json
{
  "workspace": "/path/to/workspace"
}
```

返回值：
```json
{
  "content": "# Project Memory\n\n## 技術スタック\nPython + FastAPI...\n\n## 設計方針\n...",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 4500,
  "last_updated": 1771056800000
}
```


## 5.向量存储/查询

### defaults.memory.vector_store

对文本进行矢量化并将其保存到矢量存储中。

权限：`memory.vector.store`

输入数据：
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

`content` 自动分块。 `collection` 是矢量存储集合名称。 `chunk_size` / `chunk_overlap`是块划分的参数。

返回值：
```json
{
  "success": true,
  "chunks_stored": 5,
  "collection": "default",
  "total_tokens": 1200
}
```

### defaults.memory.vector_query

获取与矢量搜索查询类似的块。

权限：`memory.vector.query`

输入数据：
```json
{
  "query": "認証の実装方法",
  "collection": "default",
  "top_k": 5,
  "threshold": 0.7,
  "filter": {}
}
```

`top_k` 是要返回的最大结果数。 `threshold` 是相似性阈值（0.0 到 1.0）。 `filter` 是基于元数据的过滤器。

返回值：
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
