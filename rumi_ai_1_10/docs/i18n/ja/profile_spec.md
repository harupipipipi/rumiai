<!-- docs-i18n-links:start -->
[EN](../../profile_spec.md) | [JP](./profile_spec.md) | [KR](../ko/profile_spec.md) | [CN](../zh-cn/profile_spec.md)
<!-- docs-i18n-links:end -->

# 機能プロファイル仕様

機能プロファイルは、機能グラフのコンパイル用のランタイムまたはワークスペースのプリセットです。これらは、どのノードが使用可能であるか、および選択されたグラフが特定の環境でどのように実行されるべきかを記述します。

バージョン: `rumi.profile.v1`

プロファイルはセキュリティの信頼できる文書ではありません。解析されたプロファイルのアクセス許可は、UI とランタイムのデフォルトをガイドする可能性がありますが、特権操作は依然として既存の信頼、付与、承認、および機能システムによって強制される必要があります。

## ファイル

初期発見候補:

1. `user_data/shared/profiles/*.profile.yaml`
2. `ecosystem/<pack_id>/profiles/*.profile.yaml`

パックが提供するプロファイル ファイルは、既存のパックの承認およびハッシュ検証フローに合格し、パックが提供するフローの読み込みに使用される信頼境界と一致するパックからのみロードされます。ユーザー共有プロファイル ファイルはユーザー所有の構成ですが、登録または使用する前にスキーマの検証と診断が必要です。

## スタートアップ プロファイルとの関係

ケイパビリティ グラフ プロファイルは、既存の `StartupProfileManager` や初期 PR の起動時スタートアップ プロファイル システムを置き換えるものではありません。

明示的なブリッジまたは移行 PR が確立されるまで、既存の起動プロファイルは、起動動作、セットアップ、および実行時の起動デフォルトを選択するための起動時の信頼できる情報源のままになります。 `rumi.profile.v1` は、ケイパビリティ グラフのロード、検証、コンパイル、およびビューア/ノード マネージャー フィルタリングによって使用されるグラフ/ランタイム プリセットです。

プロファイルローダーは、既存のシステムと共存することで、既存のシステムに適応します。明示的に接続されている場合にのみ、表示または診断のために起動関連のデフォルトを読み取ることができますが、起動プロファイルの選択に優先してはなりません。

バックエンド API は、この関係を並べて公開します。

```json
{
  "launch_time_source_of_truth": "StartupProfileManager",
  "capability_graph_profiles_role": "graph_runtime_presets",
  "startup_profile_api": "/api/panel/startup/profiles"
}
```

これは、ビューアに対する明示的なブリッジ コントラクトです。起動プロファイルは引き続き起動時の起動動作を所有し、`rumi.profile.v1` は、ケイパビリティ グラフの読み込み、パレット フィルタリング、検証、およびコンパイル プレビューを制御します。 `StartupProfileManager` を置き換える場合でも、専用の移行決定と PR が必要です。

用語:

- `StartupProfileManager` は、`rumi_cli`、`rumi_desktopapp`、および `rumi_work` などの起動時スタートアップ プロファイルを所有します。
- `CapabilityProfileDefinition` は、`defaultspack.coding` などの `rumi.profile.v1` グラフ/ランタイム プリセットを所有します。
- 機能プロファイルの `default_graph` はコンパイル入力のみです。スタートアップ プロファイルの起動では、この PR 内のグラフが自動的にコンパイルされません。
- 起動プロファイルの起動からケイパビリティ グラフのコンパイル/ランタイム登録へのブリッジングは、起動コントラクトが明示的に設計されるまでは意図的に範囲外になります。

## グラフとの関係

グラフとプロファイルは別個です。

- グラフは能力配線図です。
- プロファイルは、その配線図の実行時のプリセット、環境、権限、デフォルト、およびノードの可用性です。

グラフ コンパイラは常に `graph_id` と `profile_id` の両方を受け取ります。

## スキーマ

```yaml
profile_id: coding
version: rumi.profile.v1
kind: runtime_profile
display_name:
  en: Coding
  ja: コーディング
locale: en
default_graph: coding_workspace
default_flow: coding_startup
enabled_nodes:
  - rumi.start
  - defaultspack.agent
  - defaultspack.tool.registry
disabled_nodes:
  - defaultspack.experimental.remote_shell
viewer:
  palette:
    include:
      - defaultspack.agent
      - defaultspack.tool.registry
permissions:
  can_install_packs: false
  can_create_profile: true
  can_update_profile: true
  can_delete_profile: false
policy:
  max_tool_calls: 8
  require_approval_for_tools: true
node_settings:
  defaultspack.agent:
    model_profile: default
```

## 必須フィールド

- `profile_id`
- `version`
- `kind`

## 共通フィールド

- `enabled_nodes`
- `disabled_nodes`
- `default_graph`
- `default_flow`
- `viewer.palette`
- `permissions`
- `policy`
- `node_settings`
- `locale`

## ノードの可用性

プロファイル対応ノード レジストリは以下から派生します。

```text
global node registry + selected profile
```

フェーズ 1 の動作:

- `disabled_nodes` にリストされているノードは利用できません
- `enabled_nodes` が空でない場合、リストされたノードのみが使用可能です
- `enabled_nodes` が空または存在しない場合、無効化されたノードを除くすべてのグローバル ノードが使用可能になります

グラフの検証とコンパイルでは、使用できないノードを使用するグラフを拒否する必要があります。

## ノードの状態

プロファイル ノードの状態は、ノード定義とは別に計算する必要があります。

予想される状態カテゴリ:

- 有効
- 無効
- 欠落している定義
- missing_configuration
- 利用不可

最初のプロファイル PR には、後でプロファイル認識グラフ検証とビューア パレット フィルタリングをサポートするのに十分な構造のみが必要です。

## インターフェースレジストリ

読み込まれたプロファイルは次のように登録されます。

```text
profile.<profile_id>
```
