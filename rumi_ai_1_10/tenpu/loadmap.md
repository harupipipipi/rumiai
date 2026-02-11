# roadmap.md — Rumi AI OS ロードマップ（思想・過去案含む完全版）

最終更新: 2026-02-11

この文書は、Rumi AI OS の「公式コア」と「ecosystem（default pack等）」を分離したまま、
セキュリティと運用を先に固め、後からいくらでも機能を載せられるようにするためのロードマップです。
過去の検討案（pack階層・共有ストア・unit実行など）もすべてここに統合します。

---

## 0. 北極星（Vision）

- **基盤のない基盤**：公式はドメイン概念（チャット/ツール/プロンプト/UI等）を一切持たず、
  「実行・承認・隔離・監査・権限」という *OS的な仕組み* のみを提供する。
- ecosystem は第三者が作る前提（悪意前提）で、**承認必須**・**Docker隔離（strict推奨）**・**Fail-soft**・**監査ログ**が中核。

---

## 1. 設計原則（Principles）

### 1.1 No Favoritism（贔屓なし）
- 公式コアは「API key」「tool」「chat」等の意味を解釈しない。
- 公式が提供するのは汎用機構：
  - Flow実行
  - 承認ゲート（hash検証）
  - 隔離実行（Docker / UDS）
  - Trust + Grant（capability）
  - 監査ログ

### 1.2 悪意前提（Threat model）
- Pack作者に悪意がある可能性を常に想定。
- Pack実行は原則 Docker `--network=none`。
- 外部通信やホスト特権は **capability（Trust+Grant）**に寄せる。

### 1.3 Fail-soft
- 一部が壊れてもOS全体は止めない。診断（Diagnostics）と監査（Audit）で可視化し継続する。

### 1.4 “ホスト権限” の単一入口
- ホストで危険なこと（外部通信、ファイルアクセス、更新適用、ターミナル等）は、
  Packから直接やらせず **capability** で仲介し、許可がない限り動かない。

---

## 2. コンセプト整理（用語は汎用に寄せる）

### 2.1 Pack / principal / capability
- **principal**：権限判断の主体。v1は運用を簡単にするため **pack_id単位**を基本とする。
- capabilityは `permission_id` で要求し、**Trust（sha256）**と **Grant（principal×permission）**で許可。

### 2.2 pack in pack（階層化）
- 過去案：`parent__child` のように階層を pack_id で表現し、
  “上位が下位を制限する（上位が許可しないと下位は動かない）” を実現したい。
- 目的：
  - bundle配布（defaultがtool群を束ねる等）
  - 運用の一括管理
  - 権限の親子制約（下位だけ許可では動かない）

> 注意：ディレクトリ階層＝セキュリティ境界、ではない。
> 強制力は「ホスト側のゲート（capability/実行器）」で担保する。

### 2.3 Store / Unit（共有領域と再利用単位）
- 過去案：「assets」は例。公式は “assets” を概念として固定しない。
- しかし **ユーザー/ecoが任意に作れる共有領域（Store）** と、
  その中の **再利用単位（Unit）** は汎用基盤として価値がある。
- Unitは `data/python/binary` 等を取りうる。
- 実行系Unitは **実行するPackが善意でも、Unit自体が悪意**の可能性があるため、
  **Pack承認＋Unit Trust（sha256 allowlist）**を基本とする。
- 実行モードは権限に応じて選べる（矯正しない）：
  - pack container
  - host capability
  - dedicated sandbox（将来）

---

## 3. すでに固めたい／固めたかった “公式コアの土台” 一覧（背景の完全反映）

### 3.1 依存（pip）導入
- Packが `requirements.lock` を同梱
- wheel-onlyがデフォルト（sdistは例外承認）
- builderコンテナで download→install（installはoffline）
- 実行時は site-packages をROマウント＋PYTHONPATHで見せる（コンテナは network=none 維持）

### 3.2 capability handler 候補導入（承認ワークフロー）
- ecosystemに “候補” を同梱
- scan→pending→approve/reject→blocked（3回reject）
- approveで Trust登録＋コピー＋registry reload
- cooldown 1h、blockedはunblockまで通知しない

### 3.3 Secrets（API keyの保存）
- `.env` を避ける（事故率低減）
- `user_data/secrets/` に格納、ログに値を出さない
- Packに秘密ファイルを見せない
- 取得は capability（例: `secret.get`）経由が基本

### 3.4 Pack配布形式
- 入力3形態：フォルダ / `.zip` / `.rumipack`（zip互換）
- 推奨：トップに pack root 1つ
- （将来）multi-pack archive（pack in pack）にも拡張可能

### 3.5 更新適用（auto update禁止）
- 公式はオートアップデートしない
- 取得→staging→適用、の分離
- applyは危険なので capability（pack.update）へ寄せたい（v1は運用APIでも可）
- 単一pack_idの適用から開始

### 3.6 実行（Python / バイナリ）
- Packの通常実行は Docker隔離で成立するので、ホストにPythonが無くても（Dockerさえあれば）OK
- ホストで動くもの（capability handler等）は、将来的に
  - Rumi本体を単一実行ファイル化（Python同梱）するか
  - handlerをOS別バイナリにする
  のどちらかが必要になる（両対応も可）

---

## 4. 実装ステータス（このロードマップ上の状態表現）

このロードマップでは、各項目を以下の状態で管理します。

- ✅ Done（実装済み・運用可能）
- 🟡 Partial（基盤はある／改善が必要）
- 🧩 Planned（設計済み・未実装）
- 🧪 Experimental（実験・後で仕様固め）

> 注：あなたのメッセージ「実装は完了しました」を受け、直近の大項目は✅扱いに寄せています。
> ただし、実リポジトリ状態の自動検証はここでは行っていません（必要なら後でチェックリスト化）。

---

## 5. v1（現在〜直近）: “運用できるOS” の完成（公式コア）

### 5.1 セキュア実行・承認・監査（基盤）
- ✅ Pack承認（hash検証、modified検出、blocked）
- ✅ 監査ログ（カテゴリ別 jsonl）
- ✅ Docker隔離（strict推奨、permissiveは警告）

### 5.2 pip依存導入（requirements.lock）
- ✅ scan→approve→builderでdownload/install
- ✅ site-packages ROマウント＋PYTHONPATH
- 🟡 sdist例外（allow_sdist）運用の監査明確化（継続改善）

### 5.3 capability（Trust+Grant+候補導入）
- ✅ 候補導入フロー（pending/approve/reject/blocked/cooldown）
- ✅ Trust store / Grant manager / Executor / Proxy（UDS）
- ✅ principal単位のgrant管理（HMAC署名）
- 🟡 マルチプラットフォームバイナリ（trustの拡張）は中期

### 5.4 Secrets（平文でOK、事故率低減）
- ✅ user_data/secrets（1 key=1 file、tombstone、journal）
- ✅ APIは list(mask)/set/delete のみ（再表示なし）
- ✅ ログに値を出さない（監査・診断とも）
- ✅ `secret.get` の rate_limit=60（事故防止）
- 🧩 v1.1: OS keychain（keyring/DPAPI等）は後回し

### 5.5 Pack import（フォルダ/zip/rumipack）
- ✅ フォルダ/zip/rumipack取り込み
- ✅ zip構造は “トップ単一ディレクトリ必須”
- ✅ zip slip / サイズ制限 等の防御
- ✅ staging→apply（バックアップ付き）
- ✅ pack_identity mismatch置換防止（事故防止）

### 5.6 階層権限（host > parent > child）
- ✅ pack_id `parent__child` を前提に parent chain を解決
- ✅ 子が許可されても親が許可されないと拒否
- ✅ 親のconfigが子に上限（intersection）

### 5.7 Flow実行の整合
- ✅ async経路とpipeline経路の `kernel:*` 解決統一
- ✅ startup flow の packs_dir 等の整合修正

---

## 6. v1.5〜v2（中期）: “拡張しても壊れない” ための発展

### 6.1 Store / Unit（共有領域と再利用単位）
- 🧩 Store registry（複数store、パス固定しない）
- 🧩 Unit registry（data/python/binary）
- 🧩 Unit trust store（sha256 allowlist）
- 🧩 Unit execution gate（host/pack container/sandbox を選べる枠）
- 🧩 「Pack承認は必須、Unit個別承認はユニット設定次第（packが要求可能）」の運用整備

> ここは「assets」という語は使わない。
> ecosystemが「互換再利用のためのストア」を作ればそれは成立する。

### 6.2 capabilityのバイナリ対応強化（Python無し運用の現実化）
- 🧩 handler.json の artifacts（os/arch別）対応
- 🧩 trust store の拡張（handler_id→複数sha256）
- 🧩 executorの直接バイナリ実行（stdin JSON / stdout JSON）
- 🧩 “Rumi本体を単一実行ファイル化” との比較検討（UX/運用）

### 6.3 更新適用の完全capability化
- 🧩 `pack.update` permission の標準化（公式は意味を解釈しないが“危険操作の枠”として）
- 🧩 apply操作は capability経由に寄せ、API直叩きは最小化
- 🧩 バージョン履歴・ロールバック（staging/backupの標準運用）

---

## 7. v3（長期）: ユーザー獲得のための“外側”はecosystemへ（公式は薄いまま）

### 7.1 ローカル管理UI（Electron等）
- 🧩 承認（pack/capability/pip/unit）を見える化
- 🧩 Secrets UI（再表示無し・貼り付け時だけ表示）
- 🧩 Store/Unit 管理 UI（互換再利用の操作）
- 🧩 doctor（Docker可否、UDS、audit、staging状態、modified一覧）

### 7.2 Supabaseログイン（任意）
- 🧩 強制しない（プロフィール表示程度）
- 🧩 無料プラン前提で会話保存等はしない

---

## 8. Addon（現状と廃止方針）
- 現状：`backend_core.ecosystem.addon_manager` に JSON Patch ベースのaddon機構が存在
- 方針：消す予定
  - v1: deprecated（新規利用停止、警告）
  - v2: 互換期間（必要なら移行ガイド）
  - v3: 削除

---

## 9. ルール・運用（Runbook要点）
- strictが本番推奨（Docker必須）
- secretsは value を一切ログに出さない
- capabilityは Trust+Grant の二段構え
- pip依存は wheel-onlyが基本、sdistは例外承認
- 更新は自動適用しない（ユーザー操作が必須）
- スキップ/拒否は audit+diagnostics で追跡

---

## 10. 今後の論点（未確定を明文化）
- Store/Unit をどこまで公式が標準化するか（枠だけ vs もう少し厚く）
- Unitの個別承認のUX（pendingが増えすぎない設計）
- “Python無し配布” の最短ルート（本体単一化 vs handlerバイナリ化）
- 階層権限のconfig上限（intersectionの定義：listは積集合、portsは最小等）

---

## 付録A: 重要なアンチパターン（やらない）
- secretsをコンテナにマウントしてPackに読ませる（即NG）
- 公式が “tool/chat/etc” を固定概念として持つ（No Favoritism違反）
- auto update（ユーザーの明示操作無しにecosystemを書き換える）
- 監査ログに秘密値や復号可能情報を出す

---
