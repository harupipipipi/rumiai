<!-- docs-i18n-links:start -->
[EN](../../competitive_agent_install_eval.md) | [JP](./competitive_agent_install_eval.md) | [KR](../ko/competitive_agent_install_eval.md) | [CN](../zh-cn/competitive_agent_install_eval.md)
<!-- docs-i18n-links:end -->

# 競合エージェントのインストール評価

日付: 2026-06-03

このメモは、デフォルトパックに対して実行されたデフォルトパックのインストール/オンボーディングチェックを記録します。
Genspark、Manus、Cline、Hermes、OpenClaw の現在のパブリック インストール フロー。
これは、defaultspack をブラウザファーストとの競争力を維持することを目的としています。
ローカルファーストのセキュリティモデルを弱めることなく、エージェントランタイム製品を実現します。

## テストされたフロー

|製品 |観察されたインストールまたは起動パス |実用的なバーのデフォルトパックは次の条件を満たす必要があります。
| --- | --- | --- |
|ゲンスパーク | `https://www.genspark.ai/ja` にあるブラウザ ワークスペース。Claw、ワークフロー、ドライブ、アプリのエントリ ポイントが表示されます。 |最初の画面では、ドキュメントを読まなくてもチャット、ツール、ワークスペース、設定を見つけられるようにする必要があります。 |
|マヌス | `https://manus.im/app`のブラウザアプリ。 |アプリ シェルは 1 つの URL からロードし、認証ゲートまたは空の初期状態を許容する必要があります。 |
|クライン |公式インストール ドキュメントには、IDE 拡張機能、CLI、カンバン、SDK のパスが記載されています。 IDE のインストールは、拡張機能を開き、Cline を検索し、インストールし、アクティビティ バーを開き、プロバイダーを認証します。 CLI インストールは、`npm install -g cline`、`cline auth`、次に `cline` です。 | defaultspack は、UI ファーストとコマンドファーストの両方のセットアップをサポートする必要があり、プロバイダーのセットアップはインストール後に明示的に行う必要があります。 |
|エルメス | `NousResearch/hermes-agent` GitHub ページでは、インストーラー、デスクトップ ビルド、ゲートウェイ、プロバイダー、プラグイン、スキル、ダッシュボード サーフェスを備えた大規模なエージェント ランタイムが公開されています。 | defaultspack には、生のチャットだけではなく、目に見えるプロバイダー、ツール、承認、ダッシュボードのプリミティブが必要です。 |
|オープンクロウ |公式ドキュメントには、インストーラー スクリプト、npm install、オンボーディング、ゲートウェイ ステータス、ダッシュボードの起動、およびチャネルのセットアップが記載されています。 Windows インストーラは `iwr -useb https://openclaw.ai/install.ps1 | iex` です。オンボードなしモードについても文書化されています。 | defaultspack には、短いインストール パス、ネットワークなし/キーなしのローカル モード、およびゲートウェイ/UI/モデルのステータスに関する次のステップのチェックをクリアする必要があります。 |

##defaultspack 結果

- `python -m rumi_ai --health` は、ディスクおよび書き込み可能な温度プローブに対して `UP` を返しました。
- `ecosystem/defaultspack/webapp`の`npm test`は207のテストに合格しました。
- `npm run build` はプロダクション シェル アセットを作成しました。
- Chrome は `http://127.0.0.1:39766/` で開発 UI を開き、
  デフォルトパックの豪華なシェル。
- `npm run lint` は、lint スクリプトが使用されていたために Windows で最初は失敗しました
  `new URL(...).pathname`、`C:\C:\...` を生成します。これは修正されました
  `fileURLToPath(import.meta.url)`。

## 競合他社のローカル インストールに関する注意事項

- `npm install --prefix work/competitor-installs/cline cline@3.0.15` 完了、
  `cline --help` はプロバイダー認証、ローカル データ ディレクトリ、ワークツリー、フック、MCP、
  ハブ、スケジューラ、およびカンバン コマンド。
- `npm install --prefix work/competitor-installs/hermes --ignore-scripts
  hermes-agent@0.15.2` completed, but `hermes-agent --help` が失敗しました
  この Windows 環境では `ModuleNotFoundError: No module named 'run_agent'` です。
- `npm install --prefix work/competitor-installs/openclaw openclaw@2026.5.28`
  ポストインストール/ヘルスプロセスがまだ実行されている間に 5 分を超えました。
  2回目の`--ignore-scripts`の試行も3分を超えました。これにより、
  OpenClaw のインストーラーは機能すれば魅力的ですが、パッケージのインストールは面倒です。
  defaultspack のローカルファースト スタートよりも重い操作パス。

## OpenCode Zen チェック

- `https://opencode.ai/zen/go/v1/models` への Python/urllib の直接アクセス
  この環境では Cloudflare エラー 1010 によってブロックされました。
- 提供された Zen キーを使用して Chrome チャネル API にアクセスすると、現在のモデルが返されました
  `minimax-m3` および `qwen3.7-max` を含むリスト。
- `minimax-m3` のライブ完了試行は OpenCode に到達しましたが、
  `CreditsError` ワークスペースには支払い方法が設定されていないためです。
-defaultspack には `opencode-go/minimax-m3` と
  Python プロバイダーのホワイトリストと静的な両方の `opencode-go/qwen3.7-max`
  プロバイダーモデルのカタログ。

## 競争準備チェックリスト

- クラウドキーなしでローカルファーストスタート。
- 1 つのローカルホスト URL から UI シェルを表示。
- クローン/ビルド時ではなく、インストール後にプロバイダー キーをセットアップします。
- モデル カタログには、評価者が使用する現在の OpenCode Zen モデルが含まれています。
- ブラウザ/コンピュータ/ツールの承認は引き続き明示的かつ監査可能です。
- Windows lint/build パスは、ワークスペースの絶対パスで機能します。
- インストールの証拠は、ヘルス、ユニット、リント、ビルド、Chrome から再現可能です。
  煙チェック。
