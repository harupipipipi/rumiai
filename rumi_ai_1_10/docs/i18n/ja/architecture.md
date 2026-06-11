<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](./architecture.md) | [KR](../ko/architecture.md) | [CN](../zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — アーキテクチャ

全体の設計や仕組みを説明した資料です。パック開発者については [pack-development.md](./pack-development.md)、オペレータについては [operations.md](./operations.md) も参照してください。

---

## 目次

1. [設計原則](#設計原則)
2. [フローシステム](#フローシステム)
3. [python_file_call](#python_file_call)
4. [フローモディファイア](#フローモディファイアー)
5. [セキュリティモデル](#セキュリティモデル)
6. [パック承認](#パックの承認)
7. [ネットワーク許可と出力プロキシ](#ネットワーク権限と出力プロキシ)
8. [能力制度(信託+助成)](#能力制度（信託＋助成）)
9. [UDS ソケットのアクセス許可](#udsソケット権限)
10. [階層的権限](#hierarchy-authority)
11. [秘密](#秘密)
12. [共有辞書](#共有辞書)
13. [ライブラリシステム](#ライブラリシステム)
14. [pip依存ライブラリの紹介](#pip-dependency-library-installation)
15. [Pack Import / Apply](#pack-import--apply)
16. [コンポーネントコンセプト](#コンポーネントの概念)
17. [vocab / converter](#vocab--converter)
18. [監査ログ](#監査ログ)
19. [エクスポート保留中](#エクスポート保留中)
20. [DIコンテナとサービス一覧](#di-container-and-service-list)
21. [カーネルミックスイン設定](#カーネルミックスインの設定)
22. [可観測性](#可観測性)
23. [共通基盤モジュール](#共通ベースモジュール)
24. [パック開発ツール](#開発ツールをパックする)
25. [非推奨の機能](#廃止された機能)

---

## 設計原則

### えこひいきはしない

公式コアにはドメイン概念 (チャット、ツール、プロンプト、AI クライアント、フロントエンドなど) がありません。公式が提供しているのは汎用の実行プラットフォームです。

正式に提供されるメカニズムは、フロー実行、認可ゲート (ハッシュ検証)、分離実行 (Docker/UDS)、Trust + Grant (機能)、および監査ログに限定されます。

### 悪意のある仮定 (脅威モデル)

パック 作成者に悪意がある可能性を常に想定してください。パックの実行は通常、Docker `--network=none` で分離されます。外部通信とホスト権限は機能 (信頼 + 許可) によって仲介され、明示的な許可がなければ機能しません。

### フェイルソフト

一部が壊れてもOS全体が止まることはありません。失敗したコンポーネントは無効になり、診断と監査にログインして続行します。

### ホスト権限の単一エントリ ポイント

ホスト上の危険なこと (外部通信、ファイル アクセス、アプリケーションの更新など) は Pack から直接実行されるのではなく、機能によって仲介されます。許可を与えないと動きません。

---

## フローシステム

### 概要

フローは、パック間の接続と実行順序を定義する YAML ファイルです。各フローはフェーズとステップで構成されます。

### フローファイル形式

```yaml
flow_id: ai_response
inputs:
  user_input: string
  context: object
outputs:
  response: string

phases:
  - prepare
  - generate
  - postprocess

defaults:
  fail_soft: true
  on_missing_step: skip

steps:
  - id: load_context
    phase: prepare
    priority: 10
    type: handler
    input:
      handler: "kernel:ctx.get"
      args:
        key: "context"

  - id: call_ai
    phase: generate
    priority: 50
    type: python_file_call
    owner_pack: ai_client
    file: blocks/generate.py
    input:
      user_input: "${ctx.user_input}"
    output: ai_response
```

### フローソース

フローは次の順序でロードされます。同じ `flow_id` の場合、優先度の高いものが優先されます (下位のソースが上位のソースのフローを上書きすることはできません)。

|優先順位 |パス |使い方 |承認 |
|--------|------|------|------|
| 1 | `flows/` |公式フロー（起動・拠点） |不要 |
| 2 | `user_data/shared/flows/` |ユーザー/外部ツールによって配置された共有フロー |不要 |
| 3 | `ecosystem/<pack_id>/backend/flows/` |パックが提供するフロー |パックの承認が必要です |
| 4 | `ecosystem/flows/` (非推奨) | local_pack互換フロー | `RUMI_LOCAL_PACK_MODE=require_approval`の場合のみ有効です。承認が必要です |

上書きルール: 公式フローは誰も上書きできません。共有フローは公式フローをオーバーライドできませんが、パック提供のフローより優先されます。パックが提供するフローは、公式フローでも共有フローでも上書きできません。 local_pack の優先順位は最も低く、他のソースをオーバーライドすることはできません。

### ステップタイプ

|タイプ |説明 |
|------|------|
| `handler` |カーネルハンドラーを呼び出す |
| `python_file_call` | Pack で Python ファイルを実行する |
| `set` |コンテキストで値を設定 |
| `if` |条件分岐（簡易版） |
| `function` | FunctionRegistry に登録された関数を実行する (Wave 27) |
| `flow` |別のフローをサブフローとして呼び出す |

### 実行順序

ステップは次の順序で決定的にソートされます。

1. `phase` (`phases` 配列のソート順)
2. `priority` (昇順、小さいものが最初に実行されます)
3. `id` (アルファベット順・タイブレーク)

### 変数参照

```yaml
input:
  user_id: "${ctx.user.id}"     # ネスト参照
  settings: "${ctx.config}"      # オブジェクト全体
```

参照先が存在しない場合は`null`(フェイルソフト)として扱われます。

---

## python_file_call

### 概要

パック内の Python ファイルをフロー内のステップとして実行します。入力を受け取り、JSON 互換の出力を返す「ブロック」。

### ブロックファイル形式

```python
# ecosystem/<pack_id>/backend/blocks/my_block.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ
        context: 実行コンテキスト
            - flow_id, step_id, phase, ts
            - owner_pack
            - inputs
            - network_check(domain, port) -> {allowed, reason}
            - http_request(method, url, ...) -> ProxyResponse

    Returns:
        JSON 互換の出力データ
    """
    return {"message": "Hello from my_block!"}
```

### パス解決

`python_file_call` の `file` フィールドは、pack_subdir を基準にして解決されます。以下の候補が順番に検索されます。

1. `<pack_subdir>/blocks/`
2. `<pack_subdir>/backend/blocks/`
3. `<pack_subdir>/backend/components/` (互換性あり)
4. `<pack_subdir>/backend/` (互換性: 直接インストール)
5. `<pack_subdir>/<file>` (最終フォールバック)

すべての候補は、pack_subdir 境界内に制限されます。境界の外側にあるファイルは実行が拒否されます。

### セキュリティチェック(実行前)

1.`owner_pack`が承認される
2. `owner_pack` のハッシュは一致する必要があります (変更されていません)。
3. ファイル パスは、pack_subdir 境界内にある必要があります。

### プリンシパル ID の取り扱い (v1)

v1 では、`principal_id` は常に `owner_pack` によって強制的に上書きされます。フロー定義に`principal_id`を指定しても、実行時には`owner_pack`が使用されます。これは職権乱用を防止するための措置です。警告は監査ログに`principal_id_overridden`として記録されます。

---

## フロー修飾子

### 概要

これは、既存のフローに後からステップを挿入、置換、または削除できる仕組みです。モディファイアを使用すると、パックがお互いを認識していない場合でも、機能をプラグインできます。

### 修飾子のファイル形式

```yaml
modifier_id: tool_inject
target_flow_id: ai_response
phase: prepare
priority: 50
action: inject_after
target_step_id: load_context

requires:
  capabilities:
    - tool_support
  interfaces:
    - tool.registry

step:
  id: inject_tools
  type: python_file_call
  owner_pack: capability_provider
  file: blocks/capability_selector.py
  input:
    context: "${ctx.context}"
  output: selected_capabilities
```

### モディファイアの配置パス

モディファイアは、ファイル名 `*.modifier.yaml` で以下に配置する必要があります。

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/` (パックで提供されている場合)

### アクション

|アクション |説明 |ターゲットステップID |ステップ |
|--------|------|----------------|------|
| `inject_before` |指定したステップの前に挿入 |必須 |必須 |
| `inject_after` |指定したステップの後に挿入 |必須 |必須 |
| `append` |フェーズの最後に追加 |不要 |必須 |
| `replace` |指定されたステップを置き換える |必須 |必須 |
| `remove` |指定したステップを削除 |必須 |不要 |

### には条件が必要です

```yaml
requires:
  interfaces:
    - "ai.client"           # InterfaceRegistry に登録されているか
  capabilities:
    - "tool_support"        # capability が有効か
```

条件が満たされない場合、モディファイアはスキップされます (フェールソフト)。

### 申請順序

1.`phase`オーダー
2. `priority` 昇順
3. `modifier_id` 昇順

### solve_target (共有辞書で解決)

```yaml
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

`resolve_target: true` を指定した場合、`target_flow_id` は共有辞書で解決されてから適用されます。

---

## セキュリティモデル

### セキュリティモード

環境変数`RUMI_SECURITY_MODE`で設定します。

|モード |ドッカー |行動 |
|--------|--------|------|
| `strict` (デフォルト) |必須 | Docker が利用できない場合は実行を拒否 |
| `permissive` |不要 |警告付きでホストの実行を許可する (開発用) |

### 保護メカニズムのリスト

|メカニズム |説明 |
|------|------|
|承認ゲート |未承認のパック内のコードは実行されません。
|ハッシュ検証 |承認後にファイルが変更された場合の自動無効化 |
| HMAC 署名 |許可ファイルの改ざんが検出されました |
|パスの制限 | Pack_subdir 境界外でのファイルの実行を拒否する |
| Docker の分離 | `--network=none`、`--cap-drop=ALL`、`--read-only` |
|出力プロキシ (UDS) |パック固有の許可リストを使用して外部通信を制御する |
| UDS グループの追加 |専用の GID を使用してソケットのアクセス許可を管理する |
|監査ログ |すべての操作を記録 |
|要件.ロックの検証 |サプライチェーン攻撃の防止 |
|パック ID 検証 |パック更新時の取り違えの防止 |
| DNSリバインディング対策 | DNS 解決結果の内部 IP 検査 |

### 脅威とその対策

|脅威 |対策 |
|------|------|
|悪意のあるコードの実行 |認可が必要 + Docker 分離 |
|ファイル改ざん | SHA-256 ハッシュ検証 |
|設定改ざん | HMAC 署名 |
|無効な外部通信 |出力プロキシ + ホワイトリスト |
|権限昇格 |パックによる明示的な付与 |
|サプライチェーン攻撃 |要件.lock 構文制限 + ホイールのみ |
|パックの取り違え | Pack_identity 比較により拒否されました |
| DNS の再バインド |解決結果の内部 IP 検査 |

---

## パックの承認

### 承認フロー

```
Pack 配置 (ecosystem/<pack_id>/)
    ↓
メタデータのみ読み込み（コード実行なし）
    ↓
ユーザー承認
    ↓
全ファイルの SHA-256 ハッシュを記録
    ↓
初めてコード実行可能に
```

### 承認ステータス

|ステータス |コードの実行 |説明 |
|------|-----------|------|
| `installed` | ❌ |配置済み、未承認 |
| `pending` | ❌ |承認待ち |
| `approved` | ✅ |承認済み |
| `running` | ✅ |承認され実行中 |
| `modified` | ❌ |承認後のファイル変更の検出 |
| `blocked` | ❌ |拒否されました |
| `error` | ❌ |エラーが発生しました（承認プロセスの失敗など） |

ファイルの変更により `modified` 状態になると、コードの実行とネットワークのアクセス許可が自動的に無効になります。再認証が必要です。

### パックのストレージ パス

パックは次のパスのいずれかに配置できます。

|パス |タイプ |説明 |
|------|------|------|
| `ecosystem/<pack_id>/` | **推奨** | `paths.py` は探索の最優先事項です。
| `ecosystem/packs/<pack_id>/` |レガシー |推奨パスと重複する場合は無視されます。

`paths.py`の`discover_pack_locations()`は、まず`ecosystem/*`を検索し、次に`ecosystem/packs/*`を互換ルートとして検索します。両方に同じ `pack_id` が存在する場合、`ecosystem/<pack_id>/` が優先されます。

---

## ネットワーク権限と出力プロキシ

### デザイン

パックは外部と直接通信できません (Docker `--network=none`)。すべての外部通信は、UDS ソケットを介して出力プロキシを通過します。

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部 API
                                        ↓
                                  network grant 確認
                                        ↓
                                    監査ログ記録
```

### UDS ベースのパック識別

UDS ソケットはパックごとに作成され、ソケット パスから `pack_id` が決定されます。リクエスト ペイロードの `owner_pack` フィールドは無視されます (セキュリティ対策)。

### ネットワーク助成金

```json
{
  "pack_id": "my_pack",
  "enabled": true,
  "allowed_domains": ["api.openai.com", "*.anthropic.com"],
  "allowed_ports": [443],
  "granted_at": "2024-01-01T00:00:00Z",
  "granted_by": "user",
  "_hmac_signature": "..."
}
```
ドメイン マッチングでは、完全一致 (`api.openai.com`) とワイルドカード (`*.anthropic.com`) がサポートされています。サブドメインを許可する場合は、ワイルドカード形式を使用して明示的に指定してください。

### Egress Proxy 防御メカニズム

内部IP禁止(localhost/プライベート/リンクローカル/CGNAT/マルチキャスト等)、DNSリバインディング対策(解決結果が内部IPの場合拒否)、リダイレクト制限(3ホップ、各ホップでグラント再確認)、リクエスト/レスポンスサイズ制限(1MB/4MB)、タイムアウト制限(最大120秒)、ヘッダー数/サイズ制限、メソッド制限(GET、HEAD、POST、PUT、DELETE、パッチ)。

### ウェーブ 12 ～ 14 の拡張

#### レート制限 (egress_rate_limiter.py)

Wave 12 で追加。パックごとのトークン バケットによるリクエスト レート制限を提供します。 Egress プロキシはリクエストを受け入れる前にバケットを検査し、バケットが空になると `429` を返します。

#### ドメイン制御 (egress_domain_controller.py)

Wave 12 で追加されました。 ホワイトリストに加えて、ドメインごとのきめ細かい制御 (ブロックリスト、ワイルドカード パターン) を提供します。

#### きめ細かいタイムアウト

Wave 12 で追加。接続タイムアウトと読み取りタイムアウトをドメインごとに設定できるようになりました。古いグローバル上限 (120 秒) はフォールバックとして維持されます。

#### モジュール分割 (ウェーブ 13)

Wave 13 では、Egress Proxy 実装を次のモジュールに分割しました。セキュリティチェックの実行順序も、IP検査→プロトコル検査→ドメイン検査→レート制限の順に整理・評価されます。

|モジュール |責任 |
|-----------|------|
| `egress_ip.py` |内部IP検査、DNSリバインディング対策 |
| `egress_protocol.py` |プロトコルメソッドヘッダー検査 |
| `egress_rate_limiter.py` |パック単位のレート制限 |
| `egress_domain_controller.py` |ドメインのホワイトリスト/ブロックリストの制御 |

#### 重複コードの削除 (W14-FIX)

Wave 14では、分割後のモジュール間に残った冗長なコード(IP検査ロジックなど)を削除し、単一責任を確保しました。

---

## 能力システム (信託 + 助成金)

### 概要

これは、パックによって提供される機能ハンドラーを承認して運用環境に導入し、プリンシパルに使用権を付与 (グラント) するためのメカニズムです。信託と補助金は独立して管理されます。

- **信頼**: `handler_id` + `sha256` の許可リスト。 handler.py の内容が信頼できるかどうかを判断する
- **助成金**: `principal_id` × `permission_id` の助成金。誰がどの機能を使用できるかを管理する

### 全体の流れ

```
候補配置 (ecosystem/<pack_id>/share/capability_handlers/<slug>/)
    ↓
scan（候補検出）
    ↓
pending（承認待ち）
    ↓
approve（Trust 登録 + コピー + Registry reload）
    ↓
Grant 付与（principal × permission）
    ↓
使用可能
```

承認は信頼のみを登録します。実際の利用には別途助成金が必要となります。

### 候補状態遷移

|状態 |説明 |
|------|------|
| `pending` |候補者が検出され承認を待っています |
| `installed` |承認された。トラスト登録＋コピー完了 |
| `rejected` |拒否されました。クールダウン後（1時間）スヌーズ可能 |
| `blocked` | 3 拒否のサイレントブロック。ブロックを解除するまで通知されません |
| `failed` |承認プロセス中にエラーが発生しました |

### 候補キー

候補者のアイデンティティは `candidate_key` で管理されます。

```
{pack_id}:{slug}:{handler_id}:{sha256}
```

sha256を含めることで、handler.pyの内容が変わった場合、別の候補として扱われるようになります。

### TOCTOU対策

承認時に handler.py の sha256 を再計算し、スキャン時の値と比較します。不一致がある場合、承認は失敗します。

### コピーして上書き

承認時には、`ecosystem/`側の候補が`user_data/capabilities/handlers/<slug>/`にコピーされます。エコシステム側はディストリビューションとして残り、移動されません。コピー先にhandlerが既に存在し、handler_idまたはsha256が異なる場合はエラーとなります(自動上書き禁止)。

### モジュール分割 (Wave 13)

Wave 13 では、機能関連のモデルとローダーが次のモジュールに分割されました。

|モジュール |責任 |
|-----------|------|
| `capability_models.py` |機能関連のデータ モデルの定義 |
| `flow_modifier_models.py` |フロー モディファイア関連のデータ モデル定義 |
| `flow_modifier_loader.py` |モディファイアファイルのロード/解析 |

### 機能システムとの統合 (フェーズ A ～ D)

Phase A～Dでは、旧`capability_handler_registry.py`が廃止され、`function_registry.py`(`FunctionRegistry`)に統合されました。すべての関数(カーネルハンドラ、core_pack関数、Pack提供関数)は`FunctionRegistry`に登録されており、`capability_executor.py`が統一して実行します。

#### 大きな変更点

`capability_handler_registry.py` が削除されました。あるいは、`core_runtime/function_registry.py` は、`FunctionRegistry` および `FunctionEntry` データ クラスを定義します。 `ManifestRegistry` は、`FunctionRegistry` (設計決定 D-6) の別名です。

#### FunctionEntry のキー フィールド

|フィールド |タイプ |説明 |
|-----------|-----|------|
| `function_id` | `str` |機能ID |
| `pack_id` | `str` |所属パックID |
| `qualified_name` | `str` (プロパティ) | `{pack_id}:{function_id}` (コロン区切り) |
| `calling_convention` | `Optional[str]` |実行方法。 7種のいずれか |
| `permission_id` | `Optional[str]` |助成金 ID (助成金の検証に使用) |
| `entrypoint` | `Optional[str]` |エントリポイント (例: `main.py:run`) |
| `risk` | `Optional[str]` |リスクレベル |
| `is_builtin` | `bool` |組み込み関数ですか？ |
| `runtime` | `str` | `python` / `binary` / `command` |
| `handler_py_sha256` | `Optional[str]` | handler.py の SHA-256 (信頼性検証用) |
| `vocab_aliases` | `Optional[List[str]]` |語彙別名 (`resolve_by_alias()` で検索可能) |
| `grant_config` | `Optional[Dict]` |付与設定 (None 以外の場合は付与検証を実行) |

#### 呼び出し規約(7種類)

|呼び出し規約 |説明 |
|-------------------|------|
| `kernel` |カーネル ハンドラーとして直接実行します。 `capability_executor` 経由では実行できません。
| `subprocess` |サブプロセスで実行 (エントリポイントを指定) |
| `block` | core_pack の DI サービス経由で実行 |
| `python_host` |ホスト Python で実行 (`RUMI_ALLOW_HOST_EXECUTION=1` が必要) |
| `python_docker` | Docker コンテナーで実行 (デフォルト) |
| `binary` |バイナリを直接実行する |
| `command` |任意のコマンドを実行します |

#### カーネル関数

`kernel.py` は `_KERNEL_HANDLER_MANIFESTS` を定義します。 `register_kernel_function()`、`pack_id="kernel"`、`calling_convention="kernel"`、`FunctionRegistry`には 70 (システム 29 + ランタイム 41) のハンドラーが登録されています。

#### 実行フロー

```
capability_executor.execute(principal_id, request)
    ↓
FunctionRegistry で permission_id を解決（resolve_by_alias）
    ↓
_unified_execute(entry, principal_id, request)
    ↓
Trust チェック（sha256 検証）
    ↓
Grant チェック（grant_config が非 None のとき）
    ↓
calling_convention で分岐実行
```

---

## UDS ソケット権限

### 問題

厳密モードでは、Pack 実行コンテナは `--user=65534:65534` (nobody) で実行されます。 UDS ソケットがデフォルトの `0660` (root:root) のままの場合、コンテナはソケットに接続できません。

### 解決策

専用のGIDを設定することで`0660`を維持したまま安全に接続することができます。

|環境変数 |説明 |デフォルト |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` |出口ソケット GID |なし |
| `RUMI_CAPABILITY_SOCKET_GID` |機能ソケット GID |なし |
| `RUMI_EGRESS_SOCKET_MODE` |出力ソケットのアクセス許可 | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` |機能ソケットの権限 | `0660` |

GID が設定されている場合、`docker run` で `--group-add=<GID>` が自動的に付与されます。

これは `RUMI_EGRESS_SOCKET_MODE=0666` / `RUMI_CAPABILITY_SOCKET_MODE=0666` で軽減できますが、任意のユーザーがソケットに接続できるようになるため、非推奨です。

---

## 階層的な権限

### 概要

`pack_id`を`parent__child`に変更することで、親子関係のあるパックを表現することができます。子は許可されているが、親は許可されていない場合、実行は拒否されます。

親の構成は、子に上限 (交差) を設定します。下位レベルだけを許可しても、上位レベルが許可しなければ機能しません。

---

## 秘密

APIキーなどのシークレット値を安全に管理します。

・`.env`を使用しない（事故率低減）
- `user_data/secrets/`に保存 (1 キー = 1 ファイル、墓石、ジャーナル)
- ログにシークレット値を表示しません (監査と診断の両方)
- 秘密ファイルを直接パックに見せないでください
- ケイパビリティ経由で取得 (例: `secrets.get`)
- APIは一覧(マスクあり)/設定/削除のみ(再表示なし)

---

## 共有辞書

### 概要

これは、任意の`namespace` / `token`を書き換えることができる仕組みです。当局は名前空間の意味を解釈しません（エコシステムが自由に決定します）。

### 安全機能

- **サイクル検出**: A→B→A のようなサイクルを自動的に拒否します。
- **衝突検出**: 同じトークンに異なる値を登録しようとすると拒否されます。
- **ホップ制限**: デフォルトの 10 ホップ後に解決を中止します。
- **監査ログ**: すべての操作を記録します。

### 永続性

`snapshot.json` (スナップショット) と `journal.jsonl` (ジャーナル) は `user_data/settings/shared_dict/` に保存されます。

---

## ライブラリシステム

### 概要

パックの初期化と更新処理を管理します。これは常駐せず、必要な場合にのみ実行されます。

### 実行タイミング

|状態 |実行するファイル |
|------|-------------------|
|最初の導入 (記録なし) | `lib/install.py` |
|ハッシュを変更する | `lib/update.py` (`install.py` でない場合) |
|変化なし |実行しないでください |

### Docker の分離

厳密モードでは、Docker コンテナ内で分離して実行されます。 `--network=none`、`--cap-drop=ALL`、`--read-only`、`--memory=256m`。 RW マウントは `user_data/packs/{pack_id}/` (コンテナ内: `/data`) のみに限定されます。

---

## pip 依存ライブラリのインストール

### 概要

パックは `requirements.lock` を含めることで PyPI パッケージへの依存関係を宣言できます。ユーザーが API を通じて認証すると、ビルダーの Docker コンテナに安全にダウンロードされ、インストールされます。ホストの Python 環境は汚れていません。

### 要件.ロック規則

`NAME==VERSION` 行のみが許可されます (コメント/空白行は許可されます)。以下は禁止されています: `-e` (編集可能)、`git+` / `http://` / `https://` (URL/VCS 参照)、`file:` / `../` / `/` (ローカル参照)、`--` オプション行、`@` 直接参照。

### 状態遷移

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### セキュリティ

ホイールのみがデフォルトです (`--only-binary=:all:`)。 sdistが必要な場合は承認時に`allow_sdist: true`を指定してください。ビルダー コンテナー (ダウンロード) は `--network=bridge` + `--cap-drop=ALL` で実行され、ビルダー コンテナー (インストール) は `--network=none` (完全にオフライン) で実行されます。実行コンテナから、サイト パッケージは読み取り専用でマウントされ (`/pip-packages:ro`)、`PYTHONPATH` に追加されます。

### index_url 制約

`https` スキームのみが許可されます。ホスト名が localhost / 127.0.0.1 / ::1 / private IP / link-local の場合は拒否されます。

---

## パックのインポート/適用

### インポート

フォルダー / `.zip` / `.rumipack` (zip 互換) からパックをステージングに持ち込みます。 「単一の最上位ディレクトリが必要」や zip スリップ/サイズ制限などの保護が zip 構造に適用されます。

### 申し込む

ステージングからエコシステムまで適用されます。バックアップが自動的に作成されます。申請の際、`pack_id`と`pack_identity`(`ecosystem.json`の`pack_identity`フィールド)の両方を比較し、既存のパックと不一致がある場合は拒否されます。

---

## コンポーネントの概念

### 概要

`backend_core/ecosystem/registry.py` は `pack_subdir/components/*/manifest.json` を読み取り、`ComponentInfo` を構築します。コンポーネントとは、セットアップなどのライフサイクル管理の単位です。

### python_file_call との関係

`python_file_call`にはコンポーネントを特別扱いしてブロックを自動検索する機能はありません。 `components/{component_id}/blocks/` にあるファイルを実行する場合は、`file` フィールドに相対パスを指定します。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

---

## 語彙 / コンバーター

> **注意**: この機能は、互換性吸収のための高度な機能です。通常の Pack 開発では使用する必要はありません。

### vocab.txt (同義語グループ)

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

同じ行に書かれた単語は同義語として扱われます。

### コンバータ

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

### コンバータのセキュリティチェック

#### 問題

`ConverterASTChecker` は、コンバータ スクリプトの AST 解析を実行し、`blocked_imports` (`os`、`subprocess`、`socket` など) の使用を検出して拒否します。ただし、現在のチェックはコンバータ ファイルのみを対象としています。コンバーターが `from .helper import func` や `import local_module` などのローカル モジュールをインポートする場合、インポートされたファイルにブロックされたインポートが含まれている場合でも、ブロックされたインポートを検出できません。

```
converter.py          ← 検査される（Level 0）
 └─ import helper     ← helper.py は検査されない
     └─ import os     ← blocked import が素通り
```

#### 検査レベルの定義

|レベル |検査範囲 |利点 |デメリット |導入コスト |
|--------|---------|----------|-----------|-----------|
|レベル 0 (現在) |単一のコンバータ ファイル |実装が速く、副作用なし |ブロックされたインポートは、ローカル インポートを介してバイパスできます。なし |
|レベル 1 (推奨) |コンバータ + 同じディレクトリ内の `.py` の再帰的走査 |最も一般的なバイパス パターンを防止します。シンプルな実装 |同じディレクトリ外の依存関係はチェックされません。低 (約 50 行) |
|レベル 2 | Pack_subdir にわたるインポート グラフの再帰的走査 |完全な依存関係ツリーを検査できます。実装が複雑。再帰の深さの管理、循環の検出、およびパスの解決を考慮する必要があります。パフォーマンスコスト付き |中～高 (約 150 行) |

#### 推奨: レベル 1

次のウェーブではレベル 1 を実装することをお勧めします。

- コンバータのローカル依存関係は通常同じディレクトリに配置されます (`converters/` の下にヘルパーを配置するパターン)
- 同じディレクトリ内に限定するとパス解決が簡単になり、誤検知のリスクが低くなります。
- レベル 2 は、コンバータが複数のディレクトリにまたがるように設計されていることを前提としていますが、現在のコンバータ ルールではそのようなケースはまれです。

レベル 2 は、ユースケースが確認され次第検討されます。

#### レベル 1 の擬似コード

```python
def check_converter_with_locals(
    converter_path: Path,
    blocked: set[str],
) -> list[str]:
    """converter と同一ディレクトリのローカル .py を再帰的に AST 検査する。"""
    violations: list[str] = []
    converter_dir = converter_path.parent
    visited: set[Path] = set()

    def _check(target: Path) -> None:
        if target in visited:
            return                          # 循環 import 防止
        visited.add(target)
        tree = ast.parse(target.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # ast.Import      → [alias.name for alias in node.names]
            # ast.ImportFrom   → node.module（相対 import の場合 None あり）
            for name in _extract_module_names(node):
                if name in blocked:
                    violations.append(f"{target.name}: blocked import '{name}'")
                # 同一ディレクトリに .py があればローカル依存として再帰検査
                local = converter_dir / f"{name.split('.')[0]}.py"
                if local.exists() and local != target:
                    _check(local)

    _check(converter_path)
    return violations
```

> `_extract_module_names()` は、`ast.Import` / `ast.ImportFrom` ノードからモジュール名文字列のリストを返すヘルパーです。既存の `ConverterASTChecker` ロジックを再利用できます。

#### テスト計画 (レベル 1)

| # |シナリオ |期待される結果 |
|---|---------|---------|
| 1 |コンバータ単体`import subprocess` |拒否 |
| 2 |コンバータ → `from .helper import x` → `helper.py` から `import os` |拒否 (ローカル依存関係によるインポート検出のブロック) |
| 3 |コンバータ → `from .helper import x` → `helper.py` はきれいです |許可される |
| 4 |コンバータ → `import requests` (外部パッケージ、ローカルに `.py` はありません) |許可 (ローカル ファイルがないためスキップ) |
| 5 |コンバータ → `helper.py` → `from .utils import y` → `utils.py` から `import socket` |拒否 (再帰スキャンによって検出) |
| 6 |循環インポート: コンバーター → ヘルパー → コンバーター |無限ループせずに正常に終了します (訪問セットによって阻止されます) |
| 7 |コンバータ ディレクトリの外にインポート (`from ..other import z`) |スキップ（レベル1の検査対象外。レベル2で対応） |

---

## 監査ログ

### 概要

すべての重要な操作は、JSON Lines 形式で `user_data/audit/` に記録されます。

### カテゴリ

|カテゴリー |目次 |
|----------|------|
| `flow_execution` |フローの実行 |
| `modifier_application` |モディファイアを適用 |
| `python_file_call` |ブロック実行 |
| `approval` |パック承認操作 |
| `permission` |権限操作 (ネットワーク許可、機能許可を含む) |
| `network` |ネットワーク通信 |
| `security` |セキュリティイベント |
| `system` |システム イベント (lib、pip、保留中のエクスポートなど) |

### ファイルの命名

`{category}_{YYYY-MM-DD}.jsonl`

ファイル名の日付は、エントリの `ts` (タイムスタンプ) から決定されます。 0時を越えてもエントリーの`ts`に該当するファイルに振り分けられます。 `ts` が無効な場合は、書き込み時の日付に戻ります。

### エントリ構造

```json
{
  "ts": "2024-01-01T00:00:00Z",
  "category": "python_file_call",
  "severity": "info",
  "action": "execute_python_file",
  "success": true,
  "flow_id": "ai_response",
  "step_id": "generate",
  "phase": "generate",
  "owner_pack": "ai_client",
  "execution_mode": "container",
  "details": {
    "file": "blocks/generate.py",
    "execution_time_ms": 150.5
  }
}
```

---

## エクスポート保留中

### 概要

`user_data/pending/summary.json`は起動時に自動生成されます。外部ツールはこのファイルを読み込むだけで承認状況を把握できます。当局はこのファイルの消費者を特別扱いしません (えこひいき禁止)。

### 出力形式

```json
{
  "ts": "2026-02-11T15:00:00Z",
  "version": "1.0",
  "packs": {
    "pending_count": 2,
    "pending_ids": ["pack_a", "pack_b"],
    "modified_count": 1,
    "modified_ids": ["pack_c"],
    "blocked_count": 0,
    "blocked_ids": []
  },
  "capability": {
    "pending_count": 1,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 3
  },
  "pip": {
    "pending_count": 0,
    "rejected_count": 0,
    "blocked_count": 0,
    "failed_count": 0,
    "installed_count": 2
  }
}
```

各モジュールをインポートできない場合、そのセクションには `"error"` キー (フェールソフト) が含まれます。

---

## DIコンテナとサービスのリスト

### 概要

`backend_core/di_container.py` は、Rumi AI OS 全体で使用される軽量の DI (Dependency Injection) コンテナです。すべてのサービスはコンテナーに登録され、名前で取得されます。 `get_container()` を介してグローバル シングルトンとしてアクセスします。

### DIContainer クラス

|方法 |説明 |
|---------|------|
| `register(name, factory)` |ファクトリ関数を名前で登録します。最初にインスタンス化 `get` (遅延生成) |
| `get(name)` |インスタンスを取得します。登録されていない場合は`KeyError` |
| `get_or_none(name)` |インスタンスを取得します。登録されていない場合は`None` |
| `has(name)` |登録されているかどうかを確認する |
| `reset()` |すべての登録をクリアする |
| `set_instance(name, instance)` |既存のインスタンスを直接登録します (テスト用) |

### グローバルアクセス

|機能 |説明 |
|------|------|
| `get_container()` |グローバル コンテナー (シングルトン) の取得 |
| `reset_container()` |グローバル コンテナをリセットします (テスト用) |

### 登録サービス一覧（32サービス）

|波 |サービス名 |
|------|-----------|
|ウェーブ 1 | `audit_logger`、`hmac_key_manager` |
|ウェーブ 2 | `vocab_registry`、`network_grant_manager`、`store_registry` |
|ウェーブ 3 | `approval_manager`、`permission_manager` |
|ウェーブ 4 | `container_orchestrator`、`host_privilege_manager`、`flow_composer`、`function_alias_registry`、`secrets_store`、`secrets_grant_manager`、`modifier_loader`、`modifier_applier` |
|ウェーブ 5 | `pack_api_server`、`egress_proxy_manager`、`python_file_executor`、`secure_executor`、`lib_executor`、`unit_executor`、`capability_executor` |
|ウェーブ 8 | `diagnostics`、`install_journal`、`interface_registry`、`event_bus`、`component_lifecycle` |
|ウェーブ 15 | `health_checker`、`metrics_collector`、`profiler` |
|ウェーブ 22 | `docker_capability_handler` |
|ウェーブ 24 | `function_registry` |

---

## カーネルミックスイン設定

### 概要

`backend_core/kernel.py` は 4 つの Mixin クラスを組み合わせてカーネルを構築します。単一ファイルの肥大化を回避しながら、関心ごとに実装を分離します。

### ミックスインリスト

|ミックスインクラス |ファイル |責任 |
|-------------|---------|------|
| `KernelCore` | `kernel_core.py` |エンジン本体。フロー読み込み、コンテキスト構築、シャットダウン |
| `KernelFlowExecutionMixin` | `kernel_flow_execution.py` |フロー実行、`depends_on` 解決、条件評価 |
| `KernelSystemHandlersMixin` | `kernel_handlers_system.py` |スタートアップ/システム ハンドラー (初期化、スキャン、承認など) |
| `KernelRuntimeHandlersMixin` | `kernel_handlers_runtime.py` |操作/実行ハンドラー (フロー実行、機能呼び出しなど) |

### 合成

```python
# kernel.py
class Kernel(
    KernelRuntimeHandlersMixin,
    KernelSystemHandlersMixin,
    KernelFlowExecutionMixin,
    KernelCore,
):
    pass
```

MRO (Method Resolution Order) は、Runtime → System → FlowExecution → Core の順に解決されます。各ミックスインは、`KernelCore` (`self.container`、`self.context` など) の属性に依存します。

---

## 可観測性

### 概要

Wave 15 で追加された 4 つのモジュールは、構造化されたログ、ヘルスチェック、メトリクス、プロファイリングを提供します。

### 構造化ログ (logging_utils.py)

`backend_core/logging_utils.py` は標準の `logging` をラップし、構造化された出力とコンテキストの伝播を提供します。

|クラス/関数 |説明 |
|--------------|------|
| `StructuredFormatter` |ログを JSON またはテキスト形式でフォーマットする |
| `StructuredLogger` | `logging.Logger` ラッパー。 `bind()` でのキーと値のコンテキストの指定 |
| `CorrelationContext` |スレッドセーフ `correlation_id` 管理。リクエストごとのトレースに使用されます。
| `get_structured_logger(name)` |キャッシュのあるファクトリー。同じ名前で呼び出すと同じインスタンスが返されます。
| `configure_logging()` |グローバル ログ設定 (レベル、形式) を一度に適用する |

環境変数 `RUMI_LOG_LEVEL` (デフォルトは `INFO`) および `RUMI_LOG_FORMAT` (`json` または `text`、デフォルトは `text`) が動作を制御します。

### ヘルスチェック (health.py)

`backend_core/health.py` は、プローブベースのヘルスチェックメカニズムを提供します。 `app.py --health`から使用。

|クラス/関数 |説明 |
|--------------|------|
| `HealthChecker` |プローブを登録し、タイムアウトと並行して実行し、結果を集計します。
| `HealthStatus` | `UP` / `DOWN` / `DEGRADED` / `UNKNOWN`の4状態 |
| `probe_disk_space` |空きディスク容量の確認 (内蔵プローブ) |
| `probe_memory` |メモリ使用量の検査 (内蔵プローブ) |
| `probe_file_writable` |ファイルに書き込み可能かどうかを確認する (組み込みプローブ) |

全てのプローブが`UP`の場合は全てのプローブも`UP`と判定され、いずれかが`DOWN`の場合は`DEGRADED`と判定され、全てのプローブが`DOWN`の場合は`DOWN`と判定されます。

### メトリクス (metrics.py)

`backend_core/metrics.py` は、アプリケーション メトリックを収集するための基盤を提供します。

|方法 |説明 |
|---------|------|
| `increment(name, labels, value)` |カウンタをインクリメント |
| `set_gauge(name, labels, value)` |セットゲージ |
| `observe(name, labels, value)` |ヒストグラムに値を記録する |
| `timer(name, labels)` |コンテキストマネージャー。ブロック実行時間を自動的に記録する |
| `snapshot()` |辞書内のすべてのメトリックの現在の値を返します。

ラベル (ディクショナリ) を使用すると、メトリクスを複数のディメンションに分類できます。 Wave 15 では、`kernel_flow_execution.py` (ステップ実行時間)、`kernel_handlers_system.py` / `kernel_handlers_runtime.py` (ハンドラ呼び出し回数/時間) に統合されました。

### プロファイリング (profiling.py)

`backend_core/profiling.py` は、関数とブロックの実行時間プロファイリングを提供します。

|メソッド/デコレータ |説明 |
|--------------------|------|
| `profile(name)` |コンテキストマネージャー。ブロック実行時間の記録 |
| `profile_func(name)` |同期関数のデコレータ |
| `profile_async(name)` |非同期関数のデコレータ |
| `summary()` | p50 / p95 / p99 パーセンタイルで概要を返す |

`max_samples` をメモリ制限として設定でき、制限を超えると古いサンプルは破棄されます。 Wave 15 の `kernel_flow_execution.py` (フロー実行時間、ステップ実行時間) に統合されました。

---

## 共通ベースモジュール

### 概要

Wave 12 ～ 15 で追加され、パッケージ間で共有される一連のユーティリティ。

### 共通の検証 (validation.py)

`backend_core/validation.py` は、Pack / Flow / Modifier の検証ユーティリティを提供します (Wave 12 が追加されました)。スキーマ検証、必須フィールド検証、値範囲検証などの共通ロジックを一元化し、各モジュールでの重複を排除します。

### 統合エラー システム (error_messages.py)

`backend_core/error_messages.py` は、Rumi AI OS 全体で統一されたエラー コード システムを定義します。

|要素 |説明 |
|------|------|
| `ErrorCode` |凍結されたデータクラス。 `RUMI-{CAT}-{NNN}` 形式 (例: `RUMI-AUTH-001`) |
|カテゴリー | `AUTH` (認証)、`NET` (ネットワーク)、`FLOW` (フロー)、`PACK` (パック)、`CAP` (機能)、`VAL` (検証)、`SYS` (システム) |
| `RumiError` |統一例外クラス。 `code`、`message`、`details`、`suggestion`を保持 |
| `format_error()` |テンプレート拡張ヘルパー。メッセージ内のプレースホルダーを動的に埋める |

エラーコードは自動収集レジストリで管理されており、モジュールロード時に自動的にレジストリに登録されます。

### 型定義 (types.py + py.typed)

`backend_core/types.py` は、パッケージ全体で使用される型定義を集約します。

|タイプ |定義 |
|------|------|
|ニュータイプ | `PackId`、`FlowId`、`CapabilityName`、`HandlerKey`、`StoreKey` |
|タイプエイリアス | `JsonValue`、`JsonDict` |
|ジェネリック | `Result[T]` (成功値またはエラーを保持) |
|列挙型 | `Severity`（`info`、`warn`、`error`、`critical`） |

`py.typed` 外部ツール (mypy など) で型チェックを可能にするためのマーカー ファイル (PEP 561) が含まれています。

### 非推奨管理 (deprecation.py)

`backend_core/deprecation.py` は、非推奨の API の管理と警告を提供します。

|要素 |説明 |
|------|------|
| `DeprecationInfo` |凍結されたデータクラス。非推奨のターゲット、バージョン、および代替を保持する |
| `DeprecationRegistry` |シングルトン。非推奨情報をスレッドセーフに管理する |
| `deprecated()` |関数/メソッドのデコレーター (非同期互換)。 | 呼び出し時に警告を出力する
| `deprecated_class()` |クラスのデコレーター。インスタンス作成時に警告が出力される |

環境変数 `RUMI_DEPRECATION_LEVEL` は動作を制御します: `warn` (デフォルト、警告を出力)、`error` (例外をスロー)、`silent` (無視)、`log` (ログのみ)。

---

## 開発ツールをパックする

### 概要

`backend_core/pack_scaffold.py` は、パック テンプレートを生成する CLI ツールです。

### PackScaffold クラス

4種類のテンプレートからPackのディレクトリ構造とファイルを自動生成します。

|テンプレート |説明 |
|------------|------|
| `minimal` |最小限の構成。 `ecosystem.json` + 空の `backend/` のみ |
| `capability` |ケイパビリティハンドラーあり。 `share/capability_handlers/`が含まれています。
| `flow` |フロー付き。 `backend/flows/` および `backend/blocks/` が含まれています。
| `full` |すべての要素を含むフルセット。 `lib/`、`converters/`、`modifiers/`などを含む。

生成されたファイルは、不正な構造を防ぐために `validation.py` で検証されます。

### CLI エントリ ポイント

```bash
python -m backend_core.pack_scaffold --template full --pack-id my_pack --output ecosystem/my_pack
```

`--template` (テンプレート名)、`--pack-id` (パック ID)、`--output` (出力パス) を指定します。

---

## 非推奨の機能

### エコシステム/フロー/（local_pack）

`ecosystem/flows/`に直接配置されたFlow/Modifierを仮想Packとして扱う互換モードです。デフォルトでは無効になっています (`RUMI_LOCAL_PACK_MODE=off`)。 `RUMI_LOCAL_PACK_MODE=require_approval` で有効にできますが、お勧めしません。

非推奨スケジュール: v2.0 では警告付きの互換モードが維持され、v3.0 で削除される予定です。

移行先：パックにして`ecosystem/<pack_id>/backend/`に置くか、`user_data/shared/flows/`に置きます。

### アドオンマネージャー

JSON パッチベースのアドオン メカニズムは `backend_core/ecosystem/addon_manager.py` に存在していましたが、フェーズ 2 で削除されました。現在コードベースには存在しません。

### フロー/ディレクトリ

古い `flow/` ディレクトリは非推奨になりました。パック内の`flows/`、`user_data/shared/flows/`、または`flows/`へ移動してください。

### 削除されたファイル

以下のファイル/ディレクトリが削除されました。

|削除対象 |交換 |理由 |
|---------|------|------|
| `capability_handler_registry.py` | `function_registry.py` | FunctionRegistry への統合 (フェーズ A ～ D) |
| `builtin_capability_handlers/` | `core_pack/` | core_pack に移行 |

# Defaultspack 関数の境界

Defaultspack は、関数マニフェストをパブリック操作境界として扱うようになりました。 HTTP ルートは互換性アダプターであり、AI ツールはオプションのファサードであり、Flow/function.call 呼び出しはすべて、ドメイン サービスに到達する前に同じdefaultspack 関数に収束します。
