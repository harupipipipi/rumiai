<!-- docs-i18n-links:start -->
[EN](../../capability_graph.md) | [JP](./capability_graph.md) | [KR](../ko/capability_graph.md) | [CN](../zh-cn/capability_graph.md)
<!-- docs-i18n-links:end -->

# 能力グラフ

Capability Graph は、既存の実行フロー システムの横に位置する機能配線層です。

実行フローは、順序付けられたランタイム プロシージャ (起動、セットアップ、ハンドラー実行、サブフロー、関数呼び出し、`python_file_call`、`universal_call`、スケジューラー統合、および明示的なパイプライン) を引き続き担当します。

ケイパビリティ グラフは、AI クライアント、エージェント、ツール バンドル、メモリ、プロンプト、資格情報、ポリシー、フロントエンド サーフェス、CLI サーフェス、将来のパック定義機能など、どのランタイム機能を接続できるかを宣言します。

## コア境界

コアはドメイン中立性を維持する必要があります。以下の一般的な概念のみを理解する場合があります。

- ノード
- ポート
- 標準
- エッジ
- グラフ
- プロフィール
- バインディングハンドラーID
- 検証結果
- 診断

コアは、`agent`、`tool`、`ai_client`、`frontend`、`cli`、`memory`、または `prompt` などのドメインの意味に基づいて分岐してはなりません。ドメイン固有の接続動作は、エコシステム パック バインディング ハンドラーに属します。

許可されるコア動作:

- エッジの互換性を検証する
- 承認されたバインディング ハンドラーを解決する
- そのバインディング ハンドラーを呼び出す
- 診断を記録する
- `InterfaceRegistry`にグラフ/プロファイル/ランタイムプロファイル値を登録

禁止されているコア動作:

```python
if target_node.kind == "agent" and source_node.kind == "tool":
    profile["agents"][target]["tools"].append(source)
```

## ファイル

能力グラフ ファイルは `.graph.yaml` を使用します。

初期発見候補:

1. `user_data/shared/graphs/*.graph.yaml`
2. `ecosystem/<pack_id>/graphs/*.graph.yaml`
3. `graphs/*.graph.yaml`

重複する `graph_id` 値が検出された場合、フェーズ 1 はそれを診断エラーとして扱います。

パックが提供するグラフ ファイルは、パックが提供するフローの読み込みと同じ信頼境界に従い、既存のパックの承認とハッシュ検証のフローに合格したパックからのみロードされます。ユーザー共有グラフ ファイルはユーザー所有の構成として許可されますが、登録またはコンパイルの前にスキーマの検証と診断が必要です。

## スキーマ

バージョン: `rumi.graph.v1`

```yaml
graph_id: coding_workspace
version: rumi.graph.v1
display_name:
  en: Coding Workspace
  ja: コーディングワークスペース
nodes:
  - id: start
    ref: rumi.start
  - id: agent
    ref: defaultspack.agent
edges:
  - id: start_to_agent
    from: start.out
    to: agent.start
    kind: binding
```

`nodes[].id` はグラフローカルのインスタンス ID です。 `nodes[].ref` はノード定義 ID を指します。同じノード定義が 1 つのグラフ内で複数回インスタンス化される場合があります。

エンドポイント形式:

```text
<graph_node_instance_id>.<port_id>
```

フェーズ 1 エッジの種類:

- `binding`

予約済みの将来のエッジの種類:

- `data`
- `event`
- `control`

不明なエッジの種類はフェーズ 1 のエラーです。

## 検証

グラフの検証チェック:

- グラフスキーマは有効です
- すべてのノード参照がグローバル ノード レジストリに存在する
- プロファイル対応の検証が要求されると、選択したプロファイルによってすべてのノード参照が有効になります
- すべてのエッジ エンドポイントが正しく解析されます
- 参照されるすべてのポートが存在する
- 送信元ポートは `output` です
- ターゲットポートは`input`です
- ソース標準とターゲット標準が交差する
- `multiple: false` 入力ポートには最大 1 つの入力エッジがあります
- `required: true` 入力ポートには入力エッジがあります

フェーズ 1 の必須ポートのエラーは検証エラーです。将来のドラフト モードでは、警告に格下げされる可能性があります。

## コンパイル

グラフのコンパイルは、最初の実装からプロファイルを認識する必要があります。

入力:

```json
{
  "graph_id": "coding_workspace",
  "profile_id": "coding"
}
```

コンパイラーの責任:

- 負荷グラフとプロファイル
- 選択したプロファイルを使用してグラフを検証します
- ノード定義を解決する
- 承認されたバインディング ハンドラーを呼び出す
- ランタイムプロファイル辞書を生成します
- フロントエンド/サーフェスバインディング時に`runtime_profile.launch.surface`を導出
  起動可能なサーフェス ノードをポイントします
- `runtime_profile.<profile_id>.<graph_id>`を`InterfaceRegistry`に登録する
- 診断を返す

コンパイラの非目標:

- ビューア UI なし
- コア コンパイラではプロバイダ固有のツール スキーマ変換は行われません
- コア内にドメイン固有の `agent/tool/ai_client` 分岐はありません

## インターフェースレジストリキー

ケイパビリティ グラフ関連のオブジェクトは、次のキー形状を使用して登録されます。

```text
node.<node_id>
graph.<graph_id>
profile.<profile_id>
runtime_profile.<profile_id>.<graph_id>
```

## コアノード

`rumi.start` はコアが所有する唯一の特別なノードです。コアはエコシステム ノードの検出前にそれを登録します。

`rumi.start` には 1 つの出力ポートがあります。

```json
{
  "id": "out",
  "direction": "output",
  "standards": ["rumi.flow.start"],
  "multiple": true,
  "required": false
}
```

他のすべてのノードは、承認されたエコシステム パックから検出されます。エコシステム パックは、コアが所有する組み込みノード ID をオーバーライドしてはなりません。

## バックエンド API

バックエンドは、認証された HTTP API を通じてケイパビリティ グラフ データを公開します。 `/api/*` パスは仕様に面した API サーフェスです。 `/api/panel/*` エイリアスは、コントロール パネル セッションと CSRF フローに対して同じ形状を返します。

API の読み取り:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`
- `GET /api/profiles`
- `GET /api/profiles/{profile_id}`
- `GET /api/profiles/{profile_id}/nodes`
- `GET /api/graphs`
- `GET /api/graphs/{graph_id}`

グラフ プレビュー API:

- `POST /api/graphs/{graph_id}/validate`
- `POST /api/graphs/{graph_id}/compile`

視聴者側のノード応答には、ロケール解決されたラベル、ポート、標準、エイリアス、バインディング、メタデータ、要件、権限、およびプロファイルが選択されたときのプロファイル ノードの状態が含まれます。プロファイル ノード API は、`palette_nodes` も返します。これには、インストールされプロファイルが有効になっているノードのみが含まれるため、ビューアはノード タイプをハードコーディングする必要がありません。

コンパイル エンドポイントは、パネル エイリアスのデフォルトではプレビューです。呼び出し元は、起動時の起動プロファイルの信頼できるソースを置き換えることなくコンパイルできます。

実行時プロファイルの場合、コンパイル応答には `surface_launch_target` が含まれます。
起動可能なフロントエンド サーフェスが含まれています。これは使用されるのと同じ正規ペイロードです
スタートアップ プロファイルによるハンドオフの再起動:

```json
{
  "kind": "desktop_app",
  "pack_id": "frontendpack",
  "principal_id": "frontendpack",
  "surface": "browser",
  "node_instance_id": "frontendpack_web_surface",
  "node_id": "frontendpack.web_surface",
  "component_full_id": "frontendpack:frontend:web",
  "source": "capability_graph"
}
```

## ビューア ノード マネージャ

初期のノード マネージャはプロファイル スコープのカタログであり、グラフ エディタの代替品ではありません。次のように表示されます。

- 能力グラフのプロファイル
- プロファイルが有効なパレット ノード
- インストール済み、無効化、欠落、未承認、および欠落構成の状態
- ノードポート、標準、エイリアス、バインディング、およびメタデータ
- グラフの検証とプレビュー結果のコンパイル

プロファイル クローン コントロールは、選択した能力グラフ プロファイルに `permissions.can_create_profile: true` がある場合にのみ表示されます。この権限は依然としてプリセット/UI ゲートです。特権書き込みは、既存の認証済みパネル API およびファイル システム コントロールの背後に残ります。
