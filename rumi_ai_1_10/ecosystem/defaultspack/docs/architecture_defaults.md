
```markdown
# defaults アーキテクチャ設計書

## 1. defaults とは何か

defaults は rumiai のセットアップ時に自動インストールされるベースパックである。rumiai 本体がドメイン知識を持たない汎用カーネルであるのに対し、defaults は AI サービスとして必要な「仕組み」を全て提供する。

defaults が提供するのは仕組みだけである。仕組みとは、チャットができる場所、エージェントが動く場所、ツールが実行される場所、プロンプトがレンダリングされる場所、UI が描画される場所を意味する。これらの場所に何を置くかは user_data が決める。

defaults 自身はチャット画面を持たない。エージェントの定義を持たない。ツールの実体を持たない。プロンプトのテンプレートを持たない。UI のコンポーネントを持たない。defaults が持つのは、それらを動かすための handler、権限、Flow、ドメインコード、通信レイヤーである。

## 2. 設計原則

### 仕組みだけ提供し、中身は全て user_data

defaults は「何ができるか」を定義し、「何をするか」は定義しない。

handler はドメイン操作の実行基盤である。`defaults.chat.send` は「メッセージを送信する仕組み」を提供する。どの会話に何を送るかは呼び出し側（tool、Flow、Pack）が決める。

権限カタログは操作の許可体系である。`chat.message.send` は「メッセージ送信が許可されうる」ことを定義する。誰に許可するかは Grant で決まる。

Flow は処理パイプラインの実行基盤である。`simple_chat` Flow は「ユーザー入力→コンテキスト構築→LLM呼び出し→応答保存」の骨格を提供する。どのモデルを使うか、どのプロンプトを適用するかは Flow の config と user_data の設定が決める。

フロントエンドは描画の枠を提供する。shell.html はスロット（main、sidebar、panel 等）を定義する空の枠である。何をどのスロットに描画するかは Asset として登録されたものが決める。

### Batteries Included, But Every Battery Is Removable

defaults を入れれば AI サービスとして必要な全ての仕組みが動く。しかし任意の仕組みを別パックで置き換えられる。handler は同名で上書き可能。Flow は replaces で差し替え可能。権限は拡張可能。フロントエンドの Asset は同一 ID で上書き可能。

### Defaults Defines the Standard, Not the Limit

defaults が定義する権限・handler・ドメインモデル・Widget 型・Asset 形式は rumiai ecosystem の標準語彙になる。他のパックはこの語彙を使う。しかしこの語彙は拡張可能であり、defaults が知らない権限ドメイン、知らない handler カテゴリ、知らない Widget 型を他のパックが追加できる。

### Know Everything, Assume Nothing

defaults は AI サービスに必要なドメイン知識（チャット、エージェント、ツール、プロンプト、AI クライアント、コーディング、メモリ、メディア）を全て知っている。しかしユーザーの環境、ユースケース、好みについて何も仮定しない。全てが設定可能であり、全てが上書き可能である。

### Security by Capability, Not by Trust

defaults 自身が rumiai の承認プロセスの対象である。defaults のコードは SHA-256 ハッシュ検証で承認され、Grant で許可された権限の範囲内でのみ動作する。defaults が特別扱いされることはない。

### 特化禁止

defaults は特定のユースケースに特化した仕組みを作らない。マルチエージェント専用 API、ナレッジ検索専用 API、スケジューラ専用 API のようなものは作らない。汎用的なプリミティブ（handler 呼び出し、イベント発行、データ読み書き、Flow 実行）を提供し、それらの組み合わせの結果として任意のユースケースが実現できるようにする。

## 3. アーキテクチャ

```
rumiai (コンパイル済みバイナリ)
│   カーネル: Flow 実行, 承認ゲート, Docker 隔離, Trust + Grant, 監査ログ
│
├── ecosystem/defaults/          ← 仕組みを提供
│     ├── handlers/              ← handler（ドメイン操作の実行基盤）
│     ├── flows/                 ← Flow（処理パイプラインの骨格）
│     ├── domain/                ← ドメインコード（chat, agent, tool 等の内部ロジック）
│     ├── transport/             ← 通信レイヤー（http, stdio, uds）
│     ├── bridge/                ← カーネル context ラッパー
│     ├── ui/
│     │     └── shell.html       ← フロントエンドの空の枠（スロット + Widget レンダラー）
│     ├── lib/
│     │     └── rumi_widgets/    ← Widget Python ヘルパー
│     └── docs/                  ← 設計ドキュメント
│
└── user_data/                   ← 中身を提供
      ├── shared/
      │     ├── tools/           ← ツール定義（handler.py + schema.json + ...）
      │     ├── agents/          ← エージェント定義（agent.json）
      │     ├── prompts/         ← プロンプト定義
      │     ├── ai_models/       ← AI モデルプロファイル
      │     └── flows/           ← ユーザー定義 Flow
      ├── packs/                 ← インストールされたパック
      │     └── {pack_id}/
      │           ├── tools/
      │           ├── agents/
      │           ├── prompts/
      │           ├── assets/    ← UI Asset（*.asset.yaml + HTML/JS）
      │           └── flows/
      ├── chat/                  ← 会話データ
      ├── memory/                ← ユーザーメモリ
      ├── config.json            ← 全体設定
      ├── layout/                ← レイアウト設定
      └── themes/                ← テーマ
```

### defaults が持つもの

handler（58個）。chat、agent、tool、prompt、ai、coding、memory、media、frontend の各カテゴリ。全ての handler は汎用的な操作基盤であり、具体的な中身の知識を持たない。

Flow（3個）。simple_chat、agent_chat、planning_agent。処理パイプラインの骨格のみを定義し、具体的なモデル選択やプロンプト適用は Flow config と user_data に委譲する。

権限カタログ（20ドメイン）。chat、agent、tool、prompt、ai、file、terminal、git、memory、media、flow、config、net、frontend、event、audit、pack、secret、kernel。全パックが共通で使う標準語彙。

ドメインコード。chat store、agent loop、tool executor、prompt renderer、ai_client、context builder 等の内部ロジック。これらは handler から呼ばれ、直接外部に露出しない。

フロントエンドの枠。shell.html（スロット定義 + Asset ローダー + Widget レンダラー + メッセージディスパッチ）。具体的な UI コンポーネントは持たない。

通信レイヤー。http、stdio、uds の3つの transport。どれを使うかは設定で選択する。

Widget ヘルパーライブラリ。rumi_widgets。バックエンドの handler や tool が Widget JSON を構築するための Python ヘルパー。使用は任意であり、直接 dict を返しても等価。

### defaults が持たないもの

具体的な UI コンポーネント（チャット画面、エージェントパネル、コードエディタ等）。これらは user_data のパックが Asset として提供する。

具体的なツール定義（file_read、bash、web_search 等）。これらは user_data/shared/tools/ に配置される。

具体的なエージェント定義（coding_assistant、research_agent 等）。これらは user_data/shared/agents/ に配置される。

具体的なプロンプトテンプレート。これらは user_data/shared/prompts/ に配置される。

具体的な AI モデルプロファイル。これらは user_data/shared/ai_models/ に配置される。

テーマ定義。これらは user_data/themes/ に配置される。

レイアウト定義。これらは user_data/layout/ に配置される。

## 4. tool の context API

tool は defaults が提供する仕組みの最も重要な消費者である。tool の handler.py に注入される context API は汎用プリミティブのみで構成される。特定のドメインに特化した API は存在しない。

### 常に注入される（宣言不要）

`context["call_handler"](handler_name, params)` は任意の handler を呼び出す。Grant で許可された権限の範囲内でのみ実行可能。呼び出し先 handler が要求する権限を呼び出し元が保持していなければ PermissionError で拒否される。これにより tool は chat 操作、agent 起動、prompt レンダリング、memory 読み書き、全てを同じプリミティブで行える。

`context["emit_event"](event_type, data)` はイベントを発行する。他の handler、Flow のイベントトリガー、フロントエンドの Asset がこのイベントを受信できる。発行側は受信者を知らない。

`context["wait_event"](event_type, timeout, filter)` はイベントを待つ。指定したイベントタイプが発行されるまでブロックする。タイムアウト指定可能。フィルタで条件を絞れる。emit_event と組み合わせることで、フロントエンドへのポップアップ表示→ユーザー応答待ち、tool 間の非同期通信、Flow トリガーのフック等が全て実現される。

`context["emit_widget"](widget_json)` は Widget JSON を UI に送出する。フロントエンドの Widget レンダラーが描画する。

`context["cancel_check"]()` はキャンセル確認。ユーザーがキャンセルした場合に CancelledError を送出する。

`context["handler_config"]` は conditions.json の behavior_variants から注入された設定。

`context["session"]` はセッション情報（session_id、workspace 等）。

### capability として宣言して注入されるもの

`data_read` は user_data 配下のファイル読み取り。`context["data_read"](path)` でアクセスする。パスは user_data/ からの相対パス。

`data_write` は user_data 配下のファイル書き込み。`context["data_write"](path, content)` でアクセスする。

`execute_flow` は Flow の起動。`context["execute_flow"](flow_id, input)` でアクセスする。Flow Engine 経由で実行される。

`shell_exec` はシェルコマンド実行。`context["capability"]("shell_exec", {...})` でアクセスする。

`browser_control` はブラウザ操作。`context["capability"]("browser_control", {...})` でアクセスする。

`container_exec` は Docker コンテナの起動・操作・破棄。`context["capability"]("container_exec", {...})` でアクセスする。display オプションで GUI 環境（Xvfb + VNC）を起動し、screenshot と input（click, type, key, scroll）で座標ベースの画面操作が可能。

`app_control` はホストアプリ操作。`context["capability"]("app_control", {...})` でアクセスする。

`http_request` は外部 HTTP 通信。`context["capability"]("http_request", {...})` でアクセスする。

`llm_call` はツール内 LLM 呼び出し。`context["capability"]("llm_call", {...})` でアクセスする。

`session_state` はセッション状態読み書き。`context["capability"]("session_state", {...})` でアクセスする。

### なぜ特化 API を作らないか

`context["chat"]` や `context["agent"]` のようなドメイン特化 API を作ると、新しいドメインが追加されるたびに context API を拡張する必要がある。これは defaults の設計原則「特化禁止」に反する。

代わりに `call_handler` という単一の汎用ゲートウェイを提供する。chat 操作は `call_handler("defaults.chat.send", {...})` で行う。agent 起動は `call_handler("defaults.agent.execute", {...})` で行う。新しいパックが新しい handler を定義すれば、tool は同じ `call_handler` でそれを呼び出せる。context API の変更は不要。

同様に、フロントエンドへの通知、ユーザーへの確認、定期実行の登録、全てが `emit_event` / `wait_event` / `execute_flow` の汎用プリミティブで実現される。これらのプリミティブ自体が変わることはほぼなく、その上に乗る handler と Flow が拡張される。

## 5. フロントエンドの仕組み

### defaults が提供するもの

shell.html のみ。shell.html は以下の機能を持つ空の枠である。

スロット定義。header、sidebar.left、main、panel.bottom、sidebar.right、statusbar、floating の7つのスロットを定義する。スロットは Asset が配置される場所であり、スロット自体は何も描画しない。

Asset ローダー。`asset.register` メッセージを受け取ると、Asset の HTML ファイルを iframe で読み込み、指定されたスロットに配置する。Asset が何であるか（チャット画面か、ファイルツリーか、ダッシュボードか）は知らない。

Widget レンダラー。バックエンドから送出された Widget JSON を受け取り、テーマに従って HTML に変換する。Widget の型（Text、CodeBlock、Image 等）ごとにレンダリングロジックを持つ。テーマが Widget の見た目を決める。

メッセージディスパッチ。バックエンドからのメッセージを `asset_id` で振り分け、該当する iframe に転送する。iframe からのメッセージをバックエンドに転送する。データの中身は解釈しない。

### defaults が提供しないもの

チャット画面の HTML/JS/CSS。エージェントパネルの HTML/JS/CSS。コードエディタの HTML/JS/CSS。設定画面の HTML/JS/CSS。これらは全て user_data のパックが Asset として提供する。

### Asset の登録形式

Asset は UI に配置されるブロックの単位である。Asset は asset.yaml（メタデータ）、HTML/JS ファイル（WebView で描画される UI）、handler（バックエンドでメッセージを処理する Python）で構成される。

```yaml
asset_id: "my_pack.chat.messages"
name: "Chat Messages"
entry: "ui/chat/messages.html"
handler: "components/chat_messages.py"
permissions:
  - chat.message.send
  - chat.message.read
  - ai.model.list
placement:
  slot: "main"
  priority: 100
category: "chat"
tags: ["chat", "messages"]
extensions: {}
```

Asset は user_data/packs/{pack_id}/assets/ に配置される。パック承認後、Asset が自動的にフロントエンドに登録される。defaults のコード変更はゼロ。

同じ asset_id で登録すると上書きされる。これにより別パックが defaults パック（またはその他のパック）の Asset を差し替えることが可能。

### Widget

Widget はバックエンドが「このデータをこう表示してほしい」と宣言するための統一プリミティブである。tool、prompt、ai_client、chat、agent、全てが同じ Widget 体系を使う。Widget は純粋なデータ（JSON）であり UI ライブラリではない。フロントエンドの shell.html 内の Widget レンダラーがこの JSON を受け取り、テーマに従って実際に描画する。

Widget の型は表示系（Text、CodeBlock、Diff、Image、Screenshot、Progress、Terminal、Table、Chart、FileTree、Markdown、Audio、Video、Map の14種）、コントロール系（Input、Button、Select、Toggle、Slider、Checkbox の6種）、レイアウト系（Container、Row、Column、Tabs、Collapsible、Card の6種）、ストリーミング系（Stream、Indicator の2種）、カスタム（Custom の1種）の計29種。

Widget の詳細仕様は docs/widget.md に定義する。

## 6. 全てが user_data で実現される例

以下は全て user_data のツール・エージェント・Flow・Asset として実現される。defaults は仕組みを提供するだけであり、これらの具体的な実装コードを持たない。

### ナレッジ検索

user_data/shared/tools/knowledge_search/ にベクトル検索ツールを配置する。user_data/shared/flows/ に Flow Modifier を配置し、user_input 到着時にこのツールを自動実行するステップを注入する。ツールの handler.py は `context["capability"]("llm_call", {...})` で埋め込み生成し、`context["data_read"]` でインデックスを読み、結果を返す。defaults の変更はゼロ。

### マルチエージェント

user_data/shared/tools/agent_delegate/ にエージェント委譲ツールを配置する。ツールの handler.py は `context["call_handler"]("defaults.chat.create_conversation", {...})` で新しい会話を作り、`context["call_handler"]("defaults.agent.execute", {...})` でエージェントを起動し、結果を受け取って返す。組織構造が必要なら user_data/shared/agents/ に複数の agent.json を置き、委譲ツールが適切なエージェントを選択する。defaults の変更はゼロ。

### AI による会話履歴の自己編集

user_data/shared/tools/history_prune/ に履歴編集ツールを配置する。ツールの handler.py は `context["call_handler"]("defaults.chat.list_conversations", {...})` でメッセージを取得し、`context["data_write"]` で会話ファイルを更新する。agent.json の tools.enabled にこのツールを追加すれば、エージェントが自律的に履歴を整理できる。defaults の変更はゼロ。

### Linux 環境での GUI 操作

user_data/shared/tools/linux_env/ に環境操作ツール群を配置する。ツールの handler.py は `context["capability"]("container_exec", {"action": "create", "options": {"display": true}})` でコンテナを起動し、screenshot と input アクションで画面操作する。操作するモデルの選択は agent.json の model 設定で行う。defaults の変更はゼロ。

### 同意ポップアップ

user_data/shared/tools/consent_check/ に同意確認ツールを配置する。ツールの handler.py は `context["emit_event"]("ui.popup.show", {"title": "免責事項", ...})` でポップアップを出し、`context["wait_event"]("ui.popup.response", timeout=60)` でユーザーの応答を待つ。agent.json の tools.enabled に追加し、エージェントのシステムプロンプトで「投資助言に該当する場合はこのツールを使え」と指示する。defaults の変更はゼロ。

### 定期実行

user_data/shared/flows/ に schedule トリガー付きの Flow を配置する。Flow の trigger.type を "schedule"、trigger.config.cron を "*/30 * * * *" に設定する。Flow の handler.py が `ctx.call_block("agent.run", {...})` でエージェントを起動する。defaults の変更はゼロ。

### 課金・クレジット管理

user_data/shared/tools/billing_check/ に使用量確認ツールを配置する。ツールの handler.py は `context["call_handler"]("defaults.ai.usage", {...})` で使用量を取得し、`context["data_read"]("billing/plan.json")` でプラン定義を読み、残りクレジットを計算して返す。UI 表示が必要なら user_data/packs/ に billing Asset を持つパックを配置する。defaults の変更はゼロ。

## 7. defaults のファイル構成

```
ecosystem/defaults/
├── README.md                      # 権限カタログ + handler 体系
├── handlers/
│     └── frontend.py              # 通信ブリッジ handler（ホスト実行）
├── flows/
│     ├── simple_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     ├── agent_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     └── planning_agent/
│           ├── flow.yaml
│           └── handler.py
├── domain/
│     ├── chat/                    # 会話データの永続化・変換
│     ├── agent/                   # エージェントループ・コンテキスト管理
│     ├── tool/                    # ツール実行・権限検証・MCP
│     ├── prompt/                  # テンプレートレンダリング
│     ├── ai_client/               # LLM 通信・プロバイダ抽象化
│     ├── coding/                  # ファイル操作・ターミナル・Git
│     ├── memory/                  # メモリ管理・ベクトルストア
│     └── media/                   # マルチモーダル処理
├── transport/
│     ├── http/                    # HTTP 通信
│     ├── stdio/                   # 標準入出力通信
│     └── uds/                     # Unix ドメインソケット通信
├── bridge/                        # カーネル context ラッパー
├── ui/
│     └── shell.html               # 空の枠（スロット + Asset ローダー + Widget レンダラー）
├── lib/
│     └── rumi_widgets/            # Widget Python ヘルパー
│           ├── __init__.py
│           ├── display.py
│           ├── controls.py
│           ├── layout.py
│           ├── stream.py
│           └── custom.py
└── docs/
      ├── architecture_defaults.md
      ├── agent.md
      ├── ai_client.md
      ├── chat.md
      ├── flow.md
      ├── prompt.md
      ├── tool.md
      ├── frontend.md
      ├── widget.md
      ├── theme.md
      ├── api.md
      ├── profiles_and_models.md
      ├── conflict_resolution.md
      ├── ui_and_layout.md
      └── capability/
            └── dependency-resolution.md
```

## 8. defaults が提供する handler 一覧

handler 58個。全ての handler は汎用的な操作基盤であり、tool の `call_handler` から呼び出せる。詳細は README.md に定義する。

frontend（3個）: start、stop、emit。

chat（8個）: send、stream、create_conversation、list_conversations、branch、search、stop、regenerate。

agent（6個）: execute、approve、reject、cancel、status、plan。

coding（12個）: file_read、file_write、file_create、file_delete、file_search、file_list、terminal_exec、terminal_stream、git_status、git_diff、git_commit、git_push。

ai（9個）: complete、stream、models、providers、embed、image_gen、image_analyze、transcribe、tts。

tool（5個）: invoke、list、schema、mcp_connect、mcp_list。

prompt（4個）: render、list、create、system。

memory（5個）: store、recall、project_context、vector_store、vector_query。

media（6個）: image_read、image_transform、doc_parse、clipboard_read、clipboard_write、screenshot。

## 9. 他のドキュメントとの関係

本ドキュメントは defaults の全体像を定義する。各ドメインの詳細設計は以下のドキュメントに記載する。

agent.md はエージェントループ、agent.json 仕様、コンテキスト管理、サブエージェント、プランニングの詳細を定義する。

ai_client.md は LLM 通信、プロバイダ抽象化、二重バリア変換、StandardMessage/StandardResponse 仕様を定義する。

chat.md は会話データ形式、RumiMessage スキーマ、会話分岐、store API を定義する。

flow.md は Flow Engine、handler.py 仕様、ノードグラフ、トリガーシステム、Block 契約を定義する。

prompt.md はプロンプトテンプレート、変数展開、Python 拡張を定義する。

tool.md はツール定義形式、context API、段階的開示、MCP 対応、Pack 連携を定義する。

frontend.md はフロントエンドアーキテクチャ、Asset 形式、通信プロトコル、スロットモデルを定義する。

widget.md は Widget 型一覧、JSON 形式、テーマ連携を定義する。

theme.md はテーマ構造、トークン、アニメーション、Widget 描画スタイルを定義する。
```