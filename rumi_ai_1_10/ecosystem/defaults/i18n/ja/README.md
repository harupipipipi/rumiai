<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# rumiai_defaults

rumiaiのデフォルトパック。

rumiai 自体は汎用カーネルであり、ドメインの知識はありません。 Defaults は、rumiai エコシステムに「AI サービスとして動作するためのすべてのメカニズム」を提供します。チャット、エージェント、ツール、プロンプト、AI クライアント、コーディング支援、マルチモーダル処理、フロントエンド通信はすべて、デフォルトのハンドラーとドメイン コードを通じて機能します。

ただし、デフォルトは「仕組み」を提供するだけです。具体的な UI、ツール定義、エージェント定義、プロンプト、テーマ、レイアウトはすべて user_data 側に配置されます。デフォルトは、それらを配置する場所と、それらを移動するメカニズムを提供します。

デフォルトだけで既存のAIサービス（ChatGPT / Claude / Cursor / Devin）と真っ向勝負できるレベルの品質を目指す。

---

## 感想

**電池は含まれていますが、すべての電池は取り外し可能です。** デフォルトを含めると、すべての機能が動作します。ただし、任意のコンポーネントを別のパックに置き換えることができます。

**デフォルトは制限ではなく標準を定義します。** デフォルトで定義された権限、ハンドラー、およびドメイン モデルは、rumiai エコシステムの「標準語彙」になります。他のパックではこの語彙が使用されます。ただし、この語彙は拡張可能であり、他のパックはデフォルトでは分からない概念を追加できます。

**すべてを知っており、何も想定しません。** デフォルトには、AI サービスに必要なすべてのドメイン知識が含まれています。ただし、ユーザーの環境、ユースケース、または好みについては想定しません。

**信頼ではなく、機能によるセキュリティ。** デフォルトは、rumiai のセキュリティ モデルに完全に従っています。デフォルト自体は、付与された権限の範囲内でのみ動作します。

**インフラストラクチャのみ、user_data のコンテンツ。** デフォルトでは、ドメイン ロジック (ハンドラー)、通信インフラストラクチャ、ウィジェット ライブラリ、シェル、およびフロー定義のみが提供されます。画面の外観 (アセット)、ツール定義、エージェント設定、プロンプト、テーマ、レイアウトはすべて user_data に配置されます。デフォルトでは、それらが機能するための API とフレームワークが提供されます。

---

## デフォルトで提供されるもの

- **handler** — call_handler で呼び出すことができるドメイン操作 API。チャット、エージェント、コーディング、AI、ツール、プロンプト、メモリ、メディア ドメインの基本操作。
- **ドメイン コード** — ハンドラーの実装。各ドメインのビジネス ロジック。
- **フロー定義** — simple_chat、agent_chat、planning_agent。デフォルトの処理パイプライン。
- **通信インフラストラクチャ** — フロントエンド ハンドラー + トランスポート。 HTTP、stdio、UDS を介した通信。
- **ウィジェット ライブラリ** — lib/rumi_widgets/。バックエンドが UI に描画命令を発行するための Python ヘルパー。
- **シェル** — ui/shell.html。スロット定義 + アセット ローダー + ウィジェット レンダラー。アセットを配置するための空のフレーム。

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

|コンテキストキー |説明 |
|---|---|
| `call_handler(handler_name, params)` |任意のハンドラーを呼び出します。 Grant | によって付与された権限の範囲内でのみ実行できます。
| `emit_event(event_type, data)` |イベントを公開します。ハンドラー、フロートリガー、フロントエンドが受信可能 |
| `wait_event(event_type, timeout, filter)` |イベントを待ちます。タイムアウトを指定できる |
| `emit_widget(widget_json)` |ウィジェット JSON を UI に送信する |
| `cancel_check()` |キャンセル確認 |
| `handler_config` | conditions.json から注入された設定 |
| `session` |セッション情報 (session_id、ワークスペースなど) |

### 何が宣言され、capability_required で注入されるのか

|機能 ID |コンテキストキー |説明 |リスク |
|---|---|---|---|
| `data_read` | `data_read(path) → str/bytes` | user_data の下のファイルを読み取り |低い |
| `data_write` | `data_write(path, content)` | user_data の下にファイルを書き込む |中 |
| `execute_flow` | `execute_flow(flow_id, input) → FlowResult` |起動の流れ |中 |
| `shell_exec` | `capability("shell_exec", {...})` |シェルコマンドの実行 |高 |
| `browser_control` | `capability("browser_control", {...})` |ブラウザ操作 |高 |
| `container_exec` | `capability("container_exec", {...})` | Docker コンテナの起動、操作、および破棄 |高 |
| `app_control` | `capability("app_control", {...})` |ホストアプリケーションの操作 |高 |
| `http_request` | `capability("http_request", {...})` |外部HTTP通信 |中 |
| `llm_call` | `capability("llm_call", {...})` |ツール内 LLM 呼び出し |中 |
| `session_state` | `capability("session_state", {...})` |セッション状態の読み取り/書き込み |低い |

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

###container_exec 機能

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

`domain.resource.action` 3層のドット分離。ワイルドカード`*`を使用して一度に指定できます。

```
chat.conversation.create     → chat ドメイン、conversation リソース、create アクション
chat.conversation.*          → conversation の全アクション
chat.*                       → chat ドメインの全権限
```

### チャット ドメイン (18 権限)

|権限 |説明 |
|------|------|
| `chat.conversation.create` |会話の作成 |
| `chat.conversation.read` |会話朗読 |
| `chat.conversation.list` |会話リスト |
| `chat.conversation.update` |会話の更新 |
| `chat.conversation.delete` |会話が削除されました |
| `chat.conversation.export` |会話のエクスポート |
| `chat.conversation.branch` |会話の分岐 |
| `chat.message.send` |メッセージを送る |
| `chat.message.read` |メッセージを読む |
| `chat.message.edit` |メッセージを編集 |
| `chat.message.delete` |メッセージを削除 |
| `chat.message.regenerate` | AI応答再生 |
| `chat.message.stream` |ストリーミング |
| `chat.message.stop` |ストリーミングを停止 |
| `chat.attachment.upload` |添付ファイルをアップロード |
| `chat.attachment.read` |添付ファイルを読む |
| `chat.reaction.write` |反応 |
| `chat.search` |メッセージ検索 |

### エージェント ドメイン (18 権限)

|権限 |説明 |
|------|------|
| `agent.create` |エージェントの作成 |
| `agent.read` |エージェントの読み取り |
| `agent.list` |エージェントリスト |
| `agent.update` |エージェントのアップデート |
| `agent.delete` |エージェントの削除 |
| `agent.execute` |エージェントの実行 |
| `agent.step.read` |ステップ読み取り |
| `agent.step.approve` |ステップの承認 |
| `agent.step.reject` |ステップ拒否 |
| `agent.cancel` |実行をキャンセル |
| `agent.pause` |一時停止 |
| `agent.resume` |履歴書 |
| `agent.status.read` |ステータスの読み取り |
| `agent.sub.spawn` |サブエージェントの起動 |
| `agent.sub.manage` |サブエージェント管理 |
| `agent.plan.read` |計画を読む |
| `agent.plan.modify` |計画変更 |
| `agent.history.read` |歴史を読む |

### ツールドメイン (13 権限)

|権限 |説明 |
|------|------|
| `tool.invoke` |ツールの実行 |
| `tool.read` |ツールの読み取り |
| `tool.list` |ツールリスト |
| `tool.schema.read` |スキーマの読み取り |
| `tool.create` |ツールの作成 |
| `tool.update` |ツールのアップデート |
| `tool.delete` |ツールの削除 |
| `tool.result.read` |実行結果の読み取り |
| `tool.permission.read` |読み取り権限 |
| `tool.permission.write` |認可書き込み |
| `tool.mcp.connect` | MCP サーバー接続 |
| `tool.mcp.disconnect` | MCP サーバーの切断 |
| `tool.mcp.list` | MCPツールリスト |

### プロンプト ドメイン (12 権限)

|権限 |説明 |
|------|------|
| `prompt.create` |プロンプト作成 |
| `prompt.read` |すぐに読む |
| `prompt.list` |プロンプトリスト |
| `prompt.update` |即時更新 |
| `prompt.delete` |プロンプトを削除 |
| `prompt.render` |プロンプトレンダリング |
| `prompt.variable.read` |変数を読み取る |
| `prompt.variable.write` |変数の書き込み |
| `prompt.system.read` |システムプロンプトを読む |
| `prompt.system.write` |システムプロンプトの書き込み |
| `prompt.import` |インポート |
| `prompt.export` |エクスポート |

### ai ドメイン (19 権限)

|権限 |説明 |
|------|------|
| `ai.completion` |テキスト生成 |
| `ai.stream` |ストリーミング生成 |
| `ai.model.list` |モデル一覧 |
| `ai.model.read` |モデル情報を読む |
| `ai.provider.list` |プロバイダーのリスト |
| `ai.provider.add` |プロバイダーを追加 |
| `ai.provider.remove` |プロバイダーの削除 |
| `ai.provider.config.read` |プロバイダー設定の読み取り |
| `ai.provider.config.write` |プロバイダー設定の書き込み |
| `ai.profile.read` | AIプロファイル読み取り |
| `ai.profile.write` | AIプロファイル作成 |
| `ai.profile.list` |プロフィール一覧 |
| `ai.usage.read` |使用法を読む |
| `ai.token.count` |トークン数 |
| `ai.embedding` |埋め込みベクトルの生成 |
| `ai.image.generate` |画像生成 |
| `ai.image.analyze` |画像解析 |
| `ai.audio.transcribe` |音声転写 |
| `ai.audio.synthesize` |音声合成 |

### ファイル ドメイン (18 権限)

|権限 |説明 |
|------|------|
| `file.read` |ファイル読み取り |
| `file.write` |ファイル書き込み |
| `file.create` |ファイルの作成 |
| `file.delete` |ファイルの削除 |
| `file.move` |ファイルの移動 |
| `file.copy` |ファイルコピー |
| `file.list` |ファイルリスト |
| `file.search` |ファイル検索 |
| `file.watch` |ファイル監視 |
| `file.metadata.read` |メタデータの読み取り |
| `file.permission.read` |読み取り権限 |
| `file.workspace.read` |ワークスペース 読み取り |
| `file.workspace.write` |ワークスペースの書き込み |
| `file.system.read` |システムファイルの読み取り |
| `file.system.write` |システムファイルの書き込み |
| `file.temp.write` |一時ファイルの書き込み |
| `file.archive.read` |アーカイブの閲覧 |
| `file.archive.create` |アーカイブの作成 |

### ターミナル ドメイン (11 権限)

|権限 |説明 |
|------|------|
| `terminal.execute` |コマンド実行 |
| `terminal.read` |読み取り出力 |
| `terminal.stream` |ストリーミング出力 |
| `terminal.session.create` |セッションの作成 |
| `terminal.session.list` |セッションリスト |
| `terminal.session.close` |セッションを終了する |
| `terminal.interrupt` |中断 |
| `terminal.env.read` |環境変数を読み取る |
| `terminal.env.write` |環境変数の書き込み |
| `terminal.cwd.read` |現在のディレクトリを読み取る |
| `terminal.cwd.write` |現在のディレクトリを変更する |

### git ドメイン (15 権限)

|権限 |説明 |
|------|------|
| `git.status` |ステータス確認 |
| `git.diff` |差分表示 |
| `git.log` |ログ表示 |
| `git.commit` |コミット |
| `git.branch.list` |支店一覧 |
| `git.branch.create` |ブランチの作成 |
| `git.branch.switch` |ブランチ切り替え |
| `git.branch.delete` |ブランチの削除 |
| `git.merge` |マージ |
| `git.push` |プッシュ |
| `git.pull` |プル |
| `git.stash` |スタッシュ |
| `git.reset` |リセット |
| `git.remote.list` |リモートリスト |
| `git.remote.manage` |リモート管理 |

### メモリドメイン (13 権限)

|権限 |説明 |
|------|------|
| `memory.short.read` |短期記憶の読み取り |
| `memory.short.write` |短期記憶書き込み |
| `memory.long.read` |長期記憶の読み取り |
| `memory.long.write` |長期記憶書き込み |
| `memory.long.delete` |長期記憶の削除 |
| `memory.long.search` |長期記憶の回復 |
| `memory.project.read` |プロジェクトメモリを読み取る |
| `memory.project.write` |プロジェクトメモリ書き込み |
| `memory.user.read` |ユーザーメモリ読み取り |
| `memory.user.write` |ユーザーメモリ書き込み |
| `memory.vector.store` |ベクトルストレージ |
| `memory.vector.query` |ベクトル検索 |
| `memory.clear` |メモリをクリア |

### メディア ドメイン (12 権限)

|権限 |説明 |
|------|------|
| `media.image.read` |画像読み取り |
| `media.image.create` |画像作成 |
| `media.image.transform` |画像変換 |
| `media.audio.read` |音声読み上げ |
| `media.audio.create` |オーディオ作成 |
| `media.audio.transcribe` |音声転写 |
| `media.video.read` |ビデオ読書 |
| `media.document.read` |ドキュメントを読む |
| `media.document.parse` |文書分析 |
| `media.clipboard.read` |クリップボードの読み取り |
| `media.clipboard.write` |クリップボードへの書き込み |
| `media.screenshot` |スクリーンショット |

### フロー ドメイン (12 権限)

|権限 |説明 |
|------|------|
| `flow.execute` |フローの実行 |
| `flow.read` |フローリーディング |
| `flow.list` |フローリスト |
| `flow.create` |フローの作成 |
| `flow.update` |フロー更新 |
| `flow.delete` |フロー削除 |
| `flow.status.read` |実行ステータスの読み取り |
| `flow.cancel` |実行中のフローをキャンセル |
| `flow.modifier.apply` |フローモディファイアを適用 |
| `flow.modifier.list` |修飾子リスト |
| `flow.context.read` |フローコンテキストの読み取り |
| `flow.context.write` |フローコンテキストの書き込み |

### 構成ドメイン (13 権限)

|権限 |説明 |
|------|------|
| `config.read` |設定の読み取り |
| `config.write` |設定書き込み |
| `config.profile.read` |プロフィールの読み取り |
| `config.profile.write` |プロフィール作成 |
| `config.profile.list` |プロフィール一覧 |
| `config.theme.read` |テーマ読書 |
| `config.theme.write` |テーマ執筆 |
| `config.keybind.read` |キーバインド読み取り |
| `config.keybind.write` |キーバインドの書き込み |
| `config.locale.read` |ロケールを読み取る |
| `config.locale.write` |ロケールの書き込み |
| `config.export` |設定のエクスポート |
| `config.import` |設定のインポート |

### ネットドメイン (11 権限)

|権限 |説明 |
|------|------|
| `net.http.request` | HTTPリクエスト |
| `net.http.stream` | HTTPストリーミング |
| `net.websocket.connect` | WebSocket接続 |
| `net.websocket.send` | WebSocket 送信 |
| `net.dns.resolve` | DNS解決 |
| `net.proxy.read` |プロキシ読み取り |
| `net.proxy.write` |代筆 |
| `net.allowlist.read` |読み取り権限リスト |
| `net.allowlist.write` |書き込み権限リスト |
| `net.download` |ダウンロード |
| `net.upload` |アップロード |

### フロントエンド ドメイン (12 権限)

|権限 |説明 |
|------|------|
| `frontend.render.mount` |アセットを描画面に配置する |
| `frontend.render.unmount` |描画面から削除 |
| `frontend.render.update` |描画コンテンツを更新 |
| `frontend.message.send` |バックエンド → 描画面 |
| `frontend.message.receive` |描画面 → バックエンド |
| `frontend.message.stream` |データを継続的にストリーミングする |
| `frontend.asset.register` |資産登録を受け入れる |
| `frontend.asset.unregister` |資産のキャンセル |
| `frontend.asset.list` |登録アセット一覧 |
| `frontend.layout.read` |レイアウト情報の取得 |
| `frontend.layout.write` |レイアウトの変更/保存 |
| `frontend.theme.read` |テーマ情報の取得 |

### イベント ドメイン (5 権限)

|権限 |説明 |
|------|------|
| `event.emit` |イベント掲載 |
| `event.subscribe` |イベントの申し込み |
| `event.unsubscribe` |イベントの購読を解除 |
| `event.list` |イベント一覧 |
| `event.history.read` |イベント履歴を読む |

### 監査ドメイン (3 つの権限)

|権限 |説明 |
|------|------|
| `audit.read` |監査ログを読む |
| `audit.search` |監査ログの検索 |
| `audit.export` |監査ログのエクスポート |

### パック ドメイン (8 権限)

|権限 |説明 |
|------|------|
| `pack.list` |パックリスト |
| `pack.read` |パックの読み取り |
| `pack.install` |パックのインストール |
| `pack.remove` |パックを削除 |
| `pack.update` |パックのアップデート |
| `pack.approve` |パックの承認 |
| `pack.config.read` |パック設定の読み取り |
| `pack.config.write` |パック設定の書き込み |

### シークレット ドメイン (4 つの権限)

|権限 |説明 |
|------|------|
| `secret.read` |秘密の読み取り |
| `secret.write` |秘密の執筆 |
| `secret.delete` |シークレットの削除 |
| `secret.list` |秘密のリスト |

### カーネル ドメイン (5 つの権限)

|権限 |説明 |
|------|------|
| `kernel.status.read` |カーネル状態の読み取り |
| `kernel.shutdown` |シャットダウン |
| `kernel.restart` |再起動 |
| `kernel.health` |健康診断 |
| `kernel.version` |バージョン情報 |

### スケジュール ドメイン (5 権限)

|権限 |説明 |
|------|------|
| `schedule.create` |スケジュール作成 |
| `schedule.read` |読書のスケジュール |
| `schedule.update` |スケジュール更新 |
| `schedule.delete` |スケジュールを削除 |
| `schedule.list` |スケジュール一覧 |

---

## 権限のプリセット

|プリセット |含まれる権限 |使い方 |
|-----------|---------|------|
| `preset.chat_basic` | `chat.conversation.*`、`chat.message.*`、`ai.completion`、`ai.stream` |基本チャット |
| `preset.chat_full` | `preset.chat_basic` + `chat.search`、`chat.attachment.*`、`prompt.*`、`memory.short.*` |フルチャット |
| `preset.coding` | `file.workspace.*`、`terminal.*`、`git.*`、`ai.completion`、`ai.stream` |コーディング |
| `preset.agent_basic` | `agent.*`、`tool.invoke`、`tool.list`、`tool.schema.read`、`ai.*` |基本エージェント |
| `preset.agent_full` | `preset.agent_basic` + `file.*`、`terminal.*`、`net.*`、`memory.*` |フルエージェント |
| `preset.frontend` | `frontend.*`、`event.*`、`config.read`、`config.theme.*` |フロントエンド |
| `preset.readonly` | `*.read`、`*.list` |読み取り専用 |
| `preset.admin` | `*` (完全な権限) |管理者 |

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

§るみ§0§

```
defaults.frontend.start        → defaults パック、frontend カテゴリ、start handler
defaults.coding.file_read      → defaults パック、coding カテゴリ、file_read handler
some_pack.custom.my_handler    → 別パックの handler
```

### デフォルトハンドラーリスト

#### フロントエンド（3 ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.frontend.start` | `frontend.serve`、`frontend.bind`、`frontend.auth.manage` |トランスポートを開始します (http/stdio/uds) |
| `defaults.frontend.stop` | `frontend.serve` |輸送を停止する |
| `defaults.frontend.emit` | `frontend.event.emit` |イベントをフロントエンドに送信する |

#### チャット（16 ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.chat.create_conversation` | `chat.conversation.create` |会話の作成 |
| `defaults.chat.get_conversation` | `chat.conversation.read` |会話データ取得 |
| `defaults.chat.list_conversations` | `chat.conversation.list` |会話リスト |
| `defaults.chat.update_conversation` | `chat.conversation.update` |会話メタデータの更新 |
| `defaults.chat.delete_conversation` | `chat.conversation.delete` |会話の削除 |
| `defaults.chat.export_conversation` | `chat.conversation.export` |会話のエクスポート |
| `defaults.chat.send` | `chat.message.send`、`ai.completion` |メッセージ送信+AI応答生成 |
| `defaults.chat.stream` | `chat.message.stream`、`ai.stream` |ストリーミング応答 |
| `defaults.chat.add_message` | `chat.message.send` |メッセージ追加（AI無応答） |
| `defaults.chat.get_message` | `chat.message.read` |メッセージを取得 |
| `defaults.chat.update_message` | `chat.message.edit` |メッセージを編集 |
| `defaults.chat.delete_message` | `chat.message.delete` |メッセージを削除 |
| `defaults.chat.branch` | `chat.conversation.branch` |会話の分岐 |
| `defaults.chat.search` | `chat.search` |メッセージ検索 |
| `defaults.chat.stop` | `chat.message.stop` |ストリーミングを停止 |
| `defaults.chat.regenerate` | `chat.message.regenerate`、`ai.completion` |応答の再生 |

#### エージェント（6 ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.agent.execute` | `agent.execute`、`tool.invoke` |エージェントの実行 |
| `defaults.agent.approve` | `agent.step.approve` |ステップの承認 |
| `defaults.agent.reject` | `agent.step.reject` |ステップ拒否 |
| `defaults.agent.cancel` | `agent.cancel` |実行をキャンセル |
| `defaults.agent.status` | `agent.status.read` |ステータス取得 |
| `defaults.agent.plan` | `agent.plan.read` |計画を立てる |

####コーディング（12ハンドラ）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.coding.file_read` | `file.workspace.read` |ファイル読み込み |
| `defaults.coding.file_write` | `file.workspace.write` |ファイル書き込み |
| `defaults.coding.file_create` | `file.create` |ファイルの作成 |
| `defaults.coding.file_delete` | `file.delete` |ファイルの削除 |
| `defaults.coding.file_search` | `file.search` |ファイル検索 |
| `defaults.coding.file_list` | `file.list` |ファイルリスト |
| `defaults.coding.terminal_exec` | `terminal.execute` |コマンド実行 |
| `defaults.coding.terminal_stream` | `terminal.stream` |ストリーミング出力 |
| `defaults.coding.git_status` | `git.status` | Git ステータス |
| `defaults.coding.git_diff` | `git.diff` | Git の差分 |
| `defaults.coding.git_commit` | `git.commit` | Git コミット |
| `defaults.coding.git_push` | `git.push` | Git プッシュ |

#### ai（9ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.ai.complete` | `ai.completion` |テキスト生成 |
| `defaults.ai.stream` | `ai.stream` |ストリーミング生成 |
| `defaults.ai.models` | `ai.model.list` |モデル一覧 |
| `defaults.ai.providers` | `ai.provider.list` |プロバイダーのリスト |
| `defaults.ai.embed` | `ai.embedding` |埋め込みベクトルの生成 |
| `defaults.ai.image_gen` | `ai.image.generate` |画像生成 |
| `defaults.ai.image_analyze` | `ai.image.analyze` |画像解析 |
| `defaults.ai.transcribe` | `ai.audio.transcribe` |音声転写 |
| `defaults.ai.tts` | `ai.audio.synthesize` |音声合成 |

####ツール（5ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.tool.invoke` | `tool.invoke` |ツールの実行 |
| `defaults.tool.list` | `tool.list` |ツールリスト |
| `defaults.tool.schema` | `tool.schema.read` |スキーマの読み取り |
| `defaults.tool.mcp_connect` | `tool.mcp.connect` | MCP サーバー接続 |
| `defaults.tool.mcp_list` | `tool.mcp.list` | MCPツールリスト |

#### プロンプト（4 ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.prompt.render` | `prompt.render` |プロンプトレンダリング |
| `defaults.prompt.list` | `prompt.list` |プロンプトリスト |
| `defaults.prompt.create` | `prompt.create` |プロンプト作成 |
| `defaults.prompt.system` | `prompt.system.read`、`prompt.system.write` |システムプロンプト管理 |

####メモリ（5ハンドラ）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.memory.store` | `memory.long.write` |長期記憶保存 |
| `defaults.memory.recall` | `memory.long.read`、`memory.long.search` |長期記憶の検索/読み取り |
| `defaults.memory.project_context` | `memory.project.read` |プロジェクトメモリを読み取る |
| `defaults.memory.vector_store` | `memory.vector.store` |ベクトルの保存 |
| `defaults.memory.vector_query` | `memory.vector.query` |ベクトル検索 |

#### メディア（6 ハンドラー）

|ハンドラー |必要な権限 |説明 |
|---|---|---|
| `defaults.media.image_read` | `media.image.read` |画像読み取り |
| `defaults.media.image_transform` | `media.image.transform` |画像変換 |
| `defaults.media.doc_parse` | `media.document.parse` |文書分析 |
| `defaults.media.clipboard_read` | `media.clipboard.read` |クリップボードの読み取り |
| `defaults.media.clipboard_write` | `media.clipboard.write` |クリップボードへの書き込み |
| `defaults.media.screenshot` | `media.screenshot` |スクリーンショット |

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

|ファイル |サイズ |目次 |
|---------|--------|------|
| `docs/architecture_defaults.md` | 3.9KB |全体的なアーキテクチャ | デフォルト
| `docs/agent.md` | 41KB |エージェントの設計 |
| `docs/ai_client.md` | 53KB | AIクライアント設計 |
| `docs/chat.md` | 43KB |チャットモジュールの設計 |
| `docs/flow.md` | 36KB |フローエンジン設計 |
| `docs/prompt.md` | 32KB |即時設計 |
| `docs/tool.md` | 35KB |ツールモジュールの設計 |
| `docs/frontend.md` | - |フロントエンド設計（見直し予定） |
| `docs/widget.md` | - |ウィジェット仕様（新規予定） |
| `docs/theme.md` | - |テーマ仕様（新規予定）｜
| `docs/profiles_and_models.md` | 3.2KB | AIモデルプロフィール |
| `docs/conflict_resolution.md` | 3.4KB |紛争解決 |
| `docs/ui_and_layout.md` | 4.2KB | UIとレイアウト |
| `docs/capability/dependency-resolution.md` | 9.2KB |機能の依存関係の解決 |

---

## 品質目標

デフォルトだけでも、以下と同等以上のユーザー エクスペリエンスを提供します。

- **ChatGPT/Claude** — チャット、マルチモーダル、メモリ
- **Claude Code / Devin** — エージェント、自律コーディング、計画
- **カーソル / ウィンドサーフィン** — コーディング支援、Git 統合、ファイル操作
- **MCP** — 外部ツール連携、プロトコルサポート
- **VS コード拡張機能** — デフォルト ハンドラーを呼び出すパックで実現できます。

これらはすべて、デフォルト ハンドラー + user_data コンテンツ (アセット、ツール、エージェント、プロンプト) の組み合わせによって実現されます。
