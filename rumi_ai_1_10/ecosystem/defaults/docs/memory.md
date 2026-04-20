# Memory 機能ガイド

## 1. 概要

memory モジュールは defaults の `domain/memory/` に配置されるドメインコードであり、長期メモリの保存・検索、プロジェクトコンテキストの管理、ベクトルストアの操作を handler として提供する。

メモリには2種類ある。プロジェクトメモリはワークスペース単位の永続メモリで、`workspace/.rumi/memory/project.md` にマークダウン形式で保存される。ユーザーメモリはユーザー単位の永続メモリで、`user_data/memory/user.md` に保存される。

短期メモリ（セッション中の会話履歴）は chat モジュールと agent モジュールが管理する。memory モジュールの対象外である。


## 2. store

### defaults.memory.store

メモリにコンテンツを保存する。

権限: `memory.long.write`

input_data:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "content": "新しく学んだ情報...",
  "merge_strategy": "append"
}
```

`memory_type` は `"project"` または `"user"`。`merge_strategy` は `"append"`（末尾に追加）、`"replace"`（全置換）、`"smart"`（AI で既存内容とマージ）から選択。

戻り値:
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

メモリからコンテンツを取得する。

権限: `memory.long.read`, `memory.long.search`

input_data:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "query": "認証の実装方針"
}
```

`query` が空文字の場合はメモリ全文を返す。`query` が指定された場合はメモリ内から関連部分を抽出して返す。

戻り値:
```json
{
  "content": "## 認証の実装方針\nOAuth 2.0 を採用し...",
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "full_content": false
}
```

`full_content` は全文を返したか部分抽出かを示す。


## 4. project context

### defaults.memory.project_context

プロジェクトメモリの全文を取得する。recall の `query` 空文字版のショートカット。

権限: `memory.project.read`

input_data:
```json
{
  "workspace": "/path/to/workspace"
}
```

戻り値:
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

テキストをベクトル化してベクトルストアに保存する。

権限: `memory.vector.store`

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

`content` は自動的にチャンク分割される。`collection` はベクトルストアのコレクション名。`chunk_size` / `chunk_overlap` はチャンク分割のパラメータ。

戻り値:
```json
{
  "success": true,
  "chunks_stored": 5,
  "collection": "default",
  "total_tokens": 1200
}
```

### defaults.memory.vector_query

ベクトル検索でクエリに類似するチャンクを取得する。

権限: `memory.vector.query`

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

`top_k` は返す結果の最大数。`threshold` は類似度の閾値（0.0〜1.0）。`filter` はメタデータによるフィルタ。

戻り値:
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
