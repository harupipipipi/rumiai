# ecosystem.json 仕様

defaults Pack のルートにある `ecosystem.json` は、Pack のコンポーネント構成と機能宣言をカーネルに伝えるためのマニフェストファイルである。

---

## トップレベルフィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `pack_id` | `string` | Pack の一意識別子。defaults Pack では `"defaults"` |
| `pack_identity` | `string` | Pack のリポジトリ識別子。形式: `"github:<owner>/<repo>"` |
| `version` | `string` | セマンティックバージョニング。例: `"1.0.0"` |
| `vocabulary` | `object` | Pack が使用する語彙定義 |
| `components` | `object` | コンポーネント定義のマップ |
| `load_order` | `array[string]` | コンポーネントの読み込み順序 |
| `metadata` | `object` | メタデータ |

---

## vocabulary

`vocabulary` は Pack が提供する機能のカテゴリ分類を定義する。

### vocabulary.types

```json
{
  "vocabulary": {
    "types": [
      "chat",
      "agent",
      "coding",
      "ai_client",
      "tool",
      "prompt",
      "memory",
      "knowledge",
      "media",
      "frontend",
      "dev"
    ]
  }
}
```

`types` は Pack が提供するコンポーネントのタイプ一覧である。各タイプは `components` 内のエントリの `type` フィールドと対応する。カーネルはこの一覧を使って、Pack がどのカテゴリの機能を提供しているかを把握する。

defaults Pack では 11 個のタイプが定義されている: `chat`（会話管理）、`agent`（エージェント実行）、`coding`（コーディングツール）、`ai_client`（AI プロバイダー管理）、`tool`（ツール管理）、`prompt`（プロンプト管理）、`memory`（メモリ管理）、`knowledge`（ナレッジ管理）、`media`（メディア処理）、`frontend`（フロントエンド）、`dev`（開発者ツール）。

---

## components

`components` はキーがコンポーネント ID、値がコンポーネント定義のオブジェクトマップである。

### コンポーネント定義の構造

```json
{
  "chat": {
    "type": "chat",
    "id": "chat",
    "path": "blocks/chat",
    "connectivity": {
      "provides": [
        "defaults.chat.create_conversation",
        "defaults.chat.get_conversation",
        "defaults.chat.list_conversations",
        ...
      ]
    }
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `type` | `string` | `vocabulary.types` のいずれか |
| `id` | `string` | コンポーネント内の一意 ID |
| `path` | `string` | block ファイルが格納されたディレクトリの相対パス（Pack ルートからの相対） |
| `connectivity` | `object` | 接続性定義 |
| `connectivity.provides` | `array[string]` | このコンポーネントが提供する handler 名の一覧 |

> **注記: frontend コンポーネントの path**
>
> 以前は `frontend` コンポーネントの `path` が `"ui"` （Pack ルート直下の `ui/` ディレクトリ）となっていたが、現在は `"blocks/frontend"` に変更済みである。全コンポーネントが `blocks/<type>` または `blocks/<id>` パターンに統一されている。

### connectivity.provides の意味

`provides` 配列に列挙された文字列は、このコンポーネントが公開する handler 名である。形式は `pack_id.category.action` の 3 セグメント構造に従う。

```
defaults.chat.create_conversation
^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^^^
pack_id  category  action
```

カーネルはこの情報を使って、`call_handler("defaults.chat.create_conversation", params)` が呼ばれた際にどの Pack のどのコンポーネントが処理すべきかを解決する。

### 各コンポーネントの provides 一覧

<!-- handler 総数 91 の内訳:
     chat=18, agent=10, coding=12, ai_client=9, tool=11,
     prompt=7, memory=5, knowledge=6, media=6, frontend=3, dev=4
-->

**chat** (18 handlers): `defaults.chat.create_conversation`, `defaults.chat.get_conversation`, `defaults.chat.list_conversations`, `defaults.chat.update_conversation`, `defaults.chat.delete_conversation`, `defaults.chat.export_conversation`, `defaults.chat.send`, `defaults.chat.stream`, `defaults.chat.add_message`, `defaults.chat.get_message`, `defaults.chat.update_message`, `defaults.chat.delete_message`, `defaults.chat.branch`, `defaults.chat.search`, `defaults.chat.stop`, `defaults.chat.regenerate`, `defaults.chat.summarize_and_trim`, `defaults.chat.auto_trim`

**agent** (10 handlers): `defaults.agent.execute`, `defaults.agent.approve`, `defaults.agent.reject`, `defaults.agent.cancel`, `defaults.agent.status`, `defaults.agent.plan`, `defaults.agent.add_instruction`, `defaults.agent.multi_execute`, `defaults.agent.multi_status`, `defaults.agent.multi_message`

**coding** (12 handlers): `defaults.coding.file_read`, `defaults.coding.file_write`, `defaults.coding.file_create`, `defaults.coding.file_delete`, `defaults.coding.file_search`, `defaults.coding.file_list`, `defaults.coding.terminal_exec`, `defaults.coding.terminal_stream`, `defaults.coding.git_status`, `defaults.coding.git_diff`, `defaults.coding.git_commit`, `defaults.coding.git_push`

**ai_client** (9 handlers): `defaults.ai.complete`, `defaults.ai.stream`, `defaults.ai.models`, `defaults.ai.providers`, `defaults.ai.embed`, `defaults.ai.image_gen`, `defaults.ai.image_analyze`, `defaults.ai.transcribe`, `defaults.ai.tts`

**tool** (11 handlers): `defaults.tool.invoke`, `defaults.tool.list`, `defaults.tool.schema`, `defaults.tool.mcp_connect`, `defaults.tool.mcp_list`, `defaults.tool.create`, `defaults.tool.update`, `defaults.tool.delete`, `defaults.tool.export`, `defaults.tool.consent_check`, `defaults.tool.consent_confirm`

**prompt** (7 handlers): `defaults.prompt.render`, `defaults.prompt.list`, `defaults.prompt.create`, `defaults.prompt.system`, `defaults.prompt.update`, `defaults.prompt.delete`, `defaults.prompt.convert`

**memory** (5 handlers): `defaults.memory.store`, `defaults.memory.recall`, `defaults.memory.project_context`, `defaults.memory.vector_store`, `defaults.memory.vector_query`

**knowledge** (6 handlers): `defaults.knowledge.create`, `defaults.knowledge.get`, `defaults.knowledge.list`, `defaults.knowledge.search`, `defaults.knowledge.update`, `defaults.knowledge.delete`

**media** (6 handlers): `defaults.media.image_read`, `defaults.media.image_transform`, `defaults.media.doc_parse`, `defaults.media.clipboard_read`, `defaults.media.clipboard_write`, `defaults.media.screenshot`

**frontend** (3 handlers): `defaults.frontend.start`, `defaults.frontend.stop`, `defaults.frontend.emit`

**dev** (4 handlers): `defaults.dev.inspect`, `defaults.dev.prompt_history`, `defaults.dev.edit_prompt_live`, `defaults.dev.replay`

---

## load_order

`load_order` はコンポーネントの初期化順序を定義する配列である。形式は `"type:id"` である。

```json
{
  "load_order": [
    "memory:memory",
    "knowledge:knowledge",
    "prompt:prompt",
    "media:media",
    "ai_client:ai_client",
    "tool:tool",
    "coding:coding",
    "chat:chat",
    "agent:agent",
    "dev:dev",
    "frontend:frontend"
  ]
}
```

### 順序の意味

依存関係に基づく順序であり、前方のコンポーネントは後方のコンポーネントに依存されない。具体的には:

1. **memory** — 他のコンポーネントに依存しない基盤
2. **knowledge** — memory と同階層の基盤。ナレッジの保存・検索を提供
3. **prompt** — memory / knowledge と同階層の基盤
4. **media** — 独立した基盤
5. **ai_client** — prompt を使用する可能性がある
6. **tool** — ai_client を使用する（AI コード生成、MCP 等）
7. **coding** — ファイル/ターミナル操作
8. **chat** — ai_client, prompt, memory を使用する
9. **agent** — chat, tool, ai_client を使用する（最も依存が多い）
10. **dev** — agent, chat 等のログを参照する開発者ツール
11. **frontend** — 常に最後。すべてのコンポーネントが準備完了してから UI を開始する

### カーネルとの対応

カーネルは `load_order` を参照して Pack の初期化時にコンポーネントを順序通りにロードする。`"type:id"` の `type` は `vocabulary.types` のいずれかであり、`id` は `components` のキーと一致する。

---

## metadata

```json
{
  "metadata": {
    "description": "Default application pack for rumiai - provides chat, agent, coding, AI client, tools, prompts, memory, knowledge, media, and frontend capabilities",
    "author": "harupipipipi",
    "license": "MIT"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `description` | `string` | Pack の説明文 |
| `author` | `string` | 作者 |
| `license` | `string` | ライセンス |

---

## 完全な ecosystem.json の例

defaults Pack の実際の `ecosystem.json` は、`pack_id: "defaults"`, `version: "1.0.0"` で、11 コンポーネント（chat, agent, coding, ai_client, tool, prompt, memory, knowledge, media, frontend, dev）を定義し、合計 91 の handler を provides している。

<!-- handler 総数内訳: chat(18) + agent(10) + coding(12) + ai_client(9) + tool(11) + prompt(7) + memory(5) + knowledge(6) + media(6) + frontend(3) + dev(4) = 91 -->
