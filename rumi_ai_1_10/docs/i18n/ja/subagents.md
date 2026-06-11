<!-- docs-i18n-links:start -->
[EN](../../subagents.md) | [JP](./subagents.md) | [KR](../ko/subagents.md) | [CN](../zh-cn/subagents.md)
<!-- docs-i18n-links:end -->

# 委任の互換性

Rumi は、「サブエージェント」を主要なアーキテクチャ概念として扱わなくなりました。

ユーザー向けの文言については、以下を推奨します。

- 長時間実行のマルチエージェント ワークスペース サーフェスの場合は `team workspace`
- `team` (そのワークスペース内の協力するエージェントのセット)
- `delegation` 制限された作業を別のエージェントに送信する場合
- 範囲が狭いワーカー ロールの場合は `specialist` または `delegated agent`

`company` および `subagent` は、古い API の互換性/内部名のままです。
ルート、保存された識別子、またはドキュメントは引き続きそれらを使用します。

正規のランタイム コントラクトは次のとおりです。

- `chat.message`：通常の会話入力
- `run.instruction`: キューに入れられたステアリングまたはランタイム ガイダンス
- `run.interrupt`: 緊急実行時ガイダンス
- `agent.delegate`: 委任されたツール対応の 1 つの実行
- `model.call`: デフォルトではツールを使用しない、1 つの限定されたモデル間の質問
- `model.switch`: 永続的な会話モデルの変更
- `model.route`: ターンスコープのルーティングオーバーライド

`subagent` は、互換性名および古いバージョンのユーザー向けエイリアスとして残ります。
委任された作業を依然として参照しているルート、関数、ツール、ラベル、ドキュメント。

## 現在の境界

- `agent.delegate` = ツール、承認、および通常のランタイム ポリシーを使用する可能性がある 1 つの委任された実行
- `multi-agent` = 複数の委任されたワーカーにわたる調整されたグループ実行
- `tool_selector`、`prompt_compactor`、`context_summarizer`、`model_router`、`vision_ocr` などのユーティリティ ロールは、特別なサブエージェント フレームワークではなく、`model.call` スタイルのユーティリティ ルーティングを通じて実装されます。

## 互換性パス

これらの互換性サーフェスは引き続き利用可能です。

- `/api/agent/subagent`
- `defaults.agent.run_subagent`
- `defaultspack.agent.run_subagent`
- `defaults.tool.subagent`
- `defaultspack.tool.subagent`
- `subagent` の児童会話ツール (`rumi_default_tools_pack`)

これらは下位互換性のために保持されており、共有入力を介してルーティングされる必要があります。
並列動作を導入する代わりに、モデル、ツール、およびポリシーの契約を結びます。

実際には、それは次のことを意味します。

- ユーティリティ ロールの互換性呼び出しは、共有 `model.call` スタイルのユーティリティ ルーティングを介してルートされます。
- タスクのような互換性呼び出しは、`agent.delegate` として共通の入力ディスパッチャーを介してルーティングされます。

古いドキュメントに `company workspace` と書かれている箇所は、今日の `team workspace` と読み替えてください。
テキストが互換性 API またはストアド ランタイムについて具体的に説明している場合を除きます。
識別子。

## ポリシーと承認

互換性 `subagent` エイリアスを使用しても、以下は回避されません。

- ツールポリシー
- 承認ゲート
- ランタイムプロファイルツールの接続
- モデルの機能チェック
- ワークスペースの信頼要件

委任された作業にツールが必要な場合は、委任された作業と同じポリシーと承認パスを使用する必要があります。
その他の走行。
