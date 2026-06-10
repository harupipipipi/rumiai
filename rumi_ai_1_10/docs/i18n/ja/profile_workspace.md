<!-- docs-i18n-links:start -->
[EN](../../profile_workspace.md) | [JP](./profile_workspace.md) | [KR](../ko/profile_workspace.md) | [CN](../zh-cn/profile_workspace.md)
<!-- docs-i18n-links:end -->

# プロファイルワークスペース

プロファイル ワークスペースは `<RUMI_USER_DATA>/profiles/<profile_id>/` の下に存在し、従来の `settings/startup_profiles.json` を削除せずにプロファイルごとのランタイム データを分離します。

```text
profiles/<profile_id>/
  profile.yaml
  user_data/
  database/rumi.sqlite
  startup/launch.yaml
  startup/surface.yaml
  flows/
  prompts/
  ecosystem/snapshots/
  permissions/grants.yaml
  permissions/tool_policy.yaml
  permissions/approvals.yaml
  audit/events.jsonl
```

`profile.yaml` は、スタートアップ プロファイルのコア フィールド (ID、パックとグラフの選択、実行時プロファイル フィールド、ポリシー、アクセス許可のデフォルト、ノード オーバーライド、およびタイムスタンプ) を反映します。

`user_data/` は、将来のプロファイルごとのランタイム データ ルートです。 `database/rumi.sqlite` は、リゾルバ API によって返されるプロファイル スコープのデータベース パスです。 `startup/` は、起動および表面構成を保存します。 `flows/` および `prompts/` はプロファイルのオーバーライドを保持します。 `ecosystem/snapshots/`には、コピーされたdefaultspackリソースのロックファイルが含まれています。 `permissions/` はデフォルトのソースであり、許可バイパスではありません。 `audit/events.jsonl` は、プロファイル スコープのイベントを記録します。

移行では、`<RUMI_USER_DATA>/settings/startup_profiles.json` を読み取り、欠落している `profile.yaml` ファイルを作成し、`profiles/active_profile.json` を書き込み、`profiles/.migration_state.json` を記録します。レガシー ファイルは、ストアが完全に移動されるまで、StartupProfileManager 状態の互換性ソースとして残ります。

## ランタイムデータベースのスコープ

この PR では、`resolve_runtime_database_path()` によるプロファイル データベース パス解決と、`resolve_runtime_user_data_dir()` によるプロファイル ユーザー データ ルート解決を導入しています。プロファイルを作成または起動すると、`<RUMI_USER_DATA>/profiles/<profile_id>/database/rumi.sqlite` が初期化され、起動ペイロードとアクティブなエコシステム メタデータでそのパスが公開されます。

この PR では、すべてのランタイム ストアがプロファイル スコープのデータベースにまだ移行されていません。ストアがすでに明示的に接続されていない限り、ランタイム ストアのプロファイル スコープの DB およびプロファイル スコープのユーザー データへの完全な移行は引き続きフォローアップとなります。

フォローアップの TODO:

- ChatStore: チャット永続性を開く前に `resolve_runtime_database_path()` を使用します。
- MemoryStore: SQLite ベースのメモリには `resolve_runtime_database_path()` を使用します。
- 設定マネージャーと設定ファイル: 従来のグローバル ユーザー データ ルートの代わりに `resolve_runtime_user_data_dir()` を使用します。
- 添付ファイルとアップロードされたファイル: プロファイル スコープのストレージには `resolve_runtime_user_data_dir()` を使用します。
