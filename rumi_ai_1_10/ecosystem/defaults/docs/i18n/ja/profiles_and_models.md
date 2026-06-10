<!-- docs-i18n-links:start -->
[EN](../../profiles_and_models.md) | [JP](./profiles_and_models.md) | [KR](../ko/profiles_and_models.md) | [CN](../zh-cn/profiles_and_models.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS のデフォルトのプロファイルとモデル

このドキュメントでは、`defaults` パックが AI プロファイル、ツール構成、およびユーザー データを管理して、極度の柔軟性、カスタム命令、および高度なモデル オーケストレーション (エージェントの混合など) の要件を満たす方法について詳しく説明します。

## 「何でもあり」プロファイルの原則

従来のアプローチは、`AI Profile` (たとえば、単に `model_name` と `temperature`) を厳密に定義することです。 Rumi AI OS は、コア プロファイル オブジェクトに対して柔軟でスキーマレスのアプローチを採用しており、パックが必要なものをすべて注入できるようにします。

### 1. 柔軟な AI プロファイル
* **構造:** AI プロファイル (`user_data/ai_profiles/` に格納) は JSON オブジェクトです。 `defaults` パックには `id`、`name`、`provider` などの標準フィールドが必要ですが、残りはオープンです。
* **カスタム手順:** ユーザーまたはパックは次のようなフィールドを追加できます。
    ```json
    {
      "id": "coding_assistant",
      "provider": "openai",
      "model": "gpt-4",
      "system_prompt": "You are a helpful coding assistant.",
      "user_preferences": {
        "language_requirement": "English Recommended",
        "output_format": "markdown",
        "verbosity": "concise"
      },
      "custom_pack_data": {
        "my_pack_id": {
          "special_feature_enabled": true
        }
      }
    }
    ```
* **解釈:** `defaults` パックのプロンプト ビルダーは、これらの `user_preferences` を読み取り、LLM に送信する前に最終的なシステム プロンプト コンテキストに動的に挿入します。

### 2. ユーザーデータの標準化
特定のユーザーの環境に関連するすべての構成は、`user_data/` に保存する必要があります。これには以下が含まれます:
* `user_data/ai_profiles/`
* `user_data/tool_settings/`
* `user_data/agent_configs/`
* `user_data/ui_preferences/`

この標準化により、ユーザー構成は移植可能で、バックアップが容易で、システム レベルのパック ファイルから分離されることが保証されます。

## 高度なモデルのサポート (MoA、アンサンブルなど)

エージェントの混合 (MoA) やカスタム ルーティング アーキテクチャなどの概念をサポートするには、`defaults` パックはエージェントと単一のモデルの間に 1:1 の関係を想定してはなりません。

### 1.「仮想プロバイダー」の概念
MoA をサポートするためにコア エンジンを変更する代わりに、`defaults` パックは「仮想プロバイダー」の作成を奨励します。
* **実装:** パックは新しい AI プロバイダー (例: `provider: moa_router`) を登録できます。 `defaults` パック エージェントにとって、これは他の LLM と同じように見えます。
* **委任:** エージェントが `moa_router` にメッセージを送信すると、`moa_router` パックのバックエンド ハンドラーが引き継ぎます。次に、さまざまな実際のモデル (GPT-4、Claude など) にサブリクエストを生成し、結果を合成し (MoA プロセス)、最終応答をエージェントに返すことができます。

### 2. マルチモデルエージェント
あるいは、`defaults` パックの `agent.json` スキーマを使用すると、プライマリ モデルと、オプションの **フォールバック モデル**、または **計画/推論** と **ツール実行** の特定のモデルを指定できます。

```json
{
  ...
  "models": {
    "primary": "anthropic/claude-3-opus",
    "fallback": "openai/gpt-3.5-turbo",
    "planner": "openai/gpt-4"
  },
  ...
}
```
これにより、基本的な多様なモデルの使用に特化した MoA パックを必要とせずに、組み込みエージェントの堅牢性とコスト効率が高くなります。
