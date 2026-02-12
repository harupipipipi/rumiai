

```markdown
# Rumi AI OS — Architecture

設計と仕組みの全体像を説明するドキュメントです。Pack 開発者は [pack-development.md](pack-development.md)、運用者は [operations.md](operations.md) も参照してください。

---

## 目次

1. [設計原則](#設計原則)
2. [Flow システム](#flow-システム)
3. [python_file_call](#python_file_call)
4. [Flow Modifier](#flow-modifier)
5. [セキュリティモデル](#セキュリティモデル)
6. [Pack 承認](#pack-承認)
7. [ネットワーク権限と Egress Proxy](#ネットワーク権限と-egress-proxy)
8. [Capability システム（Trust + Grant）](#capability-システムtrust--grant)
9. [UDS ソケット権限](#uds-ソケット権限)
10. [階層権限](#階層権限)
11. [Secrets](#secrets)
12. [共有辞書（Shared Dict）](#共有辞書shared-dict)
13. [lib システム](#lib-システム)
14. [pip 依存ライブラリ導入](#pip-依存ライブラリ導入)
15. [Pack Import / Apply](#pack-import--apply)
16. [Component 概念](#component-概念)
17. [vocab / converter](#vocab--converter)
18. [監査ログ](#監査ログ)
19. [Pending Export](#pending-export)
20. [Deprecated 機能](#deprecated-機能)

---

## 設計原則

### No Favoritism（贔屓なし）

公式コアはドメイン概念（チャット、ツール、プロンプト、AI クライアント、フロントエンド等）を一切持ちません。公式が提供するのは汎用の実行基盤です。

公式が提供する機構は以下に限定されます: Flow 実行、承認ゲート（hash 検証）、隔離実行（Docker / UDS）、Trust + Grant（capability）、監査ログ。

### 悪意前提（Threat Model）

Pack 作者に悪意がある可能性を常に想定します。Pack 実行は原則 Docker `--network=none` で隔離されます。外部通信やホスト特権は capability（Trust + Grant）で仲介し、明示的な許可がない限り動作しません。

### Fail-Soft

一部が壊れても OS 全体は停止しません。失敗したコンポーネントは無効化され、Diagnostics と Audit に記録して継続します。

### ホスト権限の単一入口

ホストで危険なこと（外部通信、ファイルアクセス、更新適用等）は、Pack から直接実行させず capability で仲介します。許可がない限り動きません。

---

## Flow システム

### 概要

Flow は Pack 間の結線・実行順序を定義する YAML ファイルです。各 Flow は phases（フェーズ）と steps（ステップ）で構成されます。

### Flow ファイル形式

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

### Flow 読み込み元

Flow は以下の順序で読み込まれます。同一 `flow_id` の場合は優先度の高い方が勝ちます。

| 優先度 | パス | 用途 |
|--------|------|------|
| 1 | `flows/` | 公式 Flow（起動・基盤） |
| 2 | `user_data/shared/flows/` | ユーザー/外部ツールが配置する共有 Flow |
| 3 | `ecosystem/<pack_id>/backend/flows/` | Pack 提供の Flow |

### ステップタイプ

| type | 説明 |
|------|------|
| `handler` | Kernel ハンドラを呼び出し |
| `python_file_call` | Pack 内の Python ファイルを実行 |
| `set` | コンテキストに値を設定 |
| `if` | 条件分岐（簡易版） |

### 実行順序

ステップは以下の順序で決定的にソートされます:

1. `phase`（`phases` 配列での並び順）
2. `priority`（昇順。小さいほど先に実行）
3. `id`（アルファベット順。タイブレーク）

### 変数参照

```yaml
input:
  user_id: "${ctx.user.id}"     # ネスト参照
  settings: "${ctx.config}"      # オブジェクト全体
```

参照先が存在しない場合は `null` 扱いになります（fail-soft）。

---

## python_file_call

### 概要

Flow のステップとして Pack 内の Python ファイルを実行します。入力を受け取り、JSON 互換の出力を返す「ブロック」です。

### ブロックファイルの形式

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

`python_file_call` の `file` フィールドは pack_subdir を基準に解決されます。以下の候補が順に探索されます:

1. `<pack_subdir>/blocks/`
2. `<pack_subdir>/backend/blocks/`
3. `<pack_subdir>/backend/components/`（互換）
4. `<pack_subdir>/backend/`（互換: 直置き）
5. `<pack_subdir>/<file>`（最終フォールバック）

全ての候補は pack_subdir boundary 内に制限されます。boundary 外のファイルは実行拒否されます。

### セキュリティチェック（実行前）

1. `owner_pack` が承認済み（approved）であること
2. `owner_pack` のハッシュが一致すること（modified でないこと）
3. ファイルパスが pack_subdir boundary 内であること

### principal_id の扱い（v1）

v1 では `principal_id` は常に `owner_pack` に強制上書きされます。Flow 定義で `principal_id` を指定しても、実行時は `owner_pack` が使用されます。これは権限の乱用事故を防ぐための措置です。監査ログには `principal_id_overridden` として警告が記録されます。

---

## Flow Modifier

### 概要

既存 Flow に後からステップを注入・置換・削除できる仕組みです。Pack 同士が互いを知らなくても、Modifier で機能を差し込めます。

### Modifier ファイル形式

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
  owner_pack: tool_pack
  file: blocks/tool_selector.py
  input:
    context: "${ctx.context}"
  output: selected_tools
```

### Modifier 配置パス

Modifier は `*.modifier.yaml` のファイル名で以下に配置します:

- `user_data/shared/flows/modifiers/`
- `ecosystem/<pack_id>/backend/flows/modifiers/`（Pack 提供の場合）

### アクション

| action | 説明 | target_step_id | step |
|--------|------|----------------|------|
| `inject_before` | 指定ステップの前に挿入 | 必須 | 必須 |
| `inject_after` | 指定ステップの後に挿入 | 必須 | 必須 |
| `append` | フェーズの末尾に追加 | 不要 | 必須 |
| `replace` | 指定ステップを置換 | 必須 | 必須 |
| `remove` | 指定ステップを削除 | 必須 | 不要 |

### requires 条件

```yaml
requires:
  interfaces:
    - "ai.client"           # InterfaceRegistry に登録されているか
  capabilities:
    - "tool_support"        # capability が有効か
```

条件が満たされない場合、Modifier はスキップされます（fail-soft）。

### 適用順序

1. `phase` 順
2. `priority` 昇順
3. `modifier_id` 昇順

### resolve_target（共有辞書での解決）

```yaml
modifier_id: compat_modifier
target_flow_id: old_flow_name
resolve_target: true              # オプトイン
resolve_namespace: "flow_id"      # デフォルト
```

`resolve_target: true` を指定すると、`target_flow_id` を共有辞書で解決してから適用します。

---

## セキュリティモデル

### セキュリティモード

環境変数 `RUMI_SECURITY_MODE` で設定します。

| モード | Docker | 動作 |
|--------|--------|------|
| `strict`（デフォルト） | 必須 | Docker 不可なら実行拒否 |
| `permissive` | 不要 | 警告付きでホスト実行を許可（開発用） |

### 保護機構一覧

| 機構 | 説明 |
|------|------|
| 承認ゲート | 未承認 Pack のコードは一切実行されない |
| ハッシュ検証 | 承認後にファイル変更されると自動無効化 |
| HMAC 署名 | Grant ファイルの改ざんを検出 |
| パス制限 | pack_subdir boundary 外のファイル実行を拒否 |
| Docker 隔離 | `--network=none`、`--cap-drop=ALL`、`--read-only` |
| Egress Proxy（UDS） | 外部通信を Pack 別 allowlist で制御 |
| UDS group-add | ソケット権限を専用 GID で管理 |
| 監査ログ | 全操作を記録 |
| requirements.lock 検証 | サプライチェーン攻撃防止 |
| pack_identity 検証 | Pack 更新時の取り違え防止 |
| DNS rebinding 対策 | DNS 解決結果の内部 IP 検査 |

### 脅威と対策

| 脅威 | 対策 |
|------|------|
| 悪意あるコード実行 | 承認必須 + Docker 隔離 |
| ファイル改ざん | SHA-256 ハッシュ検証 |
| 設定改ざん | HMAC 署名 |
| 不正な外部通信 | Egress Proxy + allowlist |
| 権限昇格 | Pack 単位の明示的 Grant |
| サプライチェーン攻撃 | requirements.lock 構文制限 + wheel-only |
| Pack 取り違え | pack_identity 比較で拒否 |
| DNS rebinding | 解決結果の内部 IP 検査 |

---

## Pack 承認

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

### 承認状態

| 状態 | コード実行 | 説明 |
|------|-----------|------|
| `installed` | ❌ | 配置済み、未承認 |
| `pending` | ❌ | 承認待ち |
| `approved` | ✅ | 承認済み |
| `modified` | ❌ | 承認後にファイル変更を検出 |
| `blocked` | ❌ | 拒否済み |

ファイル変更で `modified` 状態になると、コード実行とネットワーク権限が自動的に無効化されます。再承認が必要です。

### Pack 格納パス

Pack は以下のいずれかのパスに配置できます。

| パス | 種別 | 説明 |
|------|------|------|
| `ecosystem/<pack_id>/` | **推奨** | `paths.py` が最優先で探索 |
| `ecosystem/packs/<pack_id>/` | 互換（legacy） | 推奨パスと重複する場合は無視される |

`paths.py` の `discover_pack_locations()` は `ecosystem/*` を先に探索し、次に `ecosystem/packs/*` を互換ルートとして探索します。同一 `pack_id` が両方に存在する場合、`ecosystem/<pack_id>/` が優先されます。

---

## ネットワーク権限と Egress Proxy

### 設計

Pack は直接外部通信できません（Docker `--network=none`）。全ての外部通信は UDS ソケット経由で Egress Proxy を通過します。

```
Pack (network=none) → UDS Socket → Egress Proxy → 外部 API
                                        ↓
                                  network grant 確認
                                        ↓
                                    監査ログ記録
```

### UDS ベースの Pack 識別

Pack 別に UDS ソケットが作成され、ソケットパスから `pack_id` が確定されます。リクエスト payload の `owner_pack` フィールドは無視されます（セキュリティ上の措置）。

### Network Grant

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

ドメインマッチングは完全一致（`api.openai.com`）、ワイルドカード（`*.anthropic.com`）、サブドメイン許可（`openai.com` は `api.openai.com` も許可）に対応します。

### Egress Proxy の防御機構

内部 IP 禁止（localhost / private / link-local / CGNAT / multicast 等）、DNS rebinding 対策（解決結果が内部 IP なら拒否）、リダイレクト上限（3 ホップ、各ホップで grant 再チェック）、リクエスト / レスポンスサイズ制限（1MB / 4MB）、タイムアウト制限（最大 120 秒）、ヘッダー数 / サイズ制限、メソッド制限（GET, HEAD, POST, PUT, DELETE, PATCH）。

---

## Capability システム（Trust + Grant）

### 概要

Pack が提供する capability handler を承認・実働化し、principal（主体）に対して使用権限（Grant）を付与する仕組みです。Trust と Grant は独立して管理されます。

- **Trust**: `handler_id` + `sha256` の allowlist。handler.py の内容が信頼済みかを判定する
- **Grant**: `principal_id` × `permission_id` の権限付与。誰がどの capability を使えるかを管理する

### 全体フロー

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

approve は Trust のみを登録します。実際に使用するには別途 Grant の付与が必要です。

### 候補の状態遷移

| 状態 | 説明 |
|------|------|
| `pending` | 候補が検出され承認待ち |
| `installed` | 承認済み。Trust 登録 + コピー完了 |
| `rejected` | 却下。クールダウン（1 時間）後に再通知可能 |
| `blocked` | 3 回 reject でサイレントブロック。unblock まで通知されない |
| `failed` | approve 処理中にエラー発生 |

### candidate_key

候補の同一性は `candidate_key` で管理されます:

```
{pack_id}:{slug}:{handler_id}:{sha256}
```

sha256 を含めることで、handler.py の内容が変わると別の候補として扱われます。

### TOCTOU 対策

approve 時に handler.py の sha256 を再計算し、scan 時の値と比較します。不一致の場合は approve が失敗します。

### コピーと上書き

approve 時に `ecosystem/` 側の候補が `user_data/capabilities/handlers/<slug>/` にコピーされます。ecosystem 側は配布物として残り、移動されません。コピー先に既に handler が存在し、handler_id または sha256 が異なる場合はエラーになります（自動上書き禁止）。

---

## UDS ソケット権限

### 問題

strict モードでは、Pack 実行コンテナは `--user=65534:65534`（nobody）で動作します。UDS ソケットがデフォルトの `0660`（root:root）のままだと、コンテナからソケットに接続できません。

### 解決策

専用 GID を設定することで、`0660` を維持しつつ安全に接続を可能にします。

| 環境変数 | 説明 | デフォルト |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | Egress ソケットの GID | なし |
| `RUMI_CAPABILITY_SOCKET_GID` | Capability ソケットの GID | なし |
| `RUMI_EGRESS_SOCKET_MODE` | Egress ソケットのパーミッション | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | Capability ソケットのパーミッション | `0660` |

GID が設定されている場合、`docker run` 時に `--group-add=<GID>` が自動的に付与されます。

`RUMI_EGRESS_SOCKET_MODE=0666` / `RUMI_CAPABILITY_SOCKET_MODE=0666` で緩和可能ですが、任意のユーザーがソケットに接続可能になるため非推奨です。

---

## 階層権限

### 概要

`pack_id` を `parent__child` の形式にすることで、親子関係を持つ Pack を表現できます。子が許可されても親が許可されていないと実行が拒否されます。

親の config は子に上限（intersection）を設定します。下位だけ許可されても上位が許可していなければ動作しません。

---

## Secrets

API key などの秘密値を安全に管理します。

- `.env` は使用しない（事故率低減）
- `user_data/secrets/` に格納（1 key = 1 file、tombstone、journal）
- ログに秘密値を一切出さない（監査・診断とも）
- Pack に秘密ファイルを直接見せない
- 取得は capability（例: `secret.get`）経由
- API は list（mask 付き）/ set / delete のみ（再表示なし）

---

## 共有辞書（Shared Dict）

### 概要

任意の `namespace` / `token` を書き換えできる仕組みです。公式は namespace の意味を解釈しません（ecosystem が自由に決めます）。

### 安全機能

- **循環検出**: A→B→A のような循環は自動的に拒否
- **衝突検出**: 同じ token に異なる value を登録しようとすると拒否
- **ホップ上限**: デフォルト 10 ホップで解決を打ち切り
- **監査ログ**: 全ての操作を記録

### 永続化

`user_data/settings/shared_dict/` に `snapshot.json`（スナップショット）と `journal.jsonl`（ジャーナル）が保存されます。

---

## lib システム

### 概要

Pack の初期化・更新処理を管理します。常駐せず、必要時のみ実行されます。

### 実行タイミング

| 条件 | 実行されるファイル |
|------|-------------------|
| 初回導入（記録なし） | `lib/install.py` |
| ハッシュ変更 | `lib/update.py`（なければ `install.py`） |
| 変更なし | 実行しない |

### Docker 隔離

strict モードでは Docker コンテナ内で隔離実行されます。`--network=none`、`--cap-drop=ALL`、`--read-only`、`--memory=256m`。RW マウントは `user_data/packs/{pack_id}/`（コンテナ内: `/data`）のみに限定されます。

---

## pip 依存ライブラリ導入

### 概要

Pack が `requirements.lock` を同梱することで、PyPI パッケージへの依存を宣言できます。ユーザーが API で承認すると、ビルダー用 Docker コンテナで安全にダウンロード・インストールされます。ホスト Python 環境は汚れません。

### requirements.lock の規約

`NAME==VERSION` 行のみ許可です（コメント / 空行は可）。以下は禁止されます: `-e`（editable）、`git+` / `http://` / `https://`（URL/VCS 参照）、`file:` / `../` / `/`（ローカル参照）、`--` オプション行、`@` direct reference。

### 状態遷移

```
scan → pending → approve → installed
                → reject  → rejected (cooldown 1h)
                            → 3回 reject → blocked → unblock → pending
```

### セキュリティ

wheel-only がデフォルト（`--only-binary=:all:`）。sdist が必要な場合は approve 時に `allow_sdist: true` を明示します。ビルダーコンテナ（download）は `--network=bridge` + `--cap-drop=ALL`、ビルダーコンテナ（install）は `--network=none`（完全オフライン）で実行されます。実行コンテナからは site-packages が読み取り専用（`/pip-packages:ro`）でマウントされ、`PYTHONPATH` に追加されます。

### index_url の制約

`https` スキームのみ許可。hostname が localhost / 127.0.0.1 / ::1 / プライベート IP / link-local の場合は拒否されます。

---

## Pack Import / Apply

### Import

フォルダ / `.zip` / `.rumipack`（zip 互換）から Pack を staging に取り込みます。zip 構造は「トップ単一ディレクトリ必須」、zip slip / サイズ制限等の防御が適用されます。

### Apply

staging から ecosystem に適用します。バックアップが自動作成されます。apply 時に `pack_id` と `pack_identity`（`ecosystem.json` の `pack_identity` フィールド）の両方を比較し、既存 Pack と不一致の場合は拒否されます。

---

## Component 概念

### 概要

`backend_core/ecosystem/registry.py` が `pack_subdir/components/*/manifest.json` を読み込み、`ComponentInfo` を構築します。Component はライフサイクル管理（setup 等）のための単位です。

### python_file_call との関係

`python_file_call` は components を特別扱いして blocks を自動探索する機能を持ちません。`components/{component_id}/blocks/` にあるファイルを実行したい場合は、`file` フィールドに相対パスを明示します。

```yaml
type: python_file_call
owner_pack: my_pack
file: components/comp1/blocks/foo.py
```

---

## vocab / converter

> **注意**: この機能は互換性吸収のための高度な機能です。通常の Pack 開発では使用する必要はありません。

### vocab.txt（同義語グループ）

```
tool, function_calling, tools, tooluse
thinking_budget, reasoning_effort
```

同じ行に書かれた語は同義として扱われます。

### converters（変換器）

```python
# ecosystem/<pack_id>/backend/converters/tool_to_function_calling.py
def convert(data, context=None):
    """tool 形式 → function_calling 形式に変換"""
    return transformed_data
```

---

## 監査ログ

### 概要

全ての重要な操作が `user_data/audit/` に JSON Lines 形式で記録されます。

### カテゴリ

| カテゴリ | 内容 |
|----------|------|
| `flow_execution` | Flow 実行 |
| `modifier_application` | Modifier 適用 |
| `python_file_call` | ブロック実行 |
| `approval` | Pack 承認操作 |
| `permission` | 権限操作（network grant, capability grant 含む） |
| `network` | ネットワーク通信 |
| `security` | セキュリティイベント |
| `system` | システムイベント（lib, pip, pending export 等） |

### ファイル命名

`{category}_{YYYY-MM-DD}.jsonl`

ファイル名の日付はエントリの `ts`（タイムスタンプ）から決定されます。深夜跨ぎでもエントリの `ts` に対応するファイルに振り分けられます。`ts` が不正な場合は書き込み時点の日付にフォールバックします。

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

## Pending Export

### 概要

起動時に `user_data/pending/summary.json` が自動生成されます。外部ツールはこのファイルを読むだけで承認待ち状況を把握できます。公式はこのファイルの消費者を特別扱いしません（No Favoritism）。

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

各モジュールが import できない場合、そのセクションには `"error"` キーが含まれます（fail-soft）。

---

## Deprecated 機能

### ecosystem/flows/（local_pack）

`ecosystem/flows/` に直接配置された Flow/Modifier を仮想 Pack として扱う互換モードです。デフォルトでは無効（`RUMI_LOCAL_PACK_MODE=off`）です。`RUMI_LOCAL_PACK_MODE=require_approval` で有効化できますが、非推奨です。

廃止スケジュール: v2.0 で警告付き互換モード維持、v3.0 で削除予定。

移行先: Pack 化して `ecosystem/<pack_id>/backend/` に配置するか、`user_data/shared/flows/` に配置してください。

### addon_manager

`backend_core/ecosystem/addon_manager.py` に JSON Patch ベースの addon 機構が存在します。v1 で deprecated（新規利用停止、警告）、v2 で互換期間、v3 で削除予定です。

### flow/ ディレクトリ

旧 `flow/` ディレクトリは非推奨です。`flows/`、`user_data/shared/flows/`、または Pack 内 `flows/` に移行してください。
```