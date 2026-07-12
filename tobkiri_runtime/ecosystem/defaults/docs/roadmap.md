# rumiai defaults Pack — ロードマップ

最終更新: 2026-03-06
ステータス凡例: ✅ 完了 / 🔧 修正必要 / ⬜ 未着手

---

## フェーズ 0: 基盤（完了）

すべて完了済み。起動 → ブラウザアクセス → AI チャットまで動作確認済み。

| ID | 内容 | ステータス |
|----|------|-----------|
| G0-G3 | スケルトン〜Chat/Flow レイヤー | ✅ |
| P0 | 正規化 | ✅ |
| G4 | Agent / Transport / Frontend | ✅ |
| G5 | AI プロバイダ (OpenAI, Anthropic, Google, Genspark) + MCP | ✅ |
| G6 | UX 強化 | ✅ |
| G7 | Tool & Prompt 拡張 | ✅ |
| G8 | Agent 強化 + 全修正 | ✅ |
| G9a/b | ナレッジ基盤 + フロー内自動検索 | ✅ |
| docs | ドキュメント 24 ファイル + 修正 4 回 | ✅ |
| startup/boot-fix | setup.py, ecosystem.json, components/ | ✅ |
| Step 0 | Route Registry パターン移行 (44→100 ルート分散) | ✅ |

---

## フェーズ 1: 機能拡張（T1-T17）

17 タスクの並列実装。Route Registry により http.py への変更なしで完了。

| ID | 内容 | domain | blocks | ルート | ステータス |
|----|------|--------|--------|--------|-----------|
| T1 | 複数会話セッション管理 | ✅ session_manager.py | 🔧 blocks/chat/session/ 未作成 | 🔧 未登録 | 🔧 |
| T2 | AI による会話履歴編集 | ✅ history_editor.py | 🔧 blocks/chat/history/ 未作成 | 🔧 未登録 | 🔧 |
| T3 | ランタイム tool 作成 | ✅ runtime_creator.py | ✅ 既存 blocks で対応 | ✅ | ✅ |
| T4 | 免責同意 tool | ✅ disclaimer_manager.py | ✅ 既存 blocks で対応 | ✅ | ✅ |
| T5 | prompt 高度化 (ビルダー, バージョニング) | ✅ builder.py | ✅ blocks/prompt/advanced/ | ✅ 8 ルート | ✅ |
| T6 | tool/prompt 統一テンプレート | ✅ unified.py | ✅ blocks/prompt/convert.py | ✅ | ✅ |
| T7 | rumi モデル (自動ルーティング) | ✅ model_router.py | ✅ blocks/ai/routing/ | ✅ 10 ルート | ✅ |
| T8 | コンテキスト表示 API | ✅ analyzer.py | 🔧 専用 blocks なし | 🔧 ルート未登録 | 🔧 |
| T9 | dev tool 拡張 | ✅ usage_tracker.py | ✅ 既存 blocks で対応 | ✅ | ✅ |
| T10 | 組織エージェント基盤 | ✅ org_manager.py | ✅ blocks/agent/org/ (11 ファイル) | 🔧 ルート未登録 | 🔧 |
| T11 | Slack 風 AI チャット | ✅ channel_manager.py | ✅ blocks/chat/channel/ (10 ファイル) | ✅ 10 ルート | ✅ |
| T12 | 定期実行 agent | ✅ scheduler.py | ✅ blocks/agent/scheduler/ (9 ファイル) | ✅ 9 ルート | ✅ |
| T13 | タスク中指示追加 | ✅ interrupt_manager.py | ✅ blocks/agent/interrupt/ (8 ファイル) | ✅ 9 ルート | ✅ |
| T14 | Linux 環境 + 座標操作 | ✅ container_manager.py | ✅ blocks/tool/container/ (12 ファイル) | ✅ 13 ルート | ✅ |
| T15 | 権限管理 | ⬜ 未実装 | ⬜ 未実装 | ⬜ | ⬜ |
| T16 | CLI 完全分離 | ✅ cli.py | ✅ blocks/cli/entry.py | ✅ 2 ルート | ✅ |
| T17 | タブシステムバックエンド | ⬜ 未実装 | ⬜ 未実装 | ⬜ | ⬜ |

---

## フェーズ 2: 品質保証 + 残修正

### 2-A: P1 修正（ブロッカー）

| ID | 内容 | 詳細 |
|----|------|------|
| P1-1 | システムルート 404 修正 | /api/health, /, /api/context, /static/* を io.http.route に登録。Registry モードでもアクセス可能にする |
| P1-2 | T15 権限管理の実装 | domain/permission/manager.py, user_store.py, role_store.py, auth.py, audit.py + blocks/permission/ + setup.py ルート登録 |
| P1-3 | T17 タブシステムの実装 | domain/frontend/tab_manager.py, tab_presets.py + blocks/frontend/tabs/ + setup.py ルート登録 |

### 2-B: P2 修正（機能補完）

| ID | 内容 | 詳細 |
|----|------|------|
| P2-1 | T10 組織エージェントのルート登録 | blocks/agent/setup.py に org 系 11 ルートを追記 |
| P2-2 | T1 セッション管理の blocks + ルート | blocks/chat/session/ 作成 + chat/setup.py に 8 ルート追記 |
| P2-3 | T2 履歴編集の blocks + ルート | blocks/chat/history/ 作成 + chat/setup.py に 4 ルート追記 |
| P2-4 | T8 コンテキスト API のルート | /api/context/conversation/{id}, /api/context/system を登録 |
| P2-5 | ecosystem.json の provides 更新 | T10/T12/T13/T14 の新ハンドラを反映 |

### 2-C: ファイルチェック

| ID | 内容 | 詳細 |
|----|------|------|
| FC-1 | 全ブロック def run シグネチャ確認 | def run(input_data, context): が統一されているか |
| FC-2 | import スタイル統一確認 | sys.path.insert(0, pack_root) + from blocks._common import ... |
| FC-3 | pass / TODO / NotImplementedError 残留チェック | 禁止されている未実装関数がないか |
| FC-4 | setup.py ルート数と実ブロック数の一致 | 登録されたルート先のモジュールが全て存在するか |
| FC-5 | 不要ファイル削除 | transport/uds.py, blocks/frontend/stop.py 等 |

### 2-D: rumiai カーネルルール適合チェック

| ID | 内容 | 詳細 |
|----|------|------|
| RC-1 | ecosystem.json スキーマ準拠 | カーネル W26 の ecosystem.schema.json に適合するか |
| RC-2 | components/ manifest.json 存在確認 | 全 11 コンポーネントに manifest.json があるか |
| RC-3 | setup.py context 利用の妥当性 | context["interface_registry"] 等の使用がカーネル仕様に準拠しているか |
| RC-4 | KernelFacade API 制限の遵守 | get_interface, list_interfaces, emit 以外を呼んでいないか |
| RC-5 | Pack 承認フロー互換性 | ファイル変更 → modified 状態 → 再承認が正しく動くか |

### 2-E: defaults としての中立性チェック

| ID | 内容 | 詳細 |
|----|------|------|
| NC-1 | AI プロバイダの贔屓なし | 特定プロバイダがハードコードされていないか。stub/default がフォールバックか |
| NC-2 | モデルの贔屓なし | rumi モデルルーティングがフェアか。特定モデルを不当に優先していないか |
| NC-3 | ストレージの中立性 | user_data/ のパスが決め打ちでなくカーネルの userdata_manager 経由か |
| NC-4 | 外部依存の最小化 | 標準ライブラリ以外の必須依存がないか（Docker SDK はオプショナルか） |
| NC-5 | 設定のオーバーライド可能性 | 全ての挙動が環境変数 or API で変更可能か。ハードコード設定がないか |

---

## フェーズ 3: 拡張性検証

### 3-A: user_data 拡張性

| ID | 内容 | 詳細 |
|----|------|------|
| UX-1 | 他 Pack からの user_data アクセス | 他の Pack が独自の user_data サブディレクトリを持てるか |
| UX-2 | データマイグレーション | user_data のスキーマ変更時にマイグレーション手段があるか |
| UX-3 | バックアップ/リストア | user_data の一括エクスポート/インポートが可能か |
| UX-4 | ストレージプラグイン | JSON ファイル以外のストレージバックエンド（SQLite 等）に差し替え可能か |
| UX-5 | 同時アクセス安全性 | 複数スレッド/プロセスからの user_data 書き込みが安全か（ロック機構） |

### 3-B: Pack 間拡張性

| ID | 内容 | 詳細 |
|----|------|------|
| PX-1 | 他 Pack からのルート追加テスト | ダミー Pack を作って io.http.route にルートを登録、http.py が収集するか |
| PX-2 | 他 Pack からの domain 差し替え | InterfaceRegistry で AIClient 等を差し替え可能か |
| PX-3 | イベントフック | EventBus で defaults Pack の動作にフックできるか |
| PX-4 | プロバイダプラグイン | 新しい AI プロバイダを他 Pack から追加できるか（Genspark 方式の再現） |

---

## フェーズ 4: プロダクション準備

### 4-A: 権限システム完成

| ID | 内容 | 詳細 |
|----|------|------|
| AUTH-1 | T15 の完全実装 | フェーズ 2-A P1-2 で基盤実装。ここでは統合テスト + エッジケース対応 |
| AUTH-2 | ルートごとの権限定義 | 全 100+ ルートに必要権限を定義 |
| AUTH-3 | 認証ミドルウェア統合 | http.py の _handle_request で権限チェックを挟む |
| AUTH-4 | デフォルトユーザー + 初期設定フロー | 初回起動時に admin ユーザーを作成 |

### 4-B: tool / prompt の一通り作成

| ID | 内容 | 詳細 |
|----|------|------|
| TP-1 | 組み込み tool セット | web_search, calculator, code_exec, file_read, file_write, http_request |
| TP-2 | 組み込み prompt テンプレート | general_assistant, coder, analyst, translator, summarizer, creative_writer |
| TP-3 | tool/prompt のドキュメント | 各ツール/プロンプトの使い方、パラメータ、例 |
| TP-4 | tool/prompt のテスト | 各ツール/プロンプトの動作確認 |

### 4-C: フロントエンド一式（ユーザー担当）

| ID | 内容 | 詳細 | 担当 |
|----|------|------|------|
| FE-1 | shell.html の大規模分割 | 背景, サイドバー, インプットバー, タイトル, chattab, setting に分割 | ユーザー |
| FE-2 | タブ UI | ブラウザ風タブ (normal, work, coding, agent, max, monitor) | ユーザー |
| FE-3 | セッション UI | 会話タブの並列表示 (履歴1 / 履歴2 / 履歴3) | ユーザー |
| FE-4 | チャネル UI | Slack 風チャンネルリスト + メッセージ表示 | ユーザー |
| FE-5 | コンテキストパネル | 現在のコンテキスト情報をリアルタイム表示 | ユーザー |
| FE-6 | Dev パネル | プロンプト使用状況、リアルタイム編集 | ユーザー |
| FE-7 | 権限管理 UI | ユーザー/ロール/権限の管理画面 | ユーザー |
| FE-8 | 免責ポップアップ | 同意 tool のポップアップ表示 | ユーザー |
| FE-9 | コンテナ操作 UI | Linux 環境の操作画面 + スクリーンショット表示 | ユーザー |

---

## フェーズ 5: デスクトップアプリ化

| ID | 内容 | 詳細 |
|----|------|------|
| DA-1 | Electron or Tauri ラッパー | shell.html をデスクトップアプリとしてパッケージング |
| DA-2 | ネイティブ通知 | OS 通知連携（定期実行 agent の結果通知等） |
| DA-3 | トレイアイコン | バックグラウンド動作 + トレイアイコン |
| DA-4 | 自動起動設定 | OS 起動時に自動でカーネル + defaults Pack を起動 |
| DA-5 | アップデーター | git pull ベースの自動更新（or GitHub Releases） |

---

## フェーズ 6: コンパイル + リリース

| ID | 内容 | 詳細 |
|----|------|------|
| CP-1 | Python バンドル | PyInstaller or Nuitka でカーネル + defaults Pack を単一バイナリ化 |
| CP-2 | フロントエンド最適化 | shell.html の minify + アセットバンドル |
| CP-3 | クロスプラットフォームビルド | macOS, Linux, Windows 向けビルド |
| CP-4 | インストーラー | macOS: .dmg, Linux: .AppImage/.deb, Windows: .msi |
| CP-5 | CI/CD パイプライン | GitHub Actions でビルド + テスト + リリース自動化 |
| CP-6 | リリースノート | 全機能のリリースノート作成 |

---

## フェーズ 7: 最終整理

| ID | 内容 | 詳細 |
|----|------|------|
| CL-1 | 不要ファイル削除 | transport/uds.py, transport/stdio.py (CLI 移行後), blocks/frontend/stop.py |
| CL-2 | docs 最終同期 | 24 ドキュメントを全機能に合わせて更新 |
| CL-3 | README.md 更新 | インストール手順、機能一覧、スクリーンショット |
| CL-4 | CHANGELOG.md 作成 | 全リリース履歴 |
| CL-5 | LICENSE 確認 | ライセンスファイルの最終確認 |
| CL-6 | feature/genspark-provider ブランチ削除 | マージ済みブランチのクリーンアップ |

---

## 統計

| 項目 | 数量 |
|------|------|
| 総フェーズ数 | 8 (0-7) |
| 総タスク数 | 約 80 |
| 完了済みタスク | 約 45 |
| 残タスク | 約 35 |
| Registry ルート数 | 100+ |
| ブロック数 | 100+ |
| domain モジュール数 | 30+ |
| ドキュメント | 24 ファイル |
