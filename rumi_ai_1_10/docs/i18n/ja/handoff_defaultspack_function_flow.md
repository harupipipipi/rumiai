<!-- docs-i18n-links:start -->
[EN](../../handoff_defaultspack_function_flow.md) | [JP](./handoff_defaultspack_function_flow.md) | [KR](../ko/handoff_defaultspack_function_flow.md) | [CN](../zh-cn/handoff_defaultspack_function_flow.md)
<!-- docs-i18n-links:end -->

# ハンドオフ:defaultspack 関数/フロー ランタイム

このハンドオフは自己完結型です。次のエンジニアは、
リポジトリ名 `rumiai` ですが、以前の会話を読んでいません。

## リポジトリとブランチ

- リポジトリ: `rumiai`
- このチェックポイントに使用されるローカル ワークスペース:
  §るみ§0§
- メインパッケージディレクトリ: `rumi_ai_1_10`
- 分岐: `codex/defaultspack-function-flow`
- リモート: `origin`、`https://github.com/harupipipipi/rumiai.git`
- このハンドオフ ファイルの前のチェックポイント コミット:
  §るみ§0§

同じブランチで作業を続け、残りの作業をすべて 1 つの PR にまとめます。
ユーザーがスコープを明示的に変更しない限り、これを複数の PR に分割しないでください。

## ユーザーの目標

ユーザーは `defaultspack` を正規ランタイムにすることを望んでおり、
これらのアーキテクチャ ルールに一致する実装:

- `defaultspack` は正規ランタイムです。
- `defaults`は薄い互換シムとしてのみ残ります。
- ツールは機能/能力ファサードとして実装されます。
- 工具の安全性は`write_action: true`に依存してはなりません。
- 信頼できないユーザー/パックのコードは、Docker 分離内で実行する必要があります。
- ホストアクセス、ネットワークアクセス、ファイル編集、ターミナル、git、ブラウザ、
  コンピュータ制御は、信頼できるデフォルトの機能/機能の許可を通過する必要があります。
- 通常のチャット入力は、宣言的な YAML フローと Python フローを経由する必要があります
  エンジン。
- フローはオーケストレーションのみです。実際のロジックは関数に属します。
- プロンプトは受動的なコンテキストであり、実行可能なツールのロジックではありません。
- AI プロバイダーはマニフェストファーストである必要があり、OpenAI 互換プロバイダーを使用する必要があります。
  可能な場合はマニフェスト/モデル定義によって追加可能です。
- フロントエンド HTTP/SSE/ウィジェット コントラクトは、バックエンドの間でも互換性を維持する必要があります
  内部はルート レジストリ + フロー/関数に移動します。

最終的に望ましい結果は、これを完全に実装して検証する 1 つの PR です。
方向。

## 維持すべきアーキテクチャ上の決定

- 正規ランタイム: `ecosystem/defaultspack`。
- レガシー互換性: `ecosystem/defaults` は `defaultspack` に委譲されます。
- フローの実装: YAML 宣言と Python エンジン。
- 許可される承認可能なツール実行タイプ:
  - `rumi_function`
  - `capability`
  - `mcp`
- `local`、`handler`、`dynamic`、`prompt` などのレガシー実行タイプ
  信頼できないツールに対しては権限がありません。既存のファーストパーティ互換性
  パスは一時的に残る場合がありますが、信頼できないツールの場合はフェールクローズする必要があります。
- 現在使用されている能力分類:
  - `file.read`
  - `file.write`
  - `terminal.exec`
  - `git.read`
  - `git.write`
  - `network.read`
  - `network.send`
  - `browser.control`
  - `computer.control`
- `write_action`はメタデータのみです。許可とリスクの決定が必要になる
  リスク クラス、承認ポリシー、実行タイプ、信頼できるパック ID、および
  能力の付与。
- Docker が利用できない場合、厳格な Docker ポリシーはホスト フォールバックを拒否する必要があります。

## チェックポイントにすでに実装されているもの

### ツールのセキュリティと機能化

- `ecosystem/defaultspack/domain/tool/security.py`を追加しました。
- リスクを正規化するために`ecosystem/defaultspack/domain/tool/registry.py`を更新しました。
  サポートされていない信頼できないレガシー実行タイプを拒否し、機能を公開します
  を付与し、ツールが表示される場所で UI/拡張機能の互換性を維持します。
  ただし、セキュリティ ポリシーによりまだ実行できません。
- 適用するために`ecosystem/defaultspack/domain/tool/executor.py`を更新しました
  機能/機能優先で実行し、サポートされていない信頼できないパスを拒否します。
- `ecosystem/rumi_default_tools_pack/tools/*/manifest.json` に移行しました。
  機能/機能ファサード メタデータ (コーディング/ファイル/git/ターミナルなど)
  ネットワーク/ブラウザ/コンピュータ ツール。
- `tests/test_defaultspack_tool_security.py`にテストを追加しました。

### Docker / 機能の境界

- 厳密な Docker ポリシーが拒否するように `core_runtime/capability_executor.py` を更新しました
  Docker が使用できない場合のホストのフォールバック。
- `tests/test_capability_executor_security.py`にテストを追加しました。

### フロー ランタイムとチャット Ingress

- `ecosystem/defaultspack/domain/flow/engine.py`を拡張しました。
- 以下の宣言的検証と実行サポートを追加しました。
  - `function`
  - `subflow`
  - `branch`
  - `parallel`
- `ecosystem/defaultspack/flows/chat_turn.flow.yaml` を正規として更新しました
  通常のチャットの入口。
- `ecosystem/defaultspack/flows/chat_stream_turn.flow.yaml`を追加しました。
- `tests/test_defaultspack_chat_turn_flow_contract.py` のテストを更新しました。

### チャットの永続化

- `ecosystem/defaultspack/blocks/chat/persist_turn.py` を更新したので永続化
  単なる JSONL ではなく、正規の `ChatStore` セマンティクスを通過します。
  パスを追加します。
- JSONL スタイルの監査は、正規のメッセージの永続性から分離されたままにする必要があります。

### 輸送/ルート登録

- ルートを説明するために`ecosystem/defaultspack/transport/registry.py`を更新しました。
  フロー/機能仕様を通じて。
- `ecosystem/defaultspack/transport/http.py`、`cli.py`、および`stdio.py`を更新しました。
  正規のフロー/機能パスを維持しながら通常のチャットをルーティングします。
  可能な場合は公的契約。
- `ecosystem/defaults/transport/{http,cli,stdio,uds}.py`を薄型に変換しました
  互換性のあるシム。
- 以下のルート テストを追加/更新しました:
  - `tests/test_defaultspack_route_integration.py`
  - `tests/test_defaults_mcp_transport.py`

### プロンプト

- `ecosystem/defaultspack/domain/prompt/effective.py`を追加しました。
- プロンプトの読み込み/解決を更新して、効果的なプロンプトがソース チェーンを返すようにしました。
  そして解決された内容。
- 以下のディスパッチャ エントリを追加しました。
  - `prompt_validate_template`
  - `prompt_resolve_for_conversation`
- 実行可能なプロンプト ロジックとしてのプロンプトからツールへのオーサリングを無効にしました。
- パッシブ/関数を生成するためのプロンプト テンプレート/統合変換を更新しました
  実行可能ファイル `execution.type = prompt` の代わりにファサード メタデータ。
- 追加されたテスト:
  - `tests/test_defaultspack_prompt_effective.py`
  - `tests/test_defaultspack_prompt_passive.py`

### AI クライアント/プロバイダー

- `ecosystem/defaultspack/domain/ai_client/gateway.py`を追加/更新しました。
- チャット/AI ブロックを直接 `AIClient` ではなく `LLMGateway` に移動しました。
  従来のモンキーパッチの互換性を維持しながら、オーケストレーションを実現します。
  ゲートウェイレベルの再エクスポートによる`blocks/chat/send.py`。
- `ecosystem/defaultspack/domain/ai_client/providers/__init__.py` を更新しました。
  マニフェストファーストの OpenAI 互換プロバイダー メタデータ。
- `tests/test_defaultspack_provider_manifest_first.py`を追加しました。

### ブラウザ/コンピュータの安定性

- 更新されました
  `ecosystem/rumi_default_tools_pack/domain/tool/browser_computer.py`は避けてください
  カスタム テスト アーティファクト ルートは古い共有選択ウィンドウ状態を再利用しています
  `browser_sessions.json`。
- これにより、完全な実行中に発生したブラウザ/コンピュータの状態に依存する障害が修正されました。
  pytestを実行します。

### ドキュメント

以下に関するドキュメントを更新しました。

- 流量仕様
- プロンプトオーサリング
- プロバイダーのオーサリング
- ツールのオーサリング
- 輸送
- AIプロバイダー/クライアント
- プロンプト/ツールの変換

変更された重要なドキュメントは次のとおりです。

- `docs/flow_spec.md`
- `docs/prompt_authoring.md`
- `docs/provider_authoring.md`
- `ecosystem/defaultspack/docs/ai_client.md`
- `ecosystem/defaultspack/docs/prompt.md`
- `ecosystem/defaultspack/docs/tool-prompt-conversion.md`
- `ecosystem/defaultspack/docs/transport.md`
- `ecosystem/defaultspack/docs/writing-tools.md`

## 検証はすでに実行されています

これらはチェックポイントのコミット前に渡されました。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_chat_turn_flow_contract.py \
  tests/test_defaultspack_route_integration.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_tool_security.py -q
```

結果：42名合格。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_*flow*.py tests/test_*route*.py \
  tests/test_defaults_mcp_transport.py \
  tests/test_defaultspack_tool_security.py \
  tests/test_defaultspack_tool_policy.py \
  tests/test_defaultspack_tool_components.py \
  tests/test_defaultspack_tool_executor_rumi_function.py \
  tests/test_defaultspack_external_send_tool.py \
  tests/test_defaultspack_prompt_effective.py \
  tests/test_defaultspack_prompt_components.py \
  tests/test_defaultspack_provider_expansion.py \
  tests/test_defaultspack_provider_foundation.py \
  tests/test_defaultspack_backend_foundation.py \
  tests/test_capability_executor_security.py -q
```

結果: 403 件が合格、1 件の警告が存在しました。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_defaultspack_agent_service_plan.py -q
```

結果：182名合格。

```bash
cd rumi_ai_1_10
python -m pytest tests/test_browser_computer_seat_delegation.py \
  tests/test_computer_desktop_action_delegation.py \
  tests/test_computer_move_drag_delegation.py \
  tests/test_defaultspack_agent_service_plan.py::test_computer_click_physical_true_operates_visible_action -q
```

ブラウザ/コンピュータの状態修正後の結果: 18 が合格しました。

```bash
git diff --check
```

結果：合格。

## 完全なテスト ステータス

完全なテスト コマンド:

```bash
cd rumi_ai_1_10
python -m pytest -q
```

何が起こったのか:

1. ブラウザ/コンピュータの状態が修正される前の完全な実行:
   `4373 passed, 19 skipped, 7 failed`。
2. 7 件の失敗はすべて、ブラウザ/コンピュータの物理的なアクションの委任テストでした。
   選択されたウィンドウの状態が古いため、アクションは `executed=False` を返しました。
3. 状態修正が追加され、関連する 18 テストのサブセットが合格しました。
4. 新しい完全な実行が開始され、以前に失敗したテストを通過しました。
   ブラウザ/コンピュータセクションですが、ユーザーが環境を移動するように要求したため、
   完成前に故意に止めた。

次のエンジニアは、クリーンなプロセスから完全なテスト スイートを再度実行する必要があります。

## すぐに次のステップに進む

1. ブランチをフェッチしてチェックアウトします。

```bash
git fetch origin
git checkout codex/defaultspack-function-flow
cd rumi_ai_1_10
```

2. 完全なテストを実行します。

```bash
python -m pytest -q
```

3. 障害が発生した場合は、チェックポイント アーキテクチャを元に戻さずに障害を修正します。

4. タッチした領域の周囲に集中したテストを再実行し、その後、完全なテストを再度実行します。

5. 設計の回帰を検査します。

```bash
rg -n 'execution\\.type.*prompt|"type": "prompt"|type: prompt|execution.*dynamic|execution.*handler' \
  ecosystem/defaultspack docs ecosystem/rumi_default_tools_pack
```

正規のプロンプトコンポーネントのメタデータを個別に扱います。実行可能なプロンプトツール
オーサリング パスとして返されるべきではありません。

6. AI クライアントの直接インポートを検査します。

```bash
rg -n 'from domain\\.ai_client\\.client import AIClient|from ecosystem\\.defaultspack\\.domain\\.ai_client\\.client import AIClient' \
  ecosystem/defaultspack/blocks ecosystem/defaultspack/domain
```

許可されたレガシー/インポート互換性の場所のみが残る必要があります。

7. 完了したら、`codex/defaultspack-function-flow` から 1 つの PR を作成します。
   `master`。

## 最終 PR の受け入れ基準

- `python -m pytest -q` が完全に合格したか、残りの失敗が明らかである
  無関係で文書化されています。
- 通常のチャットは`defaultspack.chat_turn`を経由します。
- `defaultspack.chat_stream_turn` または同等のストリーミング チャット フロー
  ルートレジストリ関数/フローパス。
- 既存のフロントエンド HTTP パス、JSON シェイプ、SSE イベント名、ウィジェット
  形状の互換性が維持されます。
- `defaults` は互換性シムとして引き続き機能します。
- 信頼できないレガシー実行タイプは、作成可能または実行可能ではありません。
- 機能/能力ツールのマニフェストは、リスク、承認、付与を明らかにします。
- ホスト/ネットワーク/ファイル/git/ブラウザ/コンピュータへのアクセスは信頼されたデフォルトを経由します
  機能/能力。
- プロンプトは受動的のままです。実行可能プロンプト ツールのオーサリング パスは復元されません。
- マニフェストのみの OpenAI 互換プロバイダーの追加は引き続き対象となります。
- ドキュメントは実行時の動作と一致します。

## 注意事項

- `defaults` トランスポート シムの大幅な変更は、交換しない限り元に戻さないでください。
  同等のルートレジストリ委任を使用します。
- `execution.type = prompt` を実行可能なツール パスとして再導入しないでください。
- 許可の決定として `write_action` に依存しないでください。それはメタデータです。
- Docker strict モードをサイレントにホスト実行にフォールバックさせないでください。
- macOS でのブラウザ/コンピュータのテストには注意してください。共有
  `browser_sessions.json` は、テスト間で選択したウィンドウの状態を保持できます。
- ユーザーが明示的に分割を要求しない限り、これを 1 つの PR として保持します。
