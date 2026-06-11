<!-- docs-i18n-links:start -->
[EN](../../../capability/dependency-resolution.md) | [JP](../../ja/capability/dependency-resolution.md) | [KR](./dependency-resolution.md) | [CN](../../zh-cn/capability/dependency-resolution.md)
<!-- docs-i18n-links:end -->

---

파일 이름: **`docs/capability/external-dependency.md`**

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
  "name": "내 코딩 어시스턴트",
  "버전": "1.0.0",

  "종속성": {
    "루미 쉘 기능": {
      "repo": "harupipipipi/rumi-shell-capability",
      "경로": ".",
      "버전": ">=1.0.0"
    },
    "루미-브라우저-도구": {
      "repo": "누군가/루미-브라우저-도구",
      "path": "팩/브라우저",
      "버전": "^2.0.0"
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
https://api.github.com/repos/{owner}/{repo}/zipball/{ref} 받기
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
사용자_데이터/팩/
├── my_coding_assistant/ # 사용자 소개 팩
│ ├── pack.json
│ ├── 도구/
│ └── 흐름/
│
├── rumi-shell-capability/ # 자동으로 종속성으로 획득
│ ├── pack.json
│ ├── 기능/
│ │ └── shell_exec/
│ │ ├── 능력.json
│ │ └── handler.py
│ └── .pack_meta.json
│
└── rumi-browser-tools/ # 자동으로 종속 항목으로 획득
    ├── 팩.json
    ├── 도구/
    └── .pack_meta.json
```

依存として取得された Pack も `user_data/packs/` に通常の Pack と同列に配置する。`.pack_meta.json` の有無で自動取得されたものかどうかを区別する。

---

## .pack_meta.json

自動取得された Pack に付与されるメタデータファイル。

```json
{
  "출처": {
    "repo": "harupipipipi/rumi-shell-capability",
    "경로": ".",
    "ref": "v1.2.0",
    "downloaded_at": "2026-02-14T10:00:00Z"
  },
  "hash": "sha256:abc123...",
  "installed_by": ["my_coding_assistant"],
  "승인": {
"승인됨": 사실,
    "approved_at": "2026-02-14T10:01:00Z",
    "approved_capability": ["shell_exec"]
  },
  "확인": {
    "확인됨": 사실,
    "verified_by": "루미 마켓플레이스",
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
팩 소개 요청
│
├─ 1. pack.json 미리 읽기 (zipball에서 pack.json만 추출)
│
├─ 2. 종속성 분석
│ ├─ 각 종속성을 재귀적으로 해결(종속성 추적도)
│ ├─ 이미 설치되어 있으며 버전 호환 가능 → 건너뛰기
│ ├─ 버전 충돌 → 오류 보고
│ └─ 순환 종속성 감지 → 오류 보고
│
├─ 3. 마켓플레이스 레지스트리 확인
│ ├─ 확인됨 → ✅
│ ├─ 테스트되지 않음 → ❓ + 경고
│ └─ 블랙리스트 → 🚫 차단
│
├─ 4. 사용자 승인
│ ├─ 의존성 목록, 검증 상태, 위험 수준 표시
│ ├─ 기능이 포함된 경우 코드 확인 옵션
│ └─ 승인 또는 취소
│
├─ 5. 다운로드/배포
│ ├─ zipball로 모든 종속 팩 가져오기
│ ├─ user_data/packs/에 위치
│ ├─ 해시 레코드
│ └─ .pack_meta.json 생성
│
└─ 6. 로드
    ├─ 기능 → 호스트 측에 등록됨
    ├─ 툴에 등록 → 로더
    └─ 흐름 → 가능
```

ネットワーク不可時は、既にインストール済みの依存はそのまま使用する。未インストールの依存がある場合はエラーとし、接続回復後に再試行を促す。

---

## Marketplace 検証

将来的に default が Marketplace レジストリを GitHub リポジトリとして公開する。

```
하루피피피피/rumi-marketplace
└── 레지스트리.json
```

```json
{
  "registry_version": "1.0.0",
  "updated_at": "2026-02-14",
  "팩": {
    "harupipipipi/rumi-shell-capability": {
      "status": "확인됨",
      "verified_versions": ["1.0.0", "1.1.0", "1.2.0"],
      "최신_검증": "1.2.0",
      "카테고리": ["능력", "쉘"],
      "risk_level": "높음",
      "verified_hashes": {
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
"my_coding_assistant" 팩을 소개합니다.

종속성:
  ✅ rumi-shell-capability v1.2.0 (루미 검증)
     ⚠️ 호스트 측 기능 추가: shell_exec(고위험)

  ✅ rumi-browser-tools v2.0.0 (루미 인증)
     ⚠️ 호스트 측 기능 추가: browser_control(높은 위험)

[모두 허용] [개별 확인] [취소]
```

未検証の場合:

```
"experimental_pack" 팩을 소개합니다.

종속성:
❓ 알 수 없음/맞춤형 v0.1.0(테스트되지 않음)
     ⚠️ 호스트 측 기능 추가: custom_thing(고위험)
     ⚠️ 루미 마켓플레이스에서 검증되지 않음

[코드 확인] [신뢰 및 허용] [취소]
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
생태계/기본/백엔드/블록/팩/
├── downloader.py # GitHub API zipball 다운로드
├── resolver.py # 종속성 해결/semver 일치/주기 감지
├── installer.py # 배치, 해시 레코드, .pack_meta.json 생성
├── verifier.py # 마켓플레이스 레지스트리 확인
└── updater.py # 업데이트 확인
```
```
