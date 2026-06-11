<!-- docs-i18n-links:start -->
[EN](../../../capability/dependency-resolution.md) | [JP](../../ja/capability/dependency-resolution.md) | [KR](../../ko/capability/dependency-resolution.md) | [CN](./dependency-resolution.md)
<!-- docs-i18n-links:end -->

---

文件名称： **`docs/capability/external-dependency.md`**

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
  "pack_id": "我的编码助手",
  "name": "我的编码助手",
  “版本”：“1.0.0”，

  “依赖项”：{
    “rumi-shell-能力”：{
      "repo": "harupipipipi/rumi-shell-capability",
      “路径”：“。”，
      “版本”：">=1.0.0"
    },
    “鲁米浏览器工具”：{
      “repo”：“某人/鲁米浏览器工具”，
      “路径”：“包/浏览器”，
      “版本”：“^2.0.0”
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
获取https://api.github.com/repos/{owner}/{repo}/zipball/{ref}
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
用户数据/包/
├── my_coding_assistant/ # 用户引入的包
│ ├── pack.json
│ ├── 工具/
│ └── 流动/
│
├── rumi-shell-capability/ # 自动获取为依赖
│ ├── pack.json
│ ├── 能力/
│ │ └── shell_exec/
│ │ ├──capability.json
│ │ └── handler.py
│ └── .pack_meta.json
│
└── rumi-browser-tools/ # 自动获取为依赖
    ├── pack.json
    ├── 工具/
    └── .pack_meta.json
```

依存として取得された Pack も `user_data/packs/` に通常の Pack と同列に配置する。`.pack_meta.json` の有無で自動取得されたものかどうかを区別する。

---

## .pack_meta.json

自動取得された Pack に付与されるメタデータファイル。

```json
{
  “来源”：{
    "repo": "harupipipipi/rumi-shell-capability",
    “路径”：“。”，
    “参考”：“v1.2.0”，
    “downloaded_at”：“2026-02-14T10:00:00Z”
  },
  "哈希": "sha256:abc123...",
  “installed_by”：[“my_coding_assistant”]，
  “批准”：{
“批准”：真实，
    “approved_at”：“2026-02-14T10:01:00Z”，
    “approved_capability”：[“shell_exec”]
  },
  “验证”：{
    “已验证”：真实，
    "verified_by": "鲁米市场",
    “checked_at”：“2026-02-14T10:00:30Z”
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
包介绍请求
│
├─ 1. 预读 pack.json （仅从 zipball 中提取 pack.json）
│
├─ 2. 分析依赖关系
│ ├─ 递归地解决每个依赖关系（也跟踪依赖关系）
│ ├─ 已安装且版本兼容 → 跳过
│ ├─ 版本冲突 → 错误报告
│ └─ 检测循环依赖 → 错误报告
│
├─ 3. 市场注册验证
│ ├─ 已验证 → ✅
│ ├─ 未测试 → ❓ + 警告
│ └─ 黑名单 → 🚫 封锁
│
├─ 4.用户认可
│ ├─ 显示依赖列表、验证状态和风险级别
│ ├─ 代码确认选项（如果包含功能）
│ └─ 批准或取消
│
├─ 5.下载/部署
│ ├─ 使用 zipball 获取所有依赖包
│ ├─ 放置在user_data/packs/中
│ ├─ 哈希记录
│ └─ .pack_meta.json 生成
│
└─ 6. 负载
    ├─ 能力 → 注册在主机端
    ├─ 注册到工具→加载器
    └─ 流量→可用
```

ネットワーク不可時は、既にインストール済みの依存はそのまま使用する。未インストールの依存がある場合はエラーとし、接続回復後に再試行を促す。

---

## Marketplace 検証

将来的に default が Marketplace レジストリを GitHub リポジトリとして公開する。

```
harupipipipi/rumi-marketplace
└── 注册表.json
```

```json
{
  “registry_version”：“1.0.0”，
  “更新时间”：“2026-02-14”，
  “包”：{
    “harupipipipi/rumi-shell-capability”：{
      “状态”：“已验证”，
      “verified_versions”：[“1.0.0”，“1.1.0”，“1.2.0”]，
      “latest_verified”：“1.2.0”，
      “类别”：[“能力”，“外壳”]，
      "risk_level": "高",
      “verified_hashes”：{
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
引入包“my_coding_assistant”。

依赖项：
  ✅rumi-shell-capability v1.2.0（Rumi 验证）
     ⚠️ 添加主机端功能：shell_exec（高风险）

  ✅rumi-browser-tools v2.0.0（Rumi 验证）
     ⚠️添加主机端功能：browser_control（高风险）

[允许全部] [单独确认] [取消]
```

未検証の場合:

```
引入包“experimental_pack”。

依赖项：
❓ 未知/自定义事物 v0.1.0（未经测试）
     ⚠️添加了主机端功能：custom_thing（高风险）
     ⚠️ 未在 Rumi Marketplace 上验证

[验证码] [信任并允许] [取消]
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
生态系统/默认/后端/块/包/
├── downloader.py # GitHub API zipball 下载
├──resolver.py # 依赖解析/semver匹配/循环检测
├── installer.py # 放置、hash记录、.pack_meta.json生成
├── verifier.py # 市场注册验证
└── updater.py # 更新检查
```
```
