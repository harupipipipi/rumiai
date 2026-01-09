```markdown
# Ecosystem Specification v1.0

## 概要

Ecosystemは、AIチャットアプリケーションの機能をモジュール化し、
拡張可能にするためのプラグインアーキテクチャです。

本仕様書は、Pack、Component、Addonの構造と相互作用を定義します。

---

## 用語定義

### Pack（パック）

完全な機能セットを含む配布単位。`ecosystem/[pack_id]/` に展開される。

| 属性 | 説明 |
|------|------|
| pack_id | 短縮識別子（ディレクトリ名として使用） |
| pack_identity | グローバル一意識別子（UUID生成の種） |
| pack_uuid | pack_identityから決定論的に生成されるUUID v5 |
| version | セマンティックバージョニング（例: 1.0.0） |
| vocabulary | このPackで使用可能なComponent typeの定義 |

**例:**
```json
{
  "pack_id": "default",
  "pack_identity": "github:haru/default-pack",
  "version": "1.0.0",
  "vocabulary": {
    "types": ["chats", "tool_pack", "prompt_pack"]
  }
}
```

### Component（コンポーネント）

Pack内の個別機能モジュール。`components/[component_dir]/` に配置される。

| 属性 | 説明 |
|------|------|
| type | コンポーネントの種類（vocabularyで定義） |
| id | コンポーネントの識別子（Pack内で一意） |
| component_uuid | pack_uuid + type + id から生成されるUUID v5 |
| version | セマンティックバージョニング |
| connectivity | 他コンポーネントとの接続性定義 |
| addon_policy | アドオンによる変更許可ポリシー |

**例:**
```json
{
  "type": "chats",
  "id": "chats_v1",
  "version": "1.0.0",
  "connectivity": {
    "accepts": ["tool_pack", "prompt_pack"],
    "provides": ["chat_history", "agent_runtime"]
  }
}
```

### Addon（アドオン）

既存Componentを拡張するJSON Patchベースの軽量拡張。

| 属性 | 説明 |
|------|------|
| addon_id | アドオンの識別子 |
| version | セマンティックバージョニング |
| priority | 適用順序（大きいほど後に適用、デフォルト: 100） |
| targets | パッチ適用対象のリスト |
| enabled | 有効/無効フラグ |

**例:**
```json
{
  "addon_id": "add_benchmark",
  "version": "1.0.0",
  "priority": 100,
  "targets": [
    {
      "pack_identity": "github:haru/default-pack",
      "component": {"type": "ai_client_provider", "id": "ai_client_v1"},
      "apply": [
        {
          "kind": "manifest_json_patch",
          "patch": [
            {"op": "add", "path": "/extensions/benchmark", "value": true}
          ]
        }
      ]
    }
  ]
}
```

---

## UUID生成規則

すべてのUUIDはバージョン5（SHA-1ベースの名前空間UUID）で生成される。
これにより、同じ入力に対して常に同じUUIDが生成される（決定論的）。

### 名前空間UUID

プロジェクト固有の名前空間UUIDを使用：

```
PACK_NAMESPACE_UUID = a3e9f8c2-7b4d-5e1a-9c6f-2d8b4a7e3f1c
```

### 生成式

```python
# Pack UUID
pack_uuid = uuid5(PACK_NAMESPACE_UUID, pack_identity)

# Component UUID
component_uuid = uuid5(pack_uuid, f"component:{type}:{id}")

# Addon UUID
addon_uuid = uuid5(pack_uuid, f"addon:{addon_id}")
```

### 例

```python
# pack_identity = "github:haru/default-pack"
pack_uuid = uuid5(PACK_NAMESPACE_UUID, "github:haru/default-pack")
# -> 特定の固定UUID

# type = "chats", id = "chats_v1"
component_uuid = uuid5(pack_uuid, "component:chats:chats_v1")
# -> 特定の固定UUID
```

**重要:** pack_identityが同じであれば、どの環境でも同じUUIDが生成される。
これにより、外部配布されたアドオンが正しく動作することが保証される。

---

## ディレクトリ構造

### 完全な構造

```
project_root/
├── backend_core/
│   └── ecosystem/
│       ├── spec/
│       │   ├── ecosystem_spec.md
│       │   └── schema/
│       │       ├── ecosystem.schema.json
│       │       ├── component_manifest.schema.json
│       │       └── addon.schema.json
│       ├── uuid_namespace.py
│       ├── uuid_utils.py
│       ├── mounts.py
│       ├── registry.py
│       ├── addon_manager.py
│       ├── active_ecosystem.py
│       ├── initializer.py
│       ├── compat.py
│       └── json_patch.py
│
├── ecosystem/
│   └── [pack_id]/
│       ├── backend/
│       │   ├── ecosystem.json
│       │   ├── components/
│       │   │   └── [component_dir]/
│       │   │       ├── manifest.json
│       │   │       └── ...（実装ファイル）
│       │   └── addons/
│       │       └── *.addon.json
│       └── frontend/
│           ├── manifest.json
│           └── ...（フロントエンド実装）
│
├── user_data/
│   ├── mounts.json
│   ├── active_ecosystem.json
│   ├── chats/
│   ├── settings/
│   ├── cache/
│   └── shared/
│
└── ecosystem_packs/
    └── *.ecopack（将来：ZIP配布形式）
```

### Pack構造

```
ecosystem/[pack_id]/
├── backend/
│   ├── ecosystem.json          # Pack定義（必須）
│   ├── components/
│   │   ├── chats/
│   │   │   ├── manifest.json   # Component定義（必須）
│   │   │   └── ...
│   │   ├── tool/
│   │   │   ├── manifest.json
│   │   │   └── tool/           # 実際のツール実装
│   │   ├── prompt/
│   │   │   ├── manifest.json
│   │   │   └── prompt/
│   │   ├── supporter/
│   │   │   ├── manifest.json
│   │   │   └── supporter/
│   │   └── ai_client/
│   │       ├── manifest.json
│   │       └── ai_client/
│   └── addons/
│       └── *.addon.json
│
└── frontend/
    ├── manifest.json
    ├── shell/
    ├── panels/
    └── buttons/
```

---

## Component Types（標準vocabulary）

Default Packで定義される標準的なComponent type：

| Type | 説明 | 主な機能 |
|------|------|----------|
| chats | チャット履歴管理 | 履歴保存、標準形式変換、UI履歴分離 |
| tool_pack | ツール（Function Calling） | 動的読み込み、仮想環境、UI対応 |
| prompt_pack | プロンプトテンプレート | 動的読み込み、設定スキーマ |
| supporter_pack | サポーター（pre/post処理） | 入力修正、コンテキスト追加 |
| ai_client_provider | AIプロバイダークライアント | 複数プロバイダー統合 |
| frontend_pack | フロントエンドUI | シェル、パネル、ボタン |
| ui_panel_pack | UIパネル | 左ペイン、中央、設定 |
| ui_button_pack | UIボタン | プロンプト切替、モデル切替 |

---

## Connectivity（接続性）

Componentは他のComponentと接続できる。接続性は`connectivity`フィールドで定義。

### フィールド

| フィールド | 説明 |
|-----------|------|
| accepts | 受け入れ可能なComponent type |
| provides | 提供するインターフェース |
| requires | 必須の依存Component type |

### 例

```json
{
  "connectivity": {
    "accepts": ["tool_pack", "prompt_pack", "supporter_pack"],
    "provides": ["chat_history", "agent_runtime"],
    "requires": []
  }
}
```

### 接続性の解決

1. `requires`に指定されたtypeのComponentが存在しない場合、警告を出力
2. `accepts`に含まれるtypeのComponentのみが接続可能
3. `provides`は他のComponentから参照される際に使用

---

## Storage（ストレージ）

### マウントポイント

データ保存先はマウントポイントで抽象化される。

| マウントポイント | デフォルトパス | 説明 |
|-----------------|---------------|------|
| data.chats | ./user_data/chats | チャット履歴 |
| data.settings | ./user_data/settings | ユーザー設定 |
| data.cache | ./user_data/cache | キャッシュデータ |
| data.shared | ./user_data/shared | 共有ストレージ |

### mounts.json

```json
{
  "version": "1.0",
  "mounts": {
    "data.chats": "./user_data/chats",
    "data.settings": "./user_data/settings",
    "data.cache": "./user_data/cache",
    "data.shared": "./user_data/shared"
  }
}
```

ユーザーは任意のパスに変更可能：

```json
{
  "mounts": {
    "data.chats": "/mnt/nas/chats",
    "data.settings": "./user_data/settings",
    "data.cache": "/tmp/cache",
    "data.shared": "./user_data/shared"
  }
}
```

### Componentでのストレージ使用

```json
{
  "storage": {
    "uses_mounts": ["data.chats"],
    "layout": "component_defined"
  }
}
```

| layout値 | 説明 |
|----------|------|
| component_defined | Componentがレイアウトを定義 |
| pack_defined | Packがレイアウトを定義 |
| shared | 複数Componentで共有 |

---

## Addon Policy（アドオンポリシー）

Componentはaddon_policyでAddonによる変更を制御する。

### フィールド

| フィールド | 説明 |
|-----------|------|
| allowed_manifest_paths | 変更可能なマニフェストのJSON Pointerパス |
| editable_files | 変更可能なファイルの定義 |
| deny_all | trueの場合、すべての変更を拒否 |

### 例

```json
{
  "addon_policy": {
    "allowed_manifest_paths": ["/connectivity/accepts", "/extensions"],
    "editable_files": [
      {
        "path_glob": "ai_profile/*.json",
        "allowed_json_pointer_prefixes": ["/benchmarks", "/metadata"]
      }
    ],
    "deny_all": false
  }
}
```

### パス制限

アドオンは以下のパスのみ変更可能（上記例の場合）：

- `/connectivity/accepts` - 接続性の拡張
- `/extensions` - 拡張データ領域
- `ai_profile/*.json`ファイル内の`/benchmarks`と`/metadata`

---

## JSON Patch制限

セキュリティ上の理由から、RFC 6902の一部操作のみ許可。

### 許可される操作

| 操作 | 説明 | 例 |
|------|------|-----|
| add | 値の追加 | `{"op": "add", "path": "/foo", "value": "bar"}` |
| remove | 値の削除 | `{"op": "remove", "path": "/foo"}` |
| replace | 値の置換 | `{"op": "replace", "path": "/foo", "value": "baz"}` |
| test | 値のテスト | `{"op": "test", "path": "/foo", "value": "bar"}` |

### 禁止される操作

| 操作 | 理由 |
|------|------|
| move | 予期しない構造変更の防止 |
| copy | 予期しないデータ複製の防止 |

---

## Active Ecosystem（アクティブエコシステム）

現在使用中のPackとComponentオーバーライドを管理。

### active_ecosystem.json

```json
{
  "active_pack_identity": "github:haru/default-pack",
  "overrides": {
    "chats": "chats_v1",
    "tool_pack": "tool_v1",
    "prompt_pack": "prompt_v1",
    "supporter_pack": "supporter_v1",
    "ai_client_provider": "ai_client_v1"
  },
  "disabled_components": [],
  "disabled_addons": [],
  "metadata": {}
}
```

### オーバーライド

各Component typeに対して使用するComponent idを指定。

```json
{
  "overrides": {
    "chats": "chats_v2",
    "tool_pack": "tool_v1"
  }
}
```

上記の場合：
- chatsはchats_v2を使用
- tool_packはtool_v1を使用

### Component/Addonの無効化

```json
{
  "disabled_components": ["default:chats:chats_v1"],
  "disabled_addons": ["default:benchmark_addon"]
}
```

---

## 初期化フロー

アプリケーション起動時の初期化順序：

1. **ディレクトリ作成**
   - user_data/配下のディレクトリを作成

2. **マウント初期化**
   - mounts.jsonを読み込み（なければ作成）
   - マウントポイントを解決

3. **レジストリ初期化**
   - ecosystem/配下のPackを走査
   - ecosystem.jsonを読み込み、検証
   - Componentを読み込み、検証
   - Addonを読み込み、検証

4. **アクティブエコシステム初期化**
   - active_ecosystem.jsonを読み込み（なければ作成）
   - オーバーライドを適用

5. **既存マネージャー初期化**
   - エコシステム経由でパス解決
   - 各マネージャーを初期化

---

## 後方互換性

エコシステムは既存のコードと後方互換性を維持。

### 互換性レイヤー（compat.py）

```python
from backend_core.ecosystem.compat import get_chats_dir

# エコシステムが初期化済みならマウント経由
# そうでなければ従来のパスを返す
chats_dir = get_chats_dir()
```

### 利用可能な関数

| 関数 | 説明 |
|------|------|
| get_chats_dir() | チャットディレクトリ |
| get_settings_dir() | 設定ディレクトリ |
| get_cache_dir() | キャッシュディレクトリ |
| get_shared_dir() | 共有ディレクトリ |
| get_tools_dir() | ツールディレクトリ |
| get_prompts_dir() | プロンプトディレクトリ |
| get_supporters_dir() | サポーターディレクトリ |
| get_ai_clients_dir() | AIクライアントディレクトリ |

---

## スキーマ検証

すべての定義ファイルはJSON Schemaで検証される。

### スキーマファイル

| ファイル | 対象 |
|----------|------|
| ecosystem.schema.json | ecosystem.json |
| component_manifest.schema.json | manifest.json |
| addon.schema.json | *.addon.json |

### 検証API

```python
from backend_core.ecosystem.spec import (
    validate_ecosystem,
    validate_component_manifest,
    validate_addon
)

# 検証（エラー時は例外）
validate_ecosystem(data)

# 検証（エラーをリストで返す）
errors = validate_ecosystem(data, raise_on_error=False)
```

---

## エラーハンドリング

### SchemaValidationError

スキーマ検証エラー：

```python
try:
    validate_ecosystem(data)
except SchemaValidationError as e:
    print(f"検証エラー: {e}")
    for error in e.errors:
        print(f"  - {error}")
```

### JsonPatchError

パッチ適用エラー：

```python
try:
    apply_patch(doc, patch)
except JsonPatchError as e:
    print(f"パッチエラー: {e}")
```

### JsonPatchForbiddenError

禁止操作エラー（move/copy）：

```python
try:
    apply_patch(doc, [{"op": "move", "from": "/a", "path": "/b"}])
except JsonPatchForbiddenError as e:
    print(f"禁止操作: {e}")
```

---

## 将来の拡張

### .ecopack形式

Pack全体をZIPファイルとして配布：

```
my_pack.ecopack
├── backend/
│   ├── ecosystem.json
│   ├── components/
│   └── addons/
└── frontend/
```

### カスタムvocabulary

Pack固有のComponent typeを定義：

```json
{
  "vocabulary": {
    "types": ["chats", "tool_pack", "custom_type"],
    "custom_types": {
      "custom_type": {
        "description": "カスタムコンポーネント",
        "singleton": true
      }
    }
  }
}
```

### Pack依存関係

他のPackへの依存：

```json
{
  "dependencies": {
    "github:haru/base-pack": ">=1.0.0"
  }
}
```

---

## 参考リンク

- [RFC 6902 - JSON Patch](https://tools.ietf.org/html/rfc6902)
- [RFC 6901 - JSON Pointer](https://tools.ietf.org/html/rfc6901)
- [JSON Schema Draft-07](https://json-schema.org/draft-07/json-schema-release-notes.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [UUID Version 5](https://tools.ietf.org/html/rfc4122#section-4.3)
```