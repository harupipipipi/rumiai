<!-- docs-i18n-links:start -->
[EN](../../../internals/ecosystem.md) | [JP](./ecosystem.md) | [KR](../../ko/internals/ecosystem.md) | [CN](../../zh-cn/internals/ecosystem.md)
<!-- docs-i18n-links:end -->

# エコシステム.json 仕様

デフォルト パックのルートにある `ecosystem.json` は、パックのコンポーネント構成と関数宣言をカーネルに伝えるマニフェスト ファイルです。

---

## 最上位フィールド

| Field | Type | Description |
|---|---|---|
| `pack_id` | `string` | Unique identifier for the Pack. In defaults pack `"defaults"` |
| `pack_identity` | `string` | Repository identifier for the Pack. Format: `"github:<owner>/<repo>"` |
| `version` | `string` | Semantic versioning. Example: `"1.0.0"` |
| `vocabulary` | `object` | Vocabulary definitions used by Pack |
| `components` | `object` | Map of component definitions |
| `load_order` | `array[string]` | Component loading order |
| `metadata` | `object` | Metadata |

---

## 語彙

`vocabulary` は、パックによって提供される機能の分類を定義します。

### 語彙.タイプ

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

`types` は、Pack によって提供されるコンポーネント タイプのリストです。各タイプは、`components` のエントリの `type` フィールドに対応します。カーネルはこのリストを使用して、パックが提供する機能のカテゴリを理解します。

デフォルト パックでは 11 種類が定義されています: `chat` (会話管理)、`agent` (エージェント実行)、`coding` (コーディング ツール)、`ai_client` (AI プロバイダー管理)、`tool` (ツール管理)、`prompt` (プロンプト管理)、`memory` (メモリ管理)、`knowledge` (ナレッジ管理)、 `media` (メディア処理)、`frontend` (フロントエンド)、`dev` (開発者ツール)。

---

## コンポーネント

`components` は、キーがコンポーネント ID、値がコンポーネント定義であるオブジェクト マップです。

### コンポーネント定義構造

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

| Field | Type | Description |
|---|---|---|
| `type` | `string` | `vocabulary.types` |
| `id` | `string` | Unique ID within the component |
| `path` | `string` | Relative path of the directory where the block file is stored (relative to the Pack root) |
| `connectivity` | `object` | Connectivity definition |
| `connectivity.provides` | `array[string]` | List of handler names provided by this component |

> **注: フロントエンド コンポーネントのパス**
>
> 以前は、`frontend`コンポーネントの`path`が`"ui"`(Packルート直下の`ui/`ディレクトリ)でしたが、`"blocks/frontend"`に変更されました。すべてのコンポーネントは、`blocks/<type>` または `blocks/<id>` パターンに従います。

### connectivity.provides の意味

`provides` 配列にリストされている文字列は、このコンポーネントによって公開されるハンドラー名です。フォーマットは `pack_id.category.action` の 3 セグメント構造に従います。

```
defaults.chat.create_conversation
^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^^^
pack_id  category  action
```

カーネルはこの情報を使用して、`call_handler("defaults.chat.create_conversation", params)` が呼び出されたときにどの Pack のどのコンポーネントを処理する必要があるかを解決します。

### 各コンポーネントの提供リスト

<!-- ハンドラーの総数の内訳: 91:
     チャット=18、エージェント=10、コーディング=12、ai_client=9、ツール=11、
     プロンプト=7、メモリ=5、知識=6、メディア=6、フロントエンド=3、開発=4
-->

**チャット** (18 ハンドラー): `defaults.chat.create_conversation`、`defaults.chat.get_conversation`、`defaults.chat.list_conversations`、`defaults.chat.update_conversation`、`defaults.chat.delete_conversation`、`defaults.chat.export_conversation`、`defaults.chat.send`、`defaults.chat.stream`、`defaults.chat.add_message`、`defaults.chat.get_message`、`defaults.chat.update_message`、`defaults.chat.delete_message`、`defaults.chat.branch`、`defaults.chat.search`、 `defaults.chat.stop`、`defaults.chat.regenerate`、`defaults.chat.summarize_and_trim`、`defaults.chat.auto_trim`**エージェント** (10 ハンドラー): `defaults.agent.execute`、`defaults.agent.approve`、`defaults.agent.reject`、`defaults.agent.cancel`、`defaults.agent.status`、`defaults.agent.plan`、`defaults.agent.add_instruction`、`defaults.agent.multi_execute`、`defaults.agent.multi_status`、 `defaults.agent.multi_message`**coding** (12 ハンドラー): `defaults.coding.file_read`、`defaults.coding.file_write`、`defaults.coding.file_create`、`defaults.coding.file_delete`、`defaults.coding.file_search`、`defaults.coding.file_list`、`defaults.coding.terminal_exec`、`defaults.coding.terminal_stream`、`defaults.coding.git_status`、`defaults.coding.git_diff`、`defaults.coding.git_commit`、 `defaults.coding.git_push`**ai_client** (9 ハンドラー): `defaults.ai.complete`、`defaults.ai.stream`、`defaults.ai.models`、`defaults.ai.providers`、`defaults.ai.embed`、`defaults.ai.image_gen`、`defaults.ai.image_analyze`、`defaults.ai.transcribe`、`defaults.ai.tts`**tool** (11 ハンドラー): `defaults.tool.invoke`、 `defaults.tool.list`、`defaults.tool.schema`、`defaults.tool.mcp_connect`、`defaults.tool.mcp_list`、`defaults.tool.create`、`defaults.tool.update`、`defaults.tool.delete`、`defaults.tool.export`、`defaults.tool.consent_check`、`defaults.tool.consent_confirm`**プロンプト** (7 ハンドラー): `defaults.prompt.render`、`defaults.prompt.list`、`defaults.prompt.create`、 `defaults.prompt.system`、`defaults.prompt.update`、`defaults.prompt.delete`、`defaults.prompt.convert`**メモリ** (5 ハンドラー): `defaults.memory.store`、`defaults.memory.recall`、`defaults.memory.project_context`、`defaults.memory.vector_store`、`defaults.memory.vector_query`**知識** (6 ハンドラー): `defaults.knowledge.create`、`defaults.knowledge.get`、 `defaults.knowledge.list`、`defaults.knowledge.search`、`defaults.knowledge.update`、`defaults.knowledge.delete`**メディア** (6 ハンドラー): `defaults.media.image_read`、`defaults.media.image_transform`、`defaults.media.doc_parse`、`defaults.media.clipboard_read`、`defaults.media.clipboard_write`、`defaults.media.screenshot`**フロントエンド** (3 ハンドラー): `defaults.frontend.start`、`defaults.frontend.stop`、 `defaults.frontend.emit`**dev** (4 ハンドラー): `defaults.dev.inspect`、`defaults.dev.prompt_history`、`defaults.dev.edit_prompt_live`、`defaults.dev.replay`

---

## ロードオーダー

`load_order` は、コンポーネントの初期化順序を定義する配列です。形式は`"type:id"`です。

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

この順序は依存関係に基づいており、前部のコンポーネントは後部のコンポーネントに依存しません。具体的には：

1. **メモリ** — 他のコンポーネントから独立した基盤
2. **知識** — 記憶と同じレベルの基礎。知識の保管と検索を提供します
3. **プロンプト** — 記憶/知識と同じ層ベース
4. **メディア** — 独立した拠点
5. **ai_client** — プロンプトを使用する場合があります
6. **ツール** — ai_client を使用する (AI コード生成、MCP など)
7. **コーディング** — ファイル/端末操作
8. **チャット** — ai_client、プロンプト、メモリを使用する
9. **エージェント** — チャット、ツール、ai_client を使用します (最も依存性が高い)
10. **dev** — エージェント、チャットなどのログを表示する開発者ツール
11. **フロントエンド** — 常に最後です。すべてのコンポーネントの準備ができたら UI を開始します

### カーネルとの対応

カーネルは `load_order` を参照して、パックの初期化中にコンポーネントを順番にロードします。 `"type:id"`の`type`は`vocabulary.types`のいずれかであり、`id`は`components`のキーと一致します。

---

## メタデータ

```json
{
  "metadata": {
    "description": "Default application pack for rumiai - provides chat, agent, coding, AI client, tools, prompts, memory, knowledge, media, and frontend capabilities",
    "author": "harupipipipi",
    "license": "MIT"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `description` | `string` | Pack description |
| `author` | `string` | Author |
| `license` | `string` | License |

---

## 完全な Ecosystem.json の例

デフォルト パックの実際の `ecosystem.json` は `pack_id: "defaults"`、`version: "1.0.0"` であり、11 のコンポーネント (チャット、エージェント、コーディング、ai_client、ツール、プロンプト、メモリ、ナレッジ、メディア、フロントエンド、開発) を定義し、合計 91 のハンドラーを提供します。

<!-- Handler total breakdown: chat(18) + agent(10) + coding(12) + ai_client(9) + tool(11) + prompt(7) + memory(5) + knowledge(6) + media(6) + frontend(3) + dev(4) = 91 -->
