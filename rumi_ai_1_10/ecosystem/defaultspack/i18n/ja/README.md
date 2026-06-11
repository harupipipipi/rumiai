<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# rumiai_defaults

## 正規の実装

このリポジトリの場合、正規のdefaultspack実装は次のとおりです。
`rumi_ai_1_10/ecosystem/defaultspack/`。

古い `ecosystem/defaults/` パッケージと個別の
`harupipipipi/rumiai_defaults` リポジトリは互換性として扱われるか、
新しいランタイム動作の信頼できるソースとしてではなく、スナップショット ソースとして使用されます。新しい
ハンドラーの実装、ローカルの安全性ポリシー、フロントエンドのルート、モデルのデフォルト、
そして品質チェックは最初に `ecosystem/defaultspack/` に到達する必要があります。レガシー
`defaults.*` 呼び出し元は互換性エイリアスまたは shim を通じて提供される必要があります
これは、defaultspack の動作に委任します。

defaultspack はデフォルトでローカルファーストです。

- 新しいランタイムは `stub/default` で始まります。クラウド モデル プロバイダーはオプトインです。
- コーディング、ターミナル、および git のミューテーションは、ローカル操作としてではなく、ローカル操作として保護されます。
  ユーザーアカウント認証。
- ローカル HTTP の機密性の高い変更には、ループバック アクセス、ローカル オリジン、CSRF が必要です
  オリジンが存在する場合のメタデータ、署名されたワンタイム承認トークン、および
  編集された JSONL 監査レコード。
- Cloudflare、Supabase、ログイン、アカウント作成、ユーザー管理は機能しません
  デフォルトパックのローカル操作保護の範囲。

rumiaiのデフォルトパック。

rumiai 自体は汎用カーネルであり、ドメインの知識はありません。 Defaults は、rumiai エコシステムに「AI サービスとして動作するためのすべてのメカニズム」を提供します。チャット、エージェント、ツール、プロンプト、AI クライアント、コーディング支援、マルチモーダル処理、フロントエンド通信はすべて、デフォルトのハンドラーとドメイン コードを通じて機能します。

ただし、デフォルトは「仕組み」を提供するだけです。具体的な UI、ツール定義、エージェント定義、プロンプト、テーマ、レイアウトはすべて user_data 側に配置されます。デフォルトは、それらを配置する場所と、それらを移動するメカニズムを提供します。

デフォルトだけで既存のAIサービス（ChatGPT / Claude / Cursor / Devin）と真っ向勝負できるレベルの品質を目指す。

---

## 感想

**電池は含まれていますが、すべての電池は取り外し可能です。** デフォルトを含めると、すべての機能が動作します。ただし、任意のコンポーネントを別のパックに置き換えることはできます。**デフォルトは制限ではなく標準を定義します。** デフォルトで定義された権限、ハンドラー、およびドメイン モデルは、rumiai エコシステムの「標準ボキャブラリー」になります。他のパックではこの語彙が使用されます。ただし、この語彙は拡張可能であり、他のパックはデフォルトが知らない概念を追加できます。**すべてを知っており、何も想定しません。** デフォルトには、AI サービスに必要なすべてのドメイン知識が含まれています。ただし、ユーザーの環境、ユースケース、または好みについては想定しません。**信頼ではなく、機能によるセキュリティ。** デフォルトは、rumiai のセキュリティ モデルに完全に従います。デフォルト自体は、付与された権限の範囲内でのみ動作します。**インフラストラクチャのみ、user_data のコンテンツ。** デフォルトは、ドメイン ロジック (ハンドラー)、通信インフラストラクチャ、ウィジェット ライブラリ、シェル、およびフロー定義のみを提供します。画面の外観 (アセット)、ツール定義、エージェント設定、プロンプト、テーマ、レイアウトはすべて user_data に配置されます。デフォルトでは、それらが機能するための API とフレームワークが提供されます。

---

## デフォルトで提供されるもの

- **handler** — call_handler で呼び出すことができるドメイン操作 API。チャット、エージェント、コーディング、AI、ツール、プロンプト、メモリ、メディア ドメインの基本操作。
- **ドメイン コード** — ハンドラーの実装。各ドメインのビジネス ロジック。
- **フロー定義** — simple_chat、agent_chat、planning_agent。デフォルトの処理パイプライン。
- **モデル機能ルーティング** — ビジョン/ツール/思考/速度/知識レベルを確認し、モデル グループ内の実際のモデルを選択します。 Vision Bridge を使用して、画像をサポートしていないモデルに画像コンテキストを渡します。
- **通信インフラストラクチャ** — フロントエンド ハンドラー + トランスポート。 HTTP、stdio、UDS を介した通信。
- **ウィジェット ライブラリ** — lib/rumi_widgets/。バックエンドが UI に描画命令を発行するための Python ヘルパー。
- **シェル** — ui/shell.html。スロット定義 + アセット ローダー + ウィジェット レンダラー。アセットを配置するための空のフレーム。

## まずどこを見るべきか

| Things to do | Places to read |
|---|---|
| I want to search from the docs entrance | `docs/index.md` |
| I want to know the relationship between the overall picture of PR97 and UI/chat/tool/MCP/skill/memory/scheduler/trigger | `docs/defaultspack-explained.md` |
| I want to see the whole picture of AI agent service defaults | `docs/ai_agent_services_feature_catalog.md`, `docs/local_agent_implementation_plan.md` |
| I want to see local priority/approval/safety policy | `docs/local_first_policy.md`, `docs/safety_permission_audit_design.md` |
| I want to see capability / profile / preset in machine readable form | `/api/agent-service/manifest`, `/api/capabilities`, `capabilities/`, `profiles/`, `presets/` |
| I want to start defaultspack on standalone | `docs/getting-started.md` |
| I want to fix the front end of 8766 | `webapp/` |
| I want to see the metadata of rumi_bundle | `docs/rumi_bundle.md` |
| Right bar / Settings / I want to know how to extend chat renderer | `docs/frontend_extensions.md` |
| I want to know the whole picture of AI Agent Service Defaults | `docs/ai_agent_services_feature_catalog.md`, `docs/local_agent_implementation_plan.md` |
| I want to know the design of local-first policy / safety / compact | `docs/local_first_policy.md`, `docs/safety_permission_audit_design.md`, `docs/compact_context_design.md` |
| I want to use capability/profile/preset | `capabilities/`, `profiles/local_agent.profile.yaml`, `presets/local_only_safe.preset.yaml` |
| I want to see the next task of frontend | `docs/frontend_todo.md` |
| I want to see the location of the actual file returned to the browser | `ui/` |
| I want to see the Browser Companion extension | `browser_extensions/rumi_browser_companion/` |
| I want to see the HTTP endpoint | `docs/chat.md`, `transport/http.py` |
| I want to know the startup flow via viewer | `../../docs/rumi_viewer_start.md` |

`webapp/` は、`dont_push_this_file/luxe-chat` に基づいており、`defaultspack` の `/api/chat/...`、`/api/ui/...`、および `/api/health` に接続するスタンドアロン フロントエンド ソースです。 `npm run build`の出力先は`ui/`であり、HTTPサーバーは`/`と`/static/...`で構築されたアセットを配信します。

## AI エージェント サービスのデフォルト

defaultspack には、Codex、Claude Code、ChatGPT Projects、Manus、Genspark、OpenClaw からインスピレーションを得たローカルファーストのビルディング ブロックが含まれています。中心となる契約は次のとおりです。

- コア動作は API キーなしで動作します。
- ファイル、ターミナル、git、メモリ、プロジェクト、コンパクト、アーティファクト、および安全機能は `capabilities/*.capability.yaml` にカタログ化されています。
- API/ネットワーク/ブラウザ/クラウドの統合はオプションのプロバイダーであり、承認ゲート制です。
- `domain/capability/catalog.py` は、機能メタデータをバックエンド ブロックと右側のサイドバーに公開します。
- デフォルトのローカル プロファイルは `profiles/local_agent.profile.yaml` です。

ロードマップについては `docs/local_agent_implementation_plan.md` から始め、右側のサイドバー/ウィジェットのエクスペリエンスについては `docs/ui_agent_experience_design.md` から始めてください。

Genspark、Manus、Cline、Hermes に対するインストール/オンボーディング パリティ チェック用
および OpenClaw については、`docs/competitive_agent_install_eval.md` を参照してください。

## デフォルトでは提供されないもの

- **アセット** — 画面に描画される UI ファイル。チャット画面、エージェント画面、コーディング画面、設定画面はすべてuser_data側に配置されます。
- **ツール定義** — tools.json + handler.py。 user_data/shared/tools/ にあります。
- **エージェント定義** — Agent.json。 user_data/shared/agents/ にあります。
- **プロンプト定義** — user_data/shared/prompts/ にあります。
- **テーマ定義** — theme.yaml。 user_data/主題/にあります。
- **レイアウト定義** —layout.json。 user_data/layouts/ にあります。
- **AI モデル プロファイル** — user_data/shared/ai_models/ にあります。

---

## ツールコンテキスト API

ツールの handler.py に注入されるコンテキストは、汎用プリミティブのみで構成されます。特定のドメイン (チャット、エージェントなど) に固有の API はありません。すべてのドメイン操作は汎用プリミティブの組み合わせによって実現されます。

### 常に注入される (宣言は必要ありません)

| context key | description |
|---|---|
| `call_handler(handler_name, params)` | Call any handler. Can only be executed within the scope of permissions granted by Grant |
| `emit_event(event_type, data)` | Publish an event. handler, Flow trigger, and front end can be received |
| `wait_event(event_type, timeout, filter)` | Wait for an event. Timeout can be specified |
| `emit_widget(widget_json)` | Send Widget JSON to the UI |
| `cancel_check()` | Cancellation confirmation |
| `handler_config` | Settings injected from conditions.json |
| `session` | Session information (session_id, workspace, etc.) |

### 何が宣言され、capability_required で注入されるのか

| capability_id | context key | description | risk |
|---|---|---|---|
| `data_read` | `data_read(path) → str/bytes` | Read file under user_data | Low |
| `data_write` | `data_write(path, content)` | Writing files under user_data | Medium |
| `execute_flow` | `execute_flow(flow_id, input) → FlowResult` | Launch Flow | Medium |
| `shell_exec` | `capability("shell_exec", {...})` | Shell command execution | High |
| `browser_control` | `capability("browser_control", {...})` | Browser operation | High |
| `container_exec` | `capability("container_exec", {...})` | Starting, operating, and destroying Docker containers | High |
| `app_control` | `capability("app_control", {...})` | Host application operation | High |
| `http_request` | `capability("http_request", {...})` | External HTTP communication | Medium |
| `llm_call` | `capability("llm_call", {...})` | In-tool LLM call | Medium |
| `session_state` | `capability("session_state", {...})` | Session state read/write | Low |

### call_handler の仕組み

call_handler は、デフォルトまたはパックで登録された任意のハンドラーを呼び出す汎用ゲートウェイです。

```python
result = context["call_handler"]("defaults.chat.send", {
    "conversation_id": "conv-1",
    "content": "hello"
})
```

呼び出し元ツールの権限を確認し、呼び出されたハンドラーによって要求された権限が含まれていない場合は拒否します。含まれている場合はハンドラを実行し、結果を返します。

チャット操作、エージェントのアクティブ化、メモリの読み取り/書き込み、プロンプトのレンダリングはすべて call_handler 経由で実行できます。 Pack によって新しいハンドラーが追加された場合、ツールは同じ call_handler を使用してそれを呼び出すこともできます。

### Emit_event / wait_event の仕組み

イベントは、システム全体にわたる汎用の通信メカニズムです。

```python
context["emit_event"]("my_tool.done", {"result": "success"})

response = context["wait_event"]("ui.user_response", timeout=30, filter={"id": "popup_1"})
```

フロントエンドのポップアップ表示やツール間の非同期通信、フロートリガーのフックなども同様の仕組みで実現されています。

### container_exec 機能

これは、Docker コンテナーのライフサイクルを操作する汎用機能です。表示オプションが true の場合、仮想フレームバッファがコンテナ内で開始され、スクリーンショットと入力 (クリック、入力、キー、スクロール) が利用可能になります。

```python
container = context["capability"]("container_exec", {
    "action": "create",
    "image": "ubuntu:22.04",
    "options": {"display": True, "memory_limit": "512m"}
})

context["capability"]("container_exec", {
    "action": "exec",
    "container_id": container["id"],
    "command": "ls -la"
})

context["capability"]("container_exec", {
    "action": "screenshot",
    "container_id": container["id"]
})

context["capability"]("container_exec", {
    "action": "input",
    "container_id": container["id"],
    "input_type": "click",
    "x": 500, "y": 300
})

context["capability"]("container_exec", {
    "action": "destroy",
    "container_id": container["id"]
})
```

---

## 権限カタログ

デフォルトでは、権限を rumiai エコシステムの「標準語彙」として定義します。ツール、ハンドラー、およびパックは、付与を使用してこれらのアクセス許可を取得し、操作を実行します。

### 命名規則

`domain.resource.action` 3層のドット分離。ワイルドカード `*` を使用して一度に指定できます。

```
chat.conversation.create     → chat ドメイン、conversation リソース、create アクション
chat.conversation.*          → conversation の全アクション
chat.*                       → chat ドメインの全権限
```

### チャット ドメイン (18 権限)

| Permissions | Description |
|------|------|
| `chat.conversation.create` | Conversation creation |
| `chat.conversation.read` | Conversation reading |
| `chat.conversation.list` | Conversation list |
| `chat.conversation.update` | Conversation update |
| `chat.conversation.delete` | Conversation deleted |
| `chat.conversation.export` | Conversation export |
| `chat.conversation.branch` | Conversation branching |
| `chat.message.send` | Send message |
| `chat.message.read` | Read message |
| `chat.message.edit` | Edit message |
| `chat.message.delete` | Delete message |
| `chat.message.regenerate` | AI response regeneration |
| `chat.message.stream` | Streaming |
| `chat.message.stop` | Stop streaming |
| `chat.attachment.upload` | Upload attachment |
| `chat.attachment.read` | Read attachment |
| `chat.reaction.write` | Reaction |
| `chat.search` | Message search |

### エージェント ドメイン (18 権限)

| Permissions | Description |
|------|------|
| `agent.create` | Agent creation |
| `agent.read` | Agent read |
| `agent.list` | Agent list |
| `agent.update` | Agent update |
| `agent.delete` | Agent deletion |
| `agent.execute` | Agent execution |
| `agent.step.read` | Step reading |
| `agent.step.approve` | Step approval |
| `agent.step.reject` | Step Rejection |
| `agent.cancel` | Cancel execution |
| `agent.pause` | Pause |
| `agent.resume` | Resume |
| `agent.status.read` | Status reading |
| `agent.sub.spawn` | Subagent startup |
| `agent.sub.manage` | Subagent management |
| `agent.plan.read` | Read plan |
| `agent.plan.modify` | Plan change |
| `agent.history.read` | History reading |

### ツールドメイン (13 権限)

| Permissions | Description |
|------|------|
| `tool.invoke` | Tool execution |
| `tool.read` | Tool reading |
| `tool.list` | Tool list |
| `tool.schema.read` | Schema reading |
| `tool.create` | Tool creation |
| `tool.update` | Tool update |
| `tool.delete` | Tool deletion |
| `tool.result.read` | Read execution results |
| `tool.permission.read` | Read permissions |
| `tool.permission.write` | Authorization write |
| `tool.mcp.connect` | MCP server connection |
| `tool.mcp.disconnect` | MCP server disconnection |
| `tool.mcp.list` | MCP tools list |

### プロンプト ドメイン (12 権限)

| Permissions | Description |
|------|------|
| `prompt.create` | Prompt creation |
| `prompt.read` | Prompt reading |
| `prompt.list` | Prompt list |
| `prompt.update` | Prompt update |
| `prompt.delete` | Delete prompt |
| `prompt.render` | Prompt rendering |
| `prompt.variable.read` | Read variable |
| `prompt.variable.write` | Writing variables |
| `prompt.system.read` | Read system prompt |
| `prompt.system.write` | System prompt writing |
| `prompt.import` | Import |
| `prompt.export` | Export |

### ai ドメイン (19 権限)

| Permissions | Description |
|------|------|
| `ai.completion` | Text generation |
| `ai.stream` | Streaming generation |
| `ai.model.list` | Model list |
| `ai.model.read` | Read model information |
| `ai.provider.list` | List of providers |
| `ai.provider.add` | Add provider |
| `ai.provider.remove` | Delete provider |
| `ai.provider.config.read` | Read provider settings |
| `ai.provider.config.write` | Write provider settings |
| `ai.profile.read` | AI profile reading |
| `ai.profile.write` | AI profile writing |
| `ai.profile.list` | Profile list |
| `ai.usage.read` | Read usage |
| `ai.token.count` | Token count |
| `ai.embedding` | Embedding vector generation |
| `ai.image.generate` | Image generation |
| `ai.image.analyze` | Image analysis |
| `ai.audio.transcribe` | Audio transcription |
| `ai.audio.synthesize` | Speech synthesis |

### ファイル ドメイン (18 権限)

| Permissions | Description |
|------|------|
| `file.read` | File read |
| `file.write` | File writing |
| `file.create` | File creation |
| `file.delete` | File deletion |
| `file.move` | File movement |
| `file.copy` | File copy |
| `file.list` | File list |
| `file.search` | File search |
| `file.watch` | File monitoring |
| `file.metadata.read` | Read metadata |
| `file.permission.read` | Read permissions |
| `file.workspace.read` | Workspace Read |
| `file.workspace.write` | Workspace writing |
| `file.system.read` | System file read |
| `file.system.write` | System file writing |
| `file.temp.write` | Temporary file writing |
| `file.archive.read` | Archive reading |
| `file.archive.create` | Archive creation |

### ターミナル ドメイン (11 権限)

| Permissions | Description |
|------|------|
| `terminal.execute` | Command execution |
| `terminal.read` | Read output |
| `terminal.stream` | Streaming output |
| `terminal.session.create` | Session creation |
| `terminal.session.list` | Session list |
| `terminal.session.close` | End session |
| `terminal.interrupt` | Interruption |
| `terminal.env.read` | Read environment variables |
| `terminal.env.write` | Writing environment variables |
| `terminal.cwd.read` | Read current directory |
| `terminal.cwd.write` | Change current directory |

### git ドメイン (15 権限)

| Permissions | Description |
|------|------|
| `git.status` | Status confirmation |
| `git.diff` | Difference display |
| `git.log` | Log display |
| `git.commit` | Commit |
| `git.branch.list` | Branch list |
| `git.branch.create` | Create branch |
| `git.branch.switch` | Branch switching |
| `git.branch.delete` | Branch deletion |
| `git.merge` | Merge |
| `git.push` | Push |
| `git.pull` | Pull |
| `git.stash` | Stash |
| `git.reset` | Reset |
| `git.remote.list` | Remote list |
| `git.remote.manage` | Remote management |

### メモリドメイン (13 権限)

| Permissions | Description |
|------|------|
| `memory.short.read` | Short-term memory read |
| `memory.short.write` | Short-term memory write |
| `memory.long.read` | Long-term memory read |
| `memory.long.write` | Long-term memory write |
| `memory.long.delete` | Long-term memory deletion |
| `memory.long.search` | Long-term memory retrieval |
| `memory.project.read` | Read project memory |
| `memory.project.write` | Project memory write |
| `memory.user.read` | User memory read |
| `memory.user.write` | User memory write |
| `memory.vector.store` | Vector storage |
| `memory.vector.query` | Vector search |
| `memory.clear` | Clear memory |

### メディア ドメイン (12 権限)

| Permissions | Description |
|------|------|
| `media.image.read` | Image reading |
| `media.image.create` | Image creation |
| `media.image.transform` | Image conversion |
| `media.audio.read` | Voice reading |
| `media.audio.create` | Audio creation |
| `media.audio.transcribe` | Audio transcription |
| `media.video.read` | Video reading |
| `media.document.read` | Read document |
| `media.document.parse` | Document analysis |
| `media.clipboard.read` | Clipboard reading |
| `media.clipboard.write` | Clipboard writing |
| `media.screenshot` | Screenshot |

### フロー ドメイン (12 権限)

| Permissions | Description |
|------|------|
| `flow.execute` | Flow execution |
| `flow.read` | Flow reading |
| `flow.list` | Flow list |
| `flow.create` | Flow creation |
| `flow.update` | Flow update |
| `flow.delete` | Flow Delete |
| `flow.status.read` | Read execution status |
| `flow.cancel` | Cancel running Flow |
| `flow.modifier.apply` | Apply Flow Modifier |
| `flow.modifier.list` | Modifier list |
| `flow.context.read` | Flow context read |
| `flow.context.write` | Flow context writing |

### 構成ドメイン (13 権限)

| Permissions | Description |
|------|------|
| `config.read` | Read settings |
| `config.write` | Settings write |
| `config.profile.read` | Profile reading |
| `config.profile.write` | Profile writing |
| `config.profile.list` | Profile list |
| `config.theme.read` | Theme reading |
| `config.theme.write` | Theme writing |
| `config.keybind.read` | Keybind Read |
| `config.keybind.write` | Keybind writing |
| `config.locale.read` | Read locale |
| `config.locale.write` | Locale writing |
| `config.export` | Settings export |
| `config.import` | Settings import |

### ネットドメイン (11 権限)

| Permissions | Description |
|------|------|
| `net.http.request` | HTTP request |
| `net.http.stream` | HTTP Streaming |
| `net.websocket.connect` | WebSocket connection |
| `net.websocket.send` | WebSocket sending |
| `net.dns.resolve` | DNS resolution |
| `net.proxy.read` | Proxy read |
| `net.proxy.write` | Proxy writing |
| `net.allowlist.read` | Read permission list |
| `net.allowlist.write` | Write permission list |
| `net.download` | Download |
| `net.upload` | Upload |

### フロントエンド ドメイン (12 権限)

| Permissions | Description |
|------|------|
| `frontend.render.mount` | Put Asset on the drawing surface |
| `frontend.render.unmount` | Remove from drawing surface |
| `frontend.render.update` | Update drawing content |
| `frontend.message.send` | Backend → drawing surface |
| `frontend.message.receive` | Drawing surface → backend |
| `frontend.message.stream` | Stream data continuously |
| `frontend.asset.register` | Accept Asset Registration |
| `frontend.asset.unregister` | Cancellation of Asset |
| `frontend.asset.list` | List of registered Assets |
| `frontend.layout.read` | Get layout information |
| `frontend.layout.write` | Change/save layout |
| `frontend.theme.read` | Get theme information |

### イベント ドメイン (5 権限)

| Permissions | Description |
|------|------|
| `event.emit` | Event publication |
| `event.subscribe` | Event subscription |
| `event.unsubscribe` | Unsubscribe from event |
| `event.list` | Event list |
| `event.history.read` | Read event history |

### 監査ドメイン (3 つの権限)

| Permissions | Description |
|------|------|
| `audit.read` | Read audit log |
| `audit.search` | Audit log search |
| `audit.export` | Audit log export |

### パック ドメイン (8 権限)

| Permissions | Description |
|------|------|
| `pack.list` | Pack list |
| `pack.read` | Pack reading |
| `pack.install` | Pack installation |
| `pack.remove` | Delete pack |
| `pack.update` | Pack update |
| `pack.approve` | Pack approval |
| `pack.config.read` | Read pack settings |
| `pack.config.write` | Pack settings write |

### シークレット ドメイン (4 つの権限)

| Permissions | Description |
|------|------|
| `secret.read` | Secret read |
| `secret.write` | Secret writing |
| `secret.delete` | Secret deletion |
| `secret.list` | Secret list |

### カーネル ドメイン (5 つの権限)

| Permissions | Description |
|------|------|
| `kernel.status.read` | Read kernel state |
| `kernel.shutdown` | Shutdown |
| `kernel.restart` | Reboot |
| `kernel.health` | Health check |
| `kernel.version` | Version information |

### スケジュール ドメイン (5 権限)

| Permissions | Description |
|------|------|
| `schedule.create` | Schedule creation |
| `schedule.read` | Schedule reading |
| `schedule.update` | Schedule update |
| `schedule.delete` | Delete schedule |
| `schedule.list` | Schedule list |

---

## 権限のプリセット

| Preset | Permissions included | Usage |
|-----------|---------|------|
| `preset.chat_basic` | `chat.conversation.*`, `chat.message.*`, `ai.completion`, `ai.stream` | Basic chat |
| `preset.chat_full` | `preset.chat_basic` + `chat.search`, `chat.attachment.*`, `prompt.*`, `memory.short.*` | Full chat |
| `preset.coding` | `file.workspace.*`, `terminal.*`, `git.*`, `ai.completion`, `ai.stream` | Coding |
| `preset.agent_basic` | `agent.*`, `tool.invoke`, `tool.list`, `tool.schema.read`, `ai.*` | Basic agent |
| `preset.agent_full` | `preset.agent_basic` + `file.*`, `terminal.*`, `net.*`, `memory.*` | Full agent |
| `preset.frontend` | `frontend.*`, `event.*`, `config.read`, `config.theme.*` | Front end |
| `preset.readonly` | `*.read`, `*.list` | Read-only |
| `preset.admin` | `*` (Full privileges) | Administrator |

---

## 独自の権限をデフォルトに設定する

デフォルトは次の権限で動作します。

```yaml
grants:
  - preset.chat_full
  - preset.agent_full
  - preset.coding
  - preset.frontend
  - memory.*
  - media.*
  - flow.*
  - config.*
  - event.*
  - schedule.*
  - audit.read
  - pack.list
  - pack.read
  - kernel.status.read
  - kernel.health
  - kernel.version
```

以下はデフォルトには追加されません。 rumiai CLI または明示的なユーザー操作が必要です。

`secret.write`、`secret.delete`、`kernel.shutdown`、`kernel.restart`、`pack.install`、`pack.remove`、`pack.approve`

---

## ハンドラーシステム

ハンドラーは rumiai の信頼によって承認されています (SHA-256 ハッシュ検証)。デフォルト ハンドラーは、rumiai エコシステム上のすべてのパック、フロー、ツールが call_handler で呼び出すことができる標準 API として機能します。

### ハンドラーの命名規則

`pack_id.category.name`

```
defaults.frontend.start        → defaults パック、frontend カテゴリ、start handler
defaults.coding.file_read      → defaults パック、coding カテゴリ、file_read handler
some_pack.custom.my_handler    → 別パックの handler
```

### デフォルトハンドラーリスト

#### フロントエンド（3 ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.frontend.start` | `frontend.serve`, `frontend.bind`, `frontend.auth.manage` | Start transport (http/stdio/uds) |
| `defaults.frontend.stop` | `frontend.serve` | Stop transport |
| `defaults.frontend.emit` | `frontend.event.emit` | Send events to the front end |

#### チャット（16 ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.chat.create_conversation` | `chat.conversation.create` | Conversation creation |
| `defaults.chat.get_conversation` | `chat.conversation.read` | Conversation data acquisition |
| `defaults.chat.list_conversations` | `chat.conversation.list` | Conversation list |
| `defaults.chat.update_conversation` | `chat.conversation.update` | Conversation metadata update |
| `defaults.chat.delete_conversation` | `chat.conversation.delete` | Conversation deletion |
| `defaults.chat.export_conversation` | `chat.conversation.export` | Conversation export |
| `defaults.chat.send` | `chat.message.send`, `ai.completion` | Message sending + AI response generation |
| `defaults.chat.stream` | `chat.message.stream`, `ai.stream` | Streaming response |
| `defaults.chat.add_message` | `chat.message.send` | Add message (AI no response) |
| `defaults.chat.get_message` | `chat.message.read` | Get message |
| `defaults.chat.update_message` | `chat.message.edit` | Edit message |
| `defaults.chat.delete_message` | `chat.message.delete` | Delete message |
| `defaults.chat.branch` | `chat.conversation.branch` | Conversation branching |
| `defaults.chat.search` | `chat.search` | Message search |
| `defaults.chat.stop` | `chat.message.stop` | Stop streaming |
| `defaults.chat.regenerate` | `chat.message.regenerate`, `ai.completion` | Response regeneration |

#### エージェント（6 ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.agent.execute` | `agent.execute`, `tool.invoke` | Agent execution |
| `defaults.agent.approve` | `agent.step.approve` | Step approval |
| `defaults.agent.reject` | `agent.step.reject` | Step Rejection |
| `defaults.agent.cancel` | `agent.cancel` | Cancel execution |
| `defaults.agent.status` | `agent.status.read` | Status acquisition |
| `defaults.agent.plan` | `agent.plan.read` | Get a plan |

#### コーディング（12ハンドラ）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.coding.file_read` | `file.workspace.read` | File reading |
| `defaults.coding.file_write` | `file.workspace.write` | File writing |
| `defaults.coding.file_create` | `file.create` | File creation |
| `defaults.coding.file_delete` | `file.delete` | File deletion |
| `defaults.coding.file_search` | `file.search` | File search |
| `defaults.coding.file_list` | `file.list` | File list |
| `defaults.coding.terminal_exec` | `terminal.execute` | Command execution |
| `defaults.coding.terminal_stream` | `terminal.stream` | Streaming output |
| `defaults.coding.git_status` | `git.status` | Git status |
| `defaults.coding.git_diff` | `git.diff` | Git diff |
| `defaults.coding.git_commit` | `git.commit` | Git commit |
| `defaults.coding.git_push` | `git.push` | Git push |

#### ai（9ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.ai.complete` | `ai.completion` | Text generation |
| `defaults.ai.stream` | `ai.stream` | Streaming generation |
| `defaults.ai.models` | `ai.model.list` | Model list |
| `defaults.ai.providers` | `ai.provider.list` | List of providers |
| `defaults.ai.embed` | `ai.embedding` | Embedding vector generation |
| `defaults.ai.image_gen` | `ai.image.generate` | Image generation |
| `defaults.ai.image_analyze` | `ai.image.analyze` | Image analysis |
| `defaults.ai.transcribe` | `ai.audio.transcribe` | Audio transcription |
| `defaults.ai.tts` | `ai.audio.synthesize` | Speech synthesis |

#### ツール（5ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.tool.invoke` | `tool.invoke` | Tool execution |
| `defaults.tool.list` | `tool.list` | Tool list |
| `defaults.tool.schema` | `tool.schema.read` | Schema reading |
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP server connection |
| `defaults.tool.mcp_list` | `tool.mcp.list` | MCP tools list |

#### プロンプト（4 ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.prompt.render` | `prompt.render` | Prompt rendering |
| `defaults.prompt.list` | `prompt.list` | Prompt list |
| `defaults.prompt.create` | `prompt.create` | Prompt creation |
| `defaults.prompt.system` | `prompt.system.read`, `prompt.system.write` | System prompt management |

#### メモリ（5ハンドラ）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.memory.store` | `memory.long.write` | Long-term memory storage |
| `defaults.memory.recall` | `memory.long.read`, `memory.long.search` | Long-term memory search/read |
| `defaults.memory.project_context` | `memory.project.read` | Read project memory |
| `defaults.memory.vector_store` | `memory.vector.store` | Vector preservation |
| `defaults.memory.vector_query` | `memory.vector.query` | Vector search |

#### メディア（6 ハンドラー）

| handler | Required permissions | Description |
|---|---|---|
| `defaults.media.image_read` | `media.image.read` | Image reading |
| `defaults.media.image_transform` | `media.image.transform` | Image conversion |
| `defaults.media.doc_parse` | `media.document.parse` | Document analysis |
| `defaults.media.clipboard_read` | `media.clipboard.read` | Clipboard reading |
| `defaults.media.clipboard_write` | `media.clipboard.write` | Clipboard writing |
| `defaults.media.screenshot` | `media.screenshot` | Screenshot |

### ハンドラーを使用した別のパックの例

```yaml
# rumiai-cursor の Flow 定義
# defaults の handler を call_handler で呼ぶだけ

phases:
  - id: boot
    steps:
      - id: start_frontend
        type: handler
        handler: defaults.frontend.start
        params:
          transport: "http"
          port: 0

  - id: main_loop
    steps:
      - id: on_code_request
        type: handler
        handler: defaults.coding.file_read

      - id: custom_sidebar
        type: handler
        handler: cursor.sidebar.render      # Pack 独自の handler

# この Pack の Grant
grants:
  - preset.coding
  - preset.frontend
  - cursor.sidebar.render
```

---

## ファイル構造

```
ecosystem/defaults/
├── README.md                          # 本ドキュメント
├── handlers/
│     └── frontend.py                  # 通信ブリッジ（transport 起動・メッセージ中継）
├── ui/
│     └── shell.html                   # 空の枠 + スロット定義 + Asset ローダー + Widget レンダラー
├── lib/
│     └── rumi_widgets/                # Widget Python ヘルパーライブラリ
│           ├── __init__.py
│           ├── display.py             # Text, CodeBlock, Image, etc.
│           ├── controls.py            # Input, Button, Select, etc.
│           ├── layout.py              # Container, Row, Column, etc.
│           ├── stream.py              # Stream, Indicator
│           └── custom.py              # Custom widget
├── domain/                            # ドメインロジック（handler の実装）
│     ├── chat/                        # chat handler の実装
│     ├── agent/                       # agent handler の実装
│     ├── tool/                        # tool handler の実装
│     ├── prompt/                      # prompt handler の実装
│     ├── ai_client/                   # ai handler の実装
│     ├── coding/                      # coding handler の実装
│     ├── memory/                      # memory handler の実装
│     └── media/                       # media handler の実装
├── flows/                             # デフォルト Flow 定義
│     ├── simple_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     ├── agent_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     └── planning_agent/
│           ├── flow.yaml
│           └── handler.py
├── transport/                         # 通信トランスポート
│     ├── http.py
│     ├── stdio.py
│     └── uds.py
├── bridge/                            # context 変換・ブリッジ
└── docs/                              # 設計ドキュメント
      ├── frontend.md
      ├── agent.md
      ├── ai_client.md
      ├── chat.md
      ├── flow.md
      ├── prompt.md
      ├── tool.md
      ├── widget.md
      ├── theme.md
      ├── architecture_defaults.md
      ├── profiles_and_models.md
      ├── conflict_resolution.md
      ├── ui_and_layout.md
      └── capability/
            └── dependency-resolution.md
```

user_data 側 (セットアップ中にデフォルトで配置されるデフォルトのコンテンツ):

```
user_data/
├── shared/
│     ├── tools/                       # デフォルトツール群
│     ├── agents/                      # デフォルトエージェント定義
│     ├── prompts/                     # デフォルトプロンプト
│     └── ai_models/                   # AI モデルプロファイル
├── assets/                            # デフォルト Asset（chat 画面、agent 画面等）
├── themes/                            # デフォルトテーマ
├── layouts/                           # デフォルトレイアウト
├── chat/                              # 会話データ
├── memory/                            # ユーザーメモリ
└── config.json                        # ユーザー設定
```

---

## ドキュメントリスト

| File | Size | Contents |
|---------|--------|------|
| `docs/index.md` | - | defaultspack docs entrance |
| `docs/defaultspack-explained.md` | - | Overall picture and main flow diagram for PR97 |
| `docs/architecture_defaults.md` | 3.9KB | defaults Overall architecture |
| `docs/agent.md` | 41KB | Agent design |
| `docs/ai_client.md` | 53KB | AI client design |
| `docs/chat.md` | 43KB | Chat module design |
| `docs/flow.md` | 36KB | Flow Engine design |
| `docs/prompt.md` | 32KB | Prompt design |
| `docs/tool.md` | 35KB | Tool module design |
| `docs/frontend.md` | - | Front-end design (scheduled for revision) |
| `docs/widget.md` | - | Widget specifications (newly planned) |
| `docs/theme.md` | - | Theme specifications (newly planned) |
| `docs/profiles_and_models.md` | 3.2KB | AI model profile |
| `docs/conflict_resolution.md` | 3.4KB | Conflict resolution |
| `docs/ui_and_layout.md` | 4.2KB | UI and layout |
| `docs/capability/dependency-resolution.md` | 9.2KB | capability dependency resolution |

---

## 品質目標

デフォルトだけでも、以下と同等以上のユーザー エクスペリエンスを提供します。

- **ChatGPT/Claude** — チャット、マルチモーダル、メモリ
- **Claude Code / Devin** — エージェント、自律コーディング、計画
- **カーソル / ウィンドサーフィン** — コーディング支援、Git 統合、ファイル操作
- **MCP** — 外部ツール連携、プロトコルサポート
- **VS コード拡張機能** — デフォルト ハンドラーを呼び出すパックで実現できます。

これらはすべて、デフォルト ハンドラー + user_data コンテンツ (アセット、ツール、エージェント、プロンプト) の組み合わせによって実現されます。
