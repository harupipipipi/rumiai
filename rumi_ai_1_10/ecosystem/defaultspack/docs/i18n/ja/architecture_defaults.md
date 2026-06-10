<!-- docs-i18n-links:start -->
[EN](../../architecture_defaults.md) | [JP](./architecture_defaults.md) | [KR](../ko/architecture_defaults.md) | [CN](../zh-cn/architecture_defaults.md)
<!-- docs-i18n-links:end -->

# デフォルトのアーキテクチャ設計ドキュメント

## 1. デフォルトとは何ですか?

defaults は、rumiai のセットアップ時に自動的にインストールされる基本パックです。 rumiai自体はドメイン知識を持たない汎用カーネルですが、defaultsはAIサービスとして必要な「仕組み」をすべて提供します。

デフォルトはメカニズムのみを提供します。メカニズムとは、チャットできる場所、エージェントが移動する場所、ツールが実行される場所、プロンプトが表示される場所、UI が描画される場所を意味します。 user_data は、これらの場所に何を配置するかを決定します。

デフォルト自体にはチャット画面はありません。エージェント定義がありません。道具としての実体はありません。プロンプトテンプレートはありません。 UI コンポーネントはありません。デフォルトには、それらを実行するためのハンドラー、権限、フロー、ドメイン コード、および通信層が含まれています。

## 2. 設計原則

### メカニズムのみを提供し、すべての内容は user_data です

デフォルトは、何を行うかではなく、何ができるかを定義します。

handler は、ドメイン操作の実行プラットフォームです。 `defaults.chat.send` は、「メッセージを送信するメカニズム」を提供します。呼び出し元 (ツール、フロー、パック) が、どの会話に何を送信するかを決定します。

権限カタログは、操作のための権限システムです。 `chat.message.send`では「メッセージの送信を許可してもよい」と定義されており、誰に許可を与えるかはGrantによって決まります。

フローは処理パイプラインの実行ベースです。 `simple_chat` フローは「ユーザー入力→コンテキスト構築→LLM呼び出し→応答保存」というフレームワークを提供します。フローの構成および user_data 設定によって、使用するモデルと適用するプロンプトが決まります。

フロントエンドは描画用のフレームを提供します。 shell.html は、スロット (メイン、サイドバー、パネルなど) を定義する空のボックスです。どのスロットに何が描かれるかは、Assetとして登録されている内容によって決まります。

### バッテリーが付属していますが、すべてのバッテリーは取り外し可能です

デフォルトを含めると、AI サービスとして必要なすべてのメカニズムが機能します。ただし、どのメカニズムも別のパックに置き換えることができます。ハンドラーは同じ名前で上書きできます。フローはリプレイスで置き換えることができます。権限は拡張可能です。フロントエンド アセットは同じ ID で上書きできます。

### デフォルトは限界ではなく標準を定義します

デフォルトで定義されている権限、ハンドラー、ドメイン モデル、ウィジェット タイプ、およびアセット形式は、rumiai エコシステムの標準語彙になります。他のパックではこの語彙が使用されます。ただし、この語彙は拡張可能であり、他のパックは、デフォルトが知らない権限ドメイン、知らないハンドラー カテゴリ、および知らないウィジェット タイプを追加できます。

### すべてを知り、何も想定しない

デフォルトは、AI サービスに必要なすべてのドメイン知識 (チャット、エージェント、ツール、プロンプト、AI クライアント、コーディング、メモリ、メディア) を知っています。ただし、ユーザーの環境、ユースケース、または好みについては想定しません。すべてが構成可能であり、すべてを上書きすることができます。

### 信頼ではなく機能によるセキュリティ

デフォルト自体は rumiai の承認プロセスの対象となります。デフォルトのコードは SHA-256 ハッシュ検証で認可され、許可によって付与されたアクセス許可の範囲内でのみ動作します。デフォルトは特別に扱われません。

### 専門化は禁止されています

デフォルトは、特定の使用例に特化したメカニズムを作成しません。マルチエージェント専用の API、ナレッジ検索専用の API、またはスケジューラ専用の API を作成しないでください。汎用的なプリミティブ（ハンドラ呼び出し、イベント発行、データ読み書き、フロー実行）を提供しており、それらの組み合わせによりあらゆるユースケースを実現できます。

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

### デフォルトの内容

ハンドラー(58個)。カテゴリ: チャット、エージェント、ツール、プロンプト、AI、コーディング、メモリ、メディア、フロントエンド。すべてのハンドラーは汎用の操作プラットフォームであり、その内容についての特別な知識はありません。

流れ（3個）。シンプルチャット、エージェントチャット、プランニングエージェント。処理パイプラインのスケルトンのみを定義し、特定のモデルの選択とプロンプト アプリケーションを Flow config と user_data に委譲します。

権利カタログ (20 ドメイン)。チャット、エージェント、ツール、プロンプト、AI、ファイル、ターミナル、git、メモリ、メディア、フロー、構成、ネット、フロントエンド、イベント、監査、パック、シークレット、カーネル。すべてのパックで使用される標準語彙。

ドメインコード。チャット ストア、エージェント ループ、ツール エグゼキュータ、プロンプト レンダラー、ai_client、コンテキスト ビルダーなどの内部ロジック。これらはハンドラーから呼び出され、外部に直接公開されません。

フロントエンドフレーム。 shell.html (スロット定義 + アセット ローダー + ウィジェット レンダラー + メッセージ ディスパッチ)。特定の UI コンポーネントはありません。

コミュニケーション層。 3 つのトランスポート: http、stdio、および uds。設定でどれを使用するかを選択します。

ウィジェットヘルパーライブラリ。 rumi_ウィジェット。バックエンド ハンドラーおよびウィジェット JSON を構築するツール用の Python ヘルパー。使用法はオプションであり、dict を直接返すのと同等です。

### デフォルトにないもの

特定の UI コンポーネント (チャット画面、エージェント パネル、コード エディターなど)。これらは user_data パックによってアセットとして提供されます。

特定のツール定義 (file_read、bash、web_search など)。これらは user_data/shared/tools/ に配置されます。

特定のエージェント定義 (coding_assistant、research_agent など)。これらは user_data/shared/agents/ に配置されます。

特定のプロンプト テンプレート。これらは user_data/shared/prompts/ に配置されます。

特定の AI モデル プロファイル。これらは user_data/shared/ai_models/ に配置されます。

テーマの定義。これらは user_data/themes/ に配置されます。

レイアウト定義。これらは user_data/layout/ に配置されます。

## 4. ツールコンテキスト API

ツールは、デフォルトで提供されるメカニズムの最も重要な利用者です。ツールの handler.py に注入されるコンテキスト API は汎用プリミティブのみで構成されます。ドメイン固有の API はありません。

### 常に注入される (宣言は必要ありません)

`context["call_handler"](§RUMI§0§)` は任意のハンドラーを呼び出します。 Grantで付与された権限の範囲内でのみ実行できます。呼び出されたハンドラーによって要求されたアクセス許可が呼び出し元にない場合、PermissionError で拒否されます。これにより、ツールは同じプリミティブを使用して、チャット操作、エージェントの起動、プロンプトのレンダリング、メモリの読み取りと書き込みを実行できるようになります。

`context["emit_event"](§RUMI§0§)` がイベントを公開します。他のハンドラー、フロー イベント トリガー、およびフロントエンド アセットはこのイベントを受信できます。発行者は受信者を知りません。

`context["wait_event"](§RUMI§0§)`はイベントを待ちます。指定されたイベント タイプが発生するまでブロックします。タイムアウトを指定できます。フィルターを使用して条件を絞り込むことができます。 Emit_eventと組み合わせることで、フロントエンドでのポップアップ表示→ユーザー応答待ち、ツール間の非同期通信、フロートリガーのフックなどを実現します。

`context["emit_widget"](§RUMI§0§)` は Widget JSON を UI に送信します。フロントエンドのウィジェット レンダラーによって描画されます。

`context["cancel_check"]()`はキャンセル確認です。ユーザーがキャンセルした場合は、CancelledError を発生させます。

`context["handler_config"]` は、conditions.json の Behavior_variants から注入される設定です。

`context["session"]`はセッション情報(session_id、workspaceなど)です。

### 機能として宣言することで注入されるもの

`data_read` は user_data の下にあるファイルを読み取ります。 `context["data_read"](§RUMI§0§)` からアクセスします。パスは user_data/ に対する相対パスです。

`data_write` は user_data の下にファイルを書き込みます。 `context["data_write"](§RUMI§0§)` からアクセスします。

`execute_flow`はフローを開始します。 `context["execute_flow"](§RUMI§0§)` からアクセスします。フローエンジン経由で実行されます。

`shell_exec`はシェルコマンドを実行します。 `context["capability"](§RUMI§0§)` からアクセスします。

`browser_control`はブラウザ操作です。 `context["capability"](§RUMI§0§)` からアクセスします。

`container_exec` は、Docker コンテナを起動、操作、および破棄します。 `context["capability"](§RUMI§0§)` からアクセスします。 GUI環境(Xvfb+VNC)は表示オプションで起動し、スクリーンショットと入力(クリック、タイプ、キー、スクロール)により座標ベースの画面操作が可能です。

`app_control`はホストアプリケーションの動作です。 `context["capability"](§RUMI§0§)` からアクセスします。

`http_request`は外部HTTP通信です。 `context["capability"](§RUMI§0§)` からアクセスします。

`llm_call` はツール内 LLM 呼び出しです。 `context["capability"](§RUMI§0§)` からアクセスします。

`session_state` はセッション状態の読み取り/書き込みです。 `context["capability"](§RUMI§0§)` からアクセスします。

### 特化した API を作成してみてはいかがでしょうか?

`context["chat"]` や `context["agent"]` などのドメイン固有の API を作成する場合は、新しいドメインが追加されるたびにコンテキスト API を拡張する必要があります。これは、「特殊化なし」というデフォルトの設計原則に違反します。

代わりに、`call_handler` と呼ばれる単一の汎用ゲートウェイが提供されます。チャット操作は`call_handler("defaults.chat.send", {...})`を使用して実行されます。エージェントは `call_handler("defaults.agent.execute", {...})` を使用して起動されます。新しいパックで新しいハンドラーが定義されている場合、ツールは同じ `call_handler` を使用してそれを呼び出すことができます。コンテキスト API を変更する必要はありません。

同様にフロントエンドへの通知、ユーザーへの確認、定期実行の登録も`emit_event` / `wait_event` / `execute_flow`の汎用プリミティブを用いて実現されています。これらのプリミティブ自体はほとんど変更されず、その上にあるハンドラーとフローは拡張されます。

## 5. フロントエンドの仕組み

### デフォルトで提供されるもの

シェル.htmlのみ。 shell.html は、次の機能を備えた空のボックスです。

スロットの定義。 7 つのスロットを定義します: header、sidebar.left、main、panel.bottom、sidebar.right、statusbar、および float。スロットはアセットが配置される場所です。スロット自体は何も描画しません。

アセットローダー。 `asset.register` メッセージを受信すると、iframe を使用してアセットの HTML ファイルをロードし、指定されたスロットに配置します。アセット（チャット画面、ファイルツリー、ダッシュボード）が何なのかわかりません。

ウィジェットレンダラー。バックエンドから送出されたWidget JSONを受け取り、テーマに合わせてHTMLに変換します。各ウィジェット タイプ (Text、CodeBlock、Image など) にはレンダリング ロジックがあります。テーマはウィジェットの外観を決定します。

メッセージのディスパッチ。 `asset_id` を使用してバックエンドからのメッセージを並べ替え、対応する iframe に転送します。 iframe からバックエンドにメッセージを転送します。データの内容は解釈されません。

### デフォルトでは提供されないもの

チャット画面のHTML/JS/CSS。エージェントパネルのHTML/JS/CSS。コードエディターHTML/JS/CSS。設定画面のHTML/JS/CSS。これらはすべて、user_data パックによってアセットとして提供されます。

### アセット登録フォーマット

アセットは UI 上に配置されるブロックの単位です。アセットは、asset.yaml (メタデータ)、HTML/JS ファイル (WebView によって描画される UI)、およびハンドラー (バックエンドでメッセージを処理する Python) で構成されます。

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

アセットは user_data/packs/{pack_id}/assets/ に配置されます。パックが承認されると、アセットがフロントエンドに自動的に登録されます。デフォルトではコードの変更はありません。

同じasset_idで登録すると上書きされます。これにより、デフォルト パック (または他のパック) のアセットを別のパックで置き換えることができます。

### ウィジェット

ウィジェットは、バックエンドが「このデータをこのように表示したい」と宣言できるようにする統合プリミティブです。ツール、プロンプト、ai_client、チャット、エージェントはすべて同じウィジェット システムを使用します。ウィジェットは純粋なデータ (JSON) であり、UI ライブラリではありません。フロントエンドのshell.html内のウィジェットレンダラーはこのJSONを受け取り、テーマに従って実際に描画します。

ウィジェットの種類は、表示タイプ（Text、CodeBlock、Diff、Image、Screenshot、Progress、terminal、Table、Chart、FileTree、Markdown、Audio、Video、Mapの14種類）、コントロールタイプ（Input、Button、Select、Toggle、Slider、Checkbox）です。レイアウト型（6種類：Container、Row、Column、Tabs、Collapsible、Card）、ストリーミング型（2種類：Stream、Indicator）、カスタム（1種類：Custom）の計29種類。

Widgetの詳しい仕様はdocs/widget.mdに定義されています。

## 6. user_data ですべてを実現する例

以下はすべてuser_dataのツール、エージェント、フロー、アセットとして実現されます。デフォルトはメカニズムを提供するだけであり、特定の実装コードはありません。

### ナレッジ検索

ベクトル検索ツールを user_data/shared/tools/knowledge_search/ に配置します。 Flow Modifier を user_data/shared/flows/ に配置し、user_input が到着したときにこのツールを自動的に実行するステップを挿入します。ツール handler.py は、`context["capability"](§RUMI§0§)` で埋め込みを生成し、`context["data_read"]` でインデックスを読み取り、結果を返します。デフォルトからの変更はありません。

### マルチエージェント

エージェント委任ツールを user_data/shared/tools/agent_delegate/ に配置します。ツール handler.py は、`context["call_handler"](§RUMI§0§)` で新しい会話を作成し、`context["call_handler"](§RUMI§1§)` でエージェントを開始し、結果を受信して​​返します。組織構造が必要な場合は、複数のagent.jsonファイルをuser_data/shared/agents/に配置すると、委任ツールが適切なエージェントを選択します。デフォルトからの変更はありません。

### AIによる会話履歴の自動編集

履歴編集ツールを user_data/shared/tools/history_prune/ に配置します。ツール handler.py は、`context["call_handler"](§RUMI§0§)` でメッセージを取得し、`context["data_write"]` で会話ファイルを更新します。このツールをagent.jsonのtools.enabledに追加すると、エージェントは自律的に履歴を整理できます。デフォルトからの変更はありません。

### Linux環境でのGUI操作

環境操作ツールを user_data/shared/tools/linux_env/ に配置します。 handler.pyというツールは`context["capability"](§RUMI§0§)`でコンテナを起動し、スクリーンショットや入力アクションで画面を操作します。 Agent.jsonのモデル設定で操作するモデルを選択します。デフォルトからの変更はありません。

### 同意ポップアップ

同意確認ツールを user_data/shared/tools/consent_check/ に配置します。ツール handler.py は、`context["emit_event"](§RUMI§0§)` でポップアップを表示し、`context["wait_event"](§RUMI§1§)` でユーザーの応答を待ちます。これをagent.jsonのtools.enabledに追加し、エージェントのシステムプロンプトに「投資アドバイスに該当する場合はこのツールを使用する」ように指示します。デフォルトからの変更はありません。

### 定期実行

user_data/shared/flows/ にスケジュールトリガーを設定したフローを配置します。フローのtrigger.typeを「schedule」、trigger.config.cronを「*/30 * * * *」に設定します。フローの handler.py は `ctx.call_block("agent.run", {...})` でエージェントを起動します。デフォルトからの変更はありません。

### 請求/クレジット管理

使用状況チェックツールを user_data/shared/tools/billing_check/ に配置します。ツール handler.py は、`context["call_handler"](§RUMI§0§)` で使用量を取得し、`context["data_read"](§RUMI§1§)` でプラン定義を読み取り、残りのクレジットを計算して返します。 UI 表示が必要な場合は、課金アセットを含むパックを user_data/packs/ に配置します。デフォルトからの変更はありません。

## 7. デフォルトのファイル構造

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

## 8. デフォルトで提供されるハンドラーのリスト

ハンドラーは58人。すべてのハンドラは汎用の操作ベースであり、ツール `call_handler` から呼び出すことができます。詳細はREADME.mdに定義されています。

フロントエンド (3 個): 開始、停止、放出。

チャット (8): 送信、ストリーム、会話の作成、会話のリスト、分岐、検索、停止、再生成。

エージェント (6 個): 実行、承認、拒否、キャンセル、ステータス、計画。

コーディング (12 個): file_read、file_write、file_create、file_delete、file_search、file_list、terminal_exec、terminal_stream、git_status、git_diff、git_commit、git_push。

ai (9 個): 完全、ストリーム、モデル、プロバイダー、埋め込み、画像生成、画像分析、転写、tts。

ツール (5 個): invoke、list、schema、mcp_connect、mcp_list。

プロンプト (4): レンダリング、リスト、作成、システム。

メモリ (5 個): ストア、リコール、project_context、vector_store、vector_query。

メディア (6 枚): image_read、image_transform、doc_parse、clipboard_read、clipboard_write、スクリーンショット。

## 9. 他の文書との関係

この文書では、デフォルトの全体像を定義します。各ドメインの詳細な設計は以下のドキュメントに記載されています。

Agent.md は、エージェント ループ、agent.json 仕様、コンテキスト管理、サブエージェント、および計画の詳細を定義します。

ai_client.md は、LLM 通信、プロバイダー抽象化、二重バリア変換、および StandardMessage/StandardResponse 仕様を定義します。

chat.md は、会話データ形式、RumiMessage スキーマ、会話分岐、ストア API を定義します。

flow.md は、フロー エンジン、handler.py 仕様、ノード グラフ、トリガー システム、およびブロック コントラクトを定義します。

プロンプト.md は、プロンプト テンプレート、変数展開、および Python 拡張機能を定義します。

tool.md は、ツール定義形式、コンテキスト API、段階的公開、MCP サポート、およびパック調整を定義します。

Frontend.md は、フロントエンド アーキテクチャ、アセット フォーマット、通信プロトコル、およびスロット モデルを定義します。

widget.md は、ウィジェットの種類のリスト、JSON 形式、およびテーマの調整を定義します。

theme.md は、テーマの構造、トークン、アニメーション、およびウィジェットの描画スタイルを定義します。
