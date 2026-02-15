
```markdown
# Rumi AI OS — Roadmap

最終更新: 2026-02-15

設計思想・過去案を含む完全版ロードマップです。設計の全体像は [architecture.md](architecture.md) を参照してください。

---

## 0. 北極星（Vision）

- **基盤のない基盤**: 公式はドメイン概念（チャット / ツール / プロンプト / UI 等）を一切持たず、「実行・承認・隔離・監査・権限」という OS 的な仕組みのみを提供する。
- ecosystem は第三者が作る前提（悪意前提）で、**承認必須**・**Docker 隔離（strict 推奨）**・**Fail-soft**・**監査ログ**が中核。

---

## 1. 設計原則（Principles）

### 1.1 No Favoritism（贔屓なし）

公式コアは「API key」「tool」「chat」等の意味を解釈しない。公式が提供するのは汎用機構: Flow 実行、承認ゲート（hash 検証）、隔離実行（Docker / UDS）、Trust + Grant（capability）、監査ログ。

### 1.2 悪意前提（Threat model）

Pack 作者に悪意がある可能性を常に想定。Pack 実行は原則 Docker `--network=none`。外部通信やホスト特権は capability（Trust + Grant）に寄せる。

### 1.3 Fail-soft

一部が壊れても OS 全体は止めない。診断（Diagnostics）と監査（Audit）で可視化し継続する。

### 1.4 ホスト権限の単一入口

ホストで危険なこと（外部通信、ファイルアクセス、更新適用、ターミナル等）は、Pack から直接やらせず capability で仲介し、許可がない限り動かない。

---

## 2. コンセプト整理

### 2.1 Pack / principal / capability

- **principal**: 権限判断の主体。v1 は運用を簡単にするため pack_id 単位を基本とする。
- capability は `permission_id` で要求し、Trust（sha256）と Grant（principal × permission）で許可。

### 2.2 pack in pack（階層化）

`parent__child` のように階層を pack_id で表現し、上位が下位を制限する（上位が許可しないと下位は動かない）を実現。

目的: bundle 配布、運用の一括管理、権限の親子制約。

> 注意: ディレクトリ階層 ≠ セキュリティ境界。強制力は「ホスト側のゲート（capability / 実行器）」で担保する。

### 2.3 Store / Unit（共有領域と再利用単位）

ユーザー / ecosystem が任意に作れる共有領域（Store）と、その中の再利用単位（Unit）は汎用基盤として価値がある。Unit は `data / python / binary` 等を取りうる。実行系 Unit は Pack 承認 + Unit Trust（sha256 allowlist）を基本とする。

実行モードは権限に応じて選べる（矯正しない）: pack container、host capability、dedicated sandbox（将来）。

---

## 3. 公式コアの土台一覧

### 3.1 依存（pip）導入

Pack が `requirements.lock` を同梱。wheel-only がデフォルト（sdist は例外承認）。builder コンテナで download → install（install は offline）。実行時は site-packages を RO マウント + PYTHONPATH で見せる（コンテナは network=none 維持）。

### 3.2 capability handler 候補導入（承認ワークフロー）

ecosystem に候補を同梱。scan → pending → approve/reject → blocked（3 回 reject）。approve で Trust 登録 + コピー + registry reload。cooldown 1h、blocked は unblock まで通知しない。

### 3.3 Secrets（API key の保存）

`.env` を避ける（事故率低減）。`user_data/secrets/` に格納、ログに値を出さない。Pack に秘密ファイルを見せない。取得は capability（例: `secrets.get`）経由が基本。

### 3.4 Pack 配布形式

入力 3 形態: フォルダ / `.zip` / `.rumipack`（zip 互換）。推奨: トップに pack root 1 つ。将来的に multi-pack archive（pack in pack）にも拡張可能。

### 3.5 更新適用（auto update 禁止）

公式はオートアップデートしない。取得 → staging → 適用の分離。apply は危険なので capability（`pack.update`）へ寄せたい（v1 は運用 API でも可）。単一 pack_id の適用から開始。

### 3.6 実行（Python / バイナリ）

Pack の通常実行は Docker 隔離で成立するので、ホストに Python が無くても（Docker さえあれば）OK。ホストで動くもの（capability handler 等）は、将来的に Rumi 本体を単一実行ファイル化（Python 同梱）するか handler を OS 別バイナリにするかのどちらかが必要になる（両対応も可）。

---

## 4. 実装ステータス

このロードマップでは、各項目を以下の状態で管理します。

| 記号 | 意味 |
|------|------|
| ✅ | Done（実装済み・運用可能） |
| 🟡 | Partial（基盤はある / 改善が必要） |
| 🧩 | Planned（設計済み・未実装） |
| 🧪 | Experimental（実験・後で仕様固め） |

> 注: 実リポジトリ状態の自動検証はここでは行っていません。必要なら後でチェックリスト化します。

---

## 5. v1（現在〜直近）: 運用できる OS の完成（公式コア）

### 5.1 セキュア実行・承認・監査（基盤）

- ✅ Pack 承認（hash 検証、modified 検出、blocked）
- ✅ 監査ログ（カテゴリ別 jsonl）
- ✅ Docker 隔離（strict 推奨、permissive は警告）

### 5.2 pip 依存導入（requirements.lock）

- ✅ scan → approve → builder で download/install
- ✅ site-packages RO マウント + PYTHONPATH
- 🟡 sdist 例外（allow_sdist）運用の監査明確化（継続改善）

### 5.3 capability（Trust + Grant + 候補導入）

- ✅ 候補導入フロー（pending / approve / reject / blocked / cooldown）
- ✅ Trust store / Grant manager / Executor / Proxy（UDS）
- ✅ principal 単位の grant 管理（HMAC 署名）
- 🟡 マルチプラットフォームバイナリ（trust の拡張）は中期

### 5.4 Secrets（平文で OK、事故率低減）

- ✅ user_data/secrets（1 key = 1 file、tombstone、journal）
- ✅ API は list(mask) / set / delete のみ（再表示なし）
- ✅ ログに値を出さない（監査・診断とも）
- ✅ `secrets.get` の rate_limit=60（事故防止）
- ✅ get_secret() ヘルパー関数（rumi_capability.py）— Wave 2 #32
- 🧩 v1.1: OS keychain（keyring / DPAPI 等）は後回し

### 5.5 Pack import（フォルダ / zip / rumipack）

- ✅ フォルダ / zip / rumipack 取り込み
- ✅ zip 構造は「トップ単一ディレクトリ必須」
- ✅ zip slip / サイズ制限等の防御
- ✅ staging → apply（バックアップ付き）
- ✅ pack_identity mismatch 置換防止（事故防止）

### 5.6 階層権限（host > parent > child）

- ✅ pack_id `parent__child` を前提に parent chain を解決
- ✅ 子が許可されても親が許可されないと拒否
- ✅ 親の config が子に上限（intersection）

### 5.7 Flow 実行の整合

- ✅ async 経路と pipeline 経路の `kernel:*` 解決統一
- ✅ startup flow の packs_dir 等の整合修正
- ✅ _eval_condition パーサー改善（値内の == / != 対応）— Wave 1 #16
- ✅ _resolve_value 再帰深度制限（MAX_RESOLVE_DEPTH=20）— Wave 1 #70
- ✅ Flow チェーン深度制限（MAX_FLOW_CHAIN_DEPTH=10）— Wave 1 #58

### 5.8 セキュリティ強化（Wave 1）

- ✅ cryptography 必須化（base64フォールバック削除）— #1
- ✅ API サーバー バインドアドレス制限（デフォルト 127.0.0.1）— #3
- ✅ ホスト実行タイムアウト（ThreadPoolExecutor, 120s）— #4
- ✅ pack_id バリデーション統一（^[a-zA-Z0-9_-]{1,64}$）— #9
- ✅ Store root_path パストラバーサル防止 — #5, #12
- ✅ コンテナ名 UUID 化（衝突回避）— #10
- ✅ Docker stdout サイズ制限（4MB）— #14
- ✅ Docker 可用性キャッシュ（60s TTL）— #17
- ✅ DNS rebinding 緩和（egress_proxy）— #13
- ✅ egress_proxy ThreadPool 化 — #33
- ✅ HMAC 署名ロジック統合（HMACSigner）— #65
- ✅ HMAC 鍵ファイル atomic write — #34
- ✅ ワイルドカードドメイン警告 — #31
- ✅ API エラーメッセージ秘匿 — #35
- ✅ ファイル名バリデーション（secure_executor）— #57
- ✅ pack_import パストラバーサル防止 — #30
- ✅ DELETE ルート衝突解決 — #59

### 5.9 エコシステム基盤強化（Wave 1）

- ✅ Flow Modifier ワイルドカード警告・dry-run モード — #7, #40
- ✅ Modifier phase 未指定時のデフォルト動作 — #8
- ✅ 重複 pack_id 検出 — #15
- ✅ connectivity requires 未充足警告 — #20
- ✅ ワイルドカード Modifier 監査ログ — #61
- ✅ No Favoritism: dead code 削除（initializer.py）、docstring 中性化 — NF1-3

---

## 6. v1.5〜v2（中期）: 拡張しても壊れないための発展

### 6.1 Store / Unit（共有領域と再利用単位）

- ✅ Store registry（複数 store、パス固定しない）— `core_runtime/store_registry.py` 実装済み
- ✅ Unit registry（data / python / binary）— `core_runtime/unit_registry.py` 実装済み
- ✅ Unit trust store（sha256 allowlist）— `core_runtime/unit_trust_store.py` 実装済み
- 🟡 Unit execution gate（host_capability モードのみ実装済み。pack container / sandbox は未実装）— `core_runtime/unit_executor.py`
- ✅ Store Compare-And-Swap（store.cas）— fcntl.flock ベース — Wave 2 #6
- ✅ store.list ページネーション（limit / cursor / prefix）— Wave 2 #18
- ✅ store.batch_get（最大100キー、900KB制限）— Wave 2 #19
- ✅ 宣言的 Store 作成（ecosystem.json の stores フィールド）— Wave 2 #62
- ✅ Pack 間 Store 共有（SharedStoreManager、手動承認）— Wave 2 #21
- 🧩 「Pack 承認は必須、Unit 個別承認はユニット設定次第（pack が要求可能）」の運用整備

> ここは「assets」という語は使わない。ecosystem が「互換再利用のためのストア」を作ればそれは成立する。

### 6.2 capability のバイナリ対応強化（Python 無し運用の現実化）

- 🧩 handler.json の artifacts（os / arch 別）対応
- 🧩 trust store の拡張（handler_id → 複数 sha256）
- 🧩 executor の直接バイナリ実行（stdin JSON / stdout JSON）
- 🧩 「Rumi 本体を単一実行ファイル化」との比較検討（UX / 運用）

### 6.3 更新適用の完全 capability 化

- 🧩 `pack.update` permission の標準化（公式は意味を解釈しないが「危険操作の枠」として）
- 🧩 apply 操作は capability 経由に寄せ、API 直叩きは最小化
- 🧩 バージョン履歴・ロールバック（staging / backup の標準運用）

### 6.4 Capability 拡張（Wave 2）

- ✅ flow.run Capability（同期 Flow-to-Flow 呼び出し、循環検出、深度制限）— Wave 2 #5
- ✅ バッチ Capability Grant（最大50件、best-effort）— Wave 2 #63
- ✅ スケジューラ タイムゾーン対応（zoneinfo、UTC フォールバック）— Wave 2 #60

### 6.5 vocab による component 出力キー正規化（Pack 互換レイヤー）

- 🧩 component type 単位での出力キー自動正規化
- 🧩 vocab_registry の synonym グループ + converter を Flow 実行パスに統合
- 🧩 正規化タイミングの標準化（ctx 格納前 vs 参照時）
- 🧩 Pack 側の vocab.txt による synonym 宣言の推奨パターン整備

#### 背景

サードパーティ Pack の開発で判明した問題。kernel_core の _execute_handler_step_async は Flow ステップの return 値をそのまま ctx[step["output"]] に格納する。つまり default Pack が {"content": "...", "model": "gpt-4"} を返す構造で Flow が ${ctx.ai_response.content} を参照していると、別の Pack のように {"text": "...", "model_name": "..."} を返す Pack に差し替えた瞬間、全ての Flow ステップで content が null になり壊れる。

vocab_registry はこの問題を解決する仕組みを既に持つが、「Flow 実行パスでの自動適用」が欠けている。

#### 提案する実装案

**方式 A（格納時正規化 — 推奨）**: kernel_core の ctx 格納前に vocab_registry で preferred term に変換。数行の変更で既存の仕組みが活きる。

**方式 B（参照時正規化）**: _resolve_value で synonym フォールバック。格納データは変更しないが解決パスが複雑。

**方式 C（opt-in 正規化）**: Flow ステップに normalize: true フラグ、または component manifest で output_vocab_group を宣言。既存影響ゼロだが Pack 作者が意識する必要あり。

### 6.6 内部リファクタリング（P3 保留）

- 🧩 グローバルシングルトン → DI コンテナ移行（テスタビリティ向上）
- 🧩 Store バックエンド SQLite 化（ファイルベースからの移行オプション）
- 🧩 pack_api_server.py の大規模ハンドラ分割（現在 ~80KB）
- 🧩 Docker 実行ロジック共通化（python_file_executor / secure_executor の統合）

---

## 7. v3（長期）: ecosystem で実現すべき外側

> v3 の項目は公式コアが実装すべきものではなく、ecosystem（Pack）として
> 第三者が提供すべきものです。公式はこれらの機能を実現するための
> 汎用的な仕組み（API サーバー、Store、Capability 等）を提供済みです。

### 7.1 管理 UI
- 管理 UI は Pack として実装可能（pack_api_server の API を呼ぶフロントエンド Pack）
- 公式は HTTP API を提供済み。UI は ecosystem の領域

### 7.2 外部認証連携
- Supabase 等の認証は Pack が Secrets + capability 経由で実現可能
- 公式は認証の仕組みを強制しない

---

## 8. Addon（廃止済み）

`backend_core/ecosystem/addon_manager.py` に存在していた JSON Patch ベースの addon 機構は削除済みです。Flow Modifier がその役割を代替します。

---

## 9. ルール・運用（Runbook 要点）

- strict が本番推奨（Docker 必須）
- secrets は value を一切ログに出さない
- capability は Trust + Grant の二段構え
- pip 依存は wheel-only が基本、sdist は例外承認
- 更新は自動適用しない（ユーザー操作が必須）
- スキップ / 拒否は audit + diagnostics で追跡

---

## 10. 今後の論点（未確定を明文化）

- Store / Unit の運用整備をどこまで公式が標準化するか（枠だけ vs もう少し厚く）
- Unit の個別承認の UX（pending が増えすぎない設計）
- Unit execution gate の pack container / sandbox モード実装
- Python 無し配布の最短ルート（本体単一化 vs handler バイナリ化）
- 階層権限の config 上限（intersection の定義: list は積集合、ports は最小等）
- vocab による出力キー正規化の適用範囲（全ステップ vs opt-in vs component type 限定）
- vocab synonym の衝突解決（Pack A が content = 本文、Pack B が content = HTML全体 の場合）
- converter の実行セキュリティ（任意 Python が走るため Trust が必要か）
- provides パターンの統一（schema は ^[a-z][a-z0-9_]*$ だが pack-development.md の例は ai.client とドット区切り — どちらを正とするか）

---

## 付録: 重要なアンチパターン（やらない）

- secrets をコンテナにマウントして Pack に読ませる（即 NG）
- 公式が tool / chat 等を固定概念として持つ（No Favoritism 違反）
- auto update（ユーザーの明示操作無しに ecosystem を書き換える）
- 監査ログに秘密値や復号可能情報を出す
```
