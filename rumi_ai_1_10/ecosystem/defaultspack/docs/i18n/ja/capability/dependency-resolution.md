<!-- docs-i18n-links:start -->
[EN](../../../capability/dependency-resolution.md) | [JP](./dependency-resolution.md) | [KR](../../ko/capability/dependency-resolution.md) | [CN](../../zh-cn/capability/dependency-resolution.md)
<!-- docs-i18n-links:end -->

---

ファイル名：**`docs/capability/external-dependency.md`**

```markdown
# External Dependency Resolution

Pack が必要とする capability・tool・flow を自身に同梱せず、外部の GitHub リポジトリ URL を指定するだけで自動取得する仕組み。

---

## 背景

Pack が特殊な capability（例: GPU 計算、シェル永続セッション、デバイス制御）を必要とする場合、従来は Pack 内の `capability/` フォルダに handler を同梱する必要があった。この方式では同じ capability を複数の Pack が重複して梱包する問題が生じる。

External Dependency Resolution により、Pack は `pack.json` に GitHub リポジトリの URL を記述するだけでよい。必要なリソースは導入時に自動的にダウンロードされ、共有リソースとして配置される。

---

## 原則

外部依存は全て **Pack** として配布する。capability のみ、tool のみ、flow のみであっても、それぞれ独立した Pack として公開する。依存管理を 1 種類に統一するためである。

---

## pack.json の dependencies

```json
{
  "pack_id": "my_coding_assistant",
  "name": "私のコーディングアシスタント",
  "バージョン": "1.0.0",

  "依存関係": {
    "rumi-shell-capability": {
      "repo": "ハルピピピピ/rumi-shell-capability",
      "パス": ".",
      "バージョン": ">=1.0.0"
    },
    "rumi-ブラウザ-ツール": {
      "repo": "someone/rumi-browser-tools",
      "パス": "パック/ブラウザ",
      "バージョン": "^2.0.0"
    }
  }
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `repo` | ○ | GitHub リポジトリ（`owner/repo` 形式） |
| `path` | ○ | リポジトリ内の Pack ルートパス。ルート直下なら `"."` |
| `version` | ○ | semver 範囲指定（`>=1.0.0`, `^2.0.0`, `1.2.3` 等） |

---

## ダウンロード方式

git コマンドは使用しない。GitHub REST API の zipball エンドポイントを使用する。

```
https://api.github.com/repos/{owner}/{repo}/zipball/{ref}を取得
```

手順:

1. `GET /repos/{owner}/{repo}/tags` でタグ一覧を取得
2. `version` の semver 範囲に合致する最新タグを選択
3. そのタグの zipball をダウンロード
4. zip を解凍し、`path` で指定されたディレクトリのみ抽出
5. `user_data/packs/{dependency_name}/` に配置

private リポジトリの場合は `Authorization: token {GITHUB_TOKEN}` ヘッダを付与する。トークンは環境変数 `GITHUB_TOKEN` で指定する。

---

## 配置先

```
ユーザーデータ/パック/
§── my_coding_assistant/ # ユーザー導入パック
│ §──pack.json
│ §── ツール/
│ └── 流れる/
│
§── rumi-shell-capability/ # 依存関係として自動取得
│ §──pack.json
│ §── 能力/
│ │ └──shell_exec/
│ │ §──capability.json
│ │ └─ handler.py
│ ━─ .pack_meta.json
│
└── rumi-browser-tools/ # 依存関係として自動取得
    §──pack.json
    §── ツール/
    ━── .pack_meta.json
```

依存として取得された Pack も `user_data/packs/` に通常の Pack と同列に配置する。`.pack_meta.json` の有無で自動取得されたものかどうかを区別する。

---

## .pack_meta.json

自動取得された Pack に付与されるメタデータファイル。

```json
{
  「ソース」: {
    "repo": "ハルピピピピ/rumi-shell-capability",
    "パス": ".",
    "ref": "v1.2.0",
    "downloaded_at": "2026-02-14T10:00:00Z"
  },
  "ハッシュ": "sha256:abc123...",
  "installed_by": ["my_coding_assistant"],
  「承認」: {
「承認済み」: true、
    "approved_at": "2026-02-14T10:01:00Z",
    "approved_capabilities": ["shell_exec"]
  },
  「検証」: {
    「検証済み」: true、
    "verified_by": "rumi マーケットプレイス",
    "checked_at": "2026-02-14T10:00:30Z"
  }
}
```

| フィールド | 説明 |
|-----------|------|
| `source` | ダウンロード元の情報 |
| `hash` | 配置されたファイル群の SHA-256 ハッシュ |
| `installed_by` | この Pack を依存として要求した Pack のリスト |
| `approval` | ユーザーの承認状態 |
| `verification` | Marketplace での検証状態 |

---

## 解決フロー

```
パック導入依頼
│
§─ 1.pack.jsonを先読みする（zipballからpack.jsonのみを抽出）
│
§─ 2. 依存関係を分析する
│ §─ 各依存関係を再帰的に解決します (依存関係のトレースも行います)
│ §─ すでにインストールされており、バージョンに互換性がある → スキップ
│ §─ バージョン競合 → エラー報告
│ └─ 循環依存関係の検出 → エラー報告
│
§─ 3. マーケットプレイスのレジストリの確認
│ §─ 確認済み → ✅
│ §─ 未テスト → ❓ + 警告
│ └─ ブラックリスト → 🚫 ブロック
│
§─ 4. ユーザーの承認
│ §─ 依存関係一覧、検証状況、リスクレベルを表示
│ §─ 機能が含まれる場合のコード確認オプション
│ └─ 承認またはキャンセル
│
§─ 5. ダウンロード・導入
│ §─ zipball で依存パックをすべて入手する
│ §─ user_data/packs/ に配置
│ §─ ハッシュレコード
│ └─ .pack_meta.json の生成
│
━─ 6. 負荷
    §─ ケイパビリティ → ホスト側に登録
    §─ ツール→ローダーに登録
    └─ 流れ → 利用可能
```

ネットワーク不可時は、既にインストール済みの依存はそのまま使用する。未インストールの依存がある場合はエラーとし、接続回復後に再試行を促す。

---

## Marketplace 検証

将来的に default が Marketplace レジストリを GitHub リポジトリとして公開する。

```
はるぴぴぴぴ/るみマーケットプレイス
└── registry.json
```

```json
{
  "レジストリのバージョン": "1.0.0",
  "更新日": "2026-02-14",
  「パック」: {
    "ハルピピピピ/rumi-shell-capability": {
      "ステータス": "検証済み",
      "verified_versions": ["1.0.0", "1.1.0", "1.2.0"],
      "最新_検証済み": "1.2.0",
      "カテゴリ": ["機能", "シェル"],
      "リスクレベル": "高",
      "検証済みハッシュ": {
        "1.2.0": "sha256:abc123..."
      }
    }
  }
}
```

| status | 表示 | 意味 |
|--------|------|------|
| `verified` | ✅ | Rumi チームがコードレビュー済み |
| `unverified` | ❓ | 未レビュー（警告表示） |
| `blocked` | 🚫 | 悪意あり・危険と判定（インストール不可） |

Pack 導入時にこのレジストリを取得（24 時間キャッシュ）し、依存先の検証状態を照合する。レジストリに存在しないリポジトリは `unverified` として扱う。

---

## 承認画面

検証済みの場合:

```
パック「my_coding_assistant」を導入します。

依存関係:
  ✅ rumi-shell-capability v1.2.0 (Rumi 検証済み)
     ⚠️ ホスト側機能の追加:shell_exec (高リスク)

  ✅ rumi-browser-tools v2.0.0 (Rumi 検証済み)
     ⚠️ ホスト側の機能が追加されました: browser_control (高リスク)

[すべて許可] [個別に確認] [キャンセル]
```

未検証の場合:

```
パック「experimental_pack」を紹介します。

依存関係:
❓ 不明/カスタムのもの v0.1.0 (未テスト)
     ⚠️ 追加されたホスト側機能:custom_thing (高リスク)
     ⚠️ Rumi マーケットプレイスでは検証されていません

[コードを確認] [信頼して許可] [キャンセル]
```

---

## Capability の探索優先順位

ツールが `capabilities_required` で capability を要求したとき、以下の順序で探索する。

1. システム組み込み（`ecosystem/default/backend/capabilities/`）
2. Pack 提供（`user_data/packs/*/capabilities/`）
3. ツール同梱（`user_data/shared/tools/*/capability/`）
4. 未発見 → 依存元 Pack の `capability_sources` から自動取得を試行

---

## アップデート

`default.pack_update` Flow がインストール済みの依存 Pack のアップデートを確認する。

1. `.pack_meta.json` の `source.repo` と `source.ref` を読む
2. GitHub API でタグ一覧を取得し、新バージョンがあるか確認
3. 新バージョンがあれば Marketplace レジストリで検証状態を確認
4. ユーザーに通知し、承認後にダウンロード・置換
5. capability の handler.py が変更された場合は再承認を要求

---

## 削除

依存 Pack は `installed_by` で参照元を追跡する。

1. 参照元 Pack が削除されたら `installed_by` から除去
2. `installed_by` が空になった依存 Pack はユーザーに削除を提案
3. 他の Pack がまだ依存している場合は保持

---

## 関連ファイル

```
エコシステム/デフォルト/バックエンド/ブロック/パック/
§── downloader.py # GitHub API zipball ダウンロード
§──solver.py # 依存関係解決/サーバマッチング/サイクル検出
§── installer.py # 配置、ハッシュレコード、.pack_meta.json 生成
§── verifier.py # マーケットプレイスのレジストリ検証
━── updater.py # アップデートチェック
```
```
