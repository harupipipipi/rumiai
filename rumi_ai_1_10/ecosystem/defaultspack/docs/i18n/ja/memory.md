<!-- docs-i18n-links:start -->
[EN](../../memory.md) | [JP](./memory.md) | [KR](../ko/memory.md) | [CN](../zh-cn/memory.md)
<!-- docs-i18n-links:end -->

# メモリー機能ガイド

## 1. 概要

メモリ モジュールは、デフォルトの `domain/memory/` に配置されるドメイン コードであり、長期メモリの保存と取得、プロジェクト コンテキストの管理、およびハンドラーとしてのベクトル ストア操作を提供します。

記憶には2種類あります。プロジェクト メモリはワークスペースごとの永続メモリであり、`workspace/.rumi/memory/project.md` にマークダウン形式で保存されます。ユーザー メモリは各ユーザーの永続メモリであり、`user_data/memory/user.md` に保存されます。

短期記憶 (セッション中の会話履歴) は、チャット モジュールとエージェント モジュールによって管理されます。メモリモジュールではカバーされません。


##2.ストア

### デフォルト.メモリ.ストア

コンテンツをメモリに保存します。

権限: `memory.long.write`

入力データ:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "content": "新しく学んだ情報...",
  "merge_strategy": "append"
}
```

`memory_type`は`"project"`または`"user"`です。 `merge_strategy`は、`"append"`(末尾に追加)、`"replace"`(完全置換)、`"smart"`(AIによる既存コンテンツとのマージ)から選択します。

戻り値:
```json
{
  "success": true,
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "size_bytes": 2500
}
```


## 3.思い出してください

### デフォルト.メモリ.リコール

メモリからコンテンツを取得します。

典拠: `memory.long.read`、`memory.long.search`

入力データ:
```json
{
  "memory_type": "project",
  "workspace": "/path/to/workspace",
  "query": "認証の実装方針"
}
```

`query` が空の文字列の場合は、メモリ全体を返します。 `query`を指定した場合は該当部分をメモリから抽出して返します。

戻り値:
```json
{
  "content": "## 認証の実装方針\nOAuth 2.0 を採用し...",
  "memory_type": "project",
  "path": "workspace/.rumi/memory/project.md",
  "full_content": false
}
```

`full_content` は、全文が返されるか部分抽出が返されるかを示します。


## 4. プロジェクトのコンテキスト

### デフォルト.メモリ.プロジェクト_コンテキスト

プロジェクトのメモリ全体を取得します。 `query` リコール用の空のテキスト バージョンのショートカット。

権限: `memory.project.read`

入力データ:
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


## 5. ベクトルストア/クエリ

###defaults.memory.vector_store

テキストをベクター化してベクター ストアに保存します。

権限: `memory.vector.store`

入力データ:
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

`content`は自動的にチャンク化されます。 `collection` は、ベクトル ストアのコレクション名です。 `chunk_size` / `chunk_overlap`はチャンク分割用のパラメータです。

戻り値:
```json
{
  "success": true,
  "chunks_stored": 5,
  "collection": "default",
  "total_tokens": 1200
}
```

###defaults.memory.vector_query

ベクトル検索でクエリに似たチャンクを取得します。

権限: `memory.vector.query`

入力データ:
```json
{
  "query": "認証の実装方法",
  "collection": "default",
  "top_k": 5,
  "threshold": 0.7,
  "filter": {}
}
```

`top_k` は、返される結果の最大数です。 `threshold` は類似度のしきい値 (0.0 ～ 1.0) です。 `filter` はメタデータに基づくフィルターです。

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


## 6. Memory2 耐久性のあるバックエンド

この PR は、既存の `MemoryStore` API を壊すことなく、`domain/memory2` を追加し、SQLite + Markdown にミラーリングします。

追加の保存先:

```text
user_data/shared/memory/state.db
user_data/shared/memory/MEMORY.md
user_data/shared/memory/USER.md
user_data/shared/memory/daily/YYYY-MM-DD.md
user_data/shared/memory/DREAMS.md
user_data/shared/memory/wiki/
```

追加のブロック:

```text
defaults.memory.add
defaults.memory.search
defaults.memory.get
defaults.memory.update
defaults.memory.delete
defaults.memory.flush
defaults.memory.status
```
