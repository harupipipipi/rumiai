# Rumi AI OS / Ecosystem (rumi_ai_1_10)

このプロジェクトは「AIチャットアプリ」を作るための“完成品”というより、**AI時代のOS / MinecraftのようなMod基盤**を作る試みです。  
AI業界は変化が速く、数年前には「ツール（Function Calling）」のような概念すら一般的ではありませんでした。  
だからこそ、このプロジェクトは **特定の機能（tool / prompt / ai_client / chat 等）を前提に固定しない**設計を目指します。

ここで提供するのは、用途を決め打ちしない「枠組み（器）」と「接続の仕組み」です。  
その上で、コミュニティが自由に機能を追加・差し替え・互換対応（他Mod対応）できる世界を目指しています。

---

## 1. ビジョン：MinecraftのMod文化 × OS設計

### MinecraftのMod文化から学ぶこと
Minecraftでは、Mod同士が増殖しても遊べるのは「受け皿（本体API / ロード順 / 互換文化）」があるからです。  
このプロジェクトはそれをAI領域で再現します。

- **Mod作者が “フォルダを追加するだけ” で拡張できる**
- **他Mod対応**（Aが入っているならBに合わせて挙動を変える）を仕組みとして持てる
- ベースが変わっても拡張が生き残れる（互換文化を作る）

### ただしMinecraftと違う点
Minecraftは「ゲーム本体」という強いベースが固定されています。  
一方、AIアプリ領域では「何が本体か」が揺れ続けます。

- チャットUIが本体なのか
- ルーティングが本体なのか
- ツールが本体なのか
- エージェント（AI→ツール→AI）が本体なのか

このプロジェクトは、**“本体（ベース）を機能として固定しない”**ことを選びます。  
本体は「接続・配線・観測・失敗しても続く」などの**OS的な能力**に寄せます。

---

## 2. 公式（Official）と非公式（Community）の境界

このプロジェクトでは、コードを大きく2つに分けます。

### 公式（変更されにくい / 枠組み）
- `app.py`  
- `backend_core/`（Ecosystemエンジン：mounts/registry/addon/compat 等）
- `core_runtime/`（Kernel：Flow実行器、Diagnostics、InstallJournal、InterfaceRegistry 等）
- `flow/`（ベースとなるFlow。最小限）

公式は **tool / prompt / chats / ai_client / agent** といった概念を特別扱いしません。  
公式の責務は次だけです：

- **Flowをロードして実行する**
- **提供物（capability）を登録・探索できる**
- **イベント（event）で疎結合にできる**
- **fail-softで壊れにくく、診断できる**
- **Addonで差し込みできる**

### 非公式（コミュニティ領域 / すべて同等）
- `ecosystem/**`

`ecosystem` 内の全ファイルは **同格**です。  
`ecosystem/default` は「推奨テンプレ」「暗黙の了解の参照実装」であって、特権はありません。

コミュニティはここに自分のPack/Component/Addonを入れて拡張します。

---

## 3. Ecosystem：Pack / Component / Addon

### Pack
機能セットの配布単位です。`ecosystem/<pack_id>/` に存在します。  
Packは複数存在し得て、アクティブなPackを切り替えられます。

### Component
Pack内の機能モジュールです。Componentは用途を決め打ちせず、**「提供物（provides）」「要求（requires）」**として接続します。

### Addon（他Mod対応の核）
Addonは **既存ComponentやFlowに“差し込み・編集”を加える**ための仕組みです。

Minecraftで言えば：
- A Mod が入っている時だけ B Mod を最適化する
- 既存の挙動に一段足す

この世界では：
- AI呼び出し直前に「追加オブジェクト（例：tools）」を注入する
- 前処理・後処理を差し込む
- Flowにステップを挿入して互換を取る

---

## 4. Flow：みんなで書く“配線図 / プログラム”

Flowは、処理順を定義する**プログラムのようなもの**です。  
重要なのは、Flowが **特定機能の存在を前提にしない**ことです。

- Flowは `ctx`（コンテキスト）を加工するステップ列
- 各ステップは handler を呼び出し、`ctx` を読み書きする
- handlerの実装は ecosystem 側が提供できる
- Addonが Flowにパッチを当てて差し込める

つまり Flowは **コミュニティが共有し、改善し、互換を取るための「共通言語」**になります。

---

## 5. “贔屓しない”とは何か

このプロジェクトで言う「贔屓しない」とは：

- 公式コードが `tool_pack` や `ai_client_provider` などを固定で列挙しない
- 公式コードが特定の実装（ChatManager等）を直 import しない
- 公式は **接続プロトコル**（Flow / iface呼び出し / registry / events）だけを持つ

ただし、完全な無語彙では互換が崩壊します。  
だから最低限の“接続語彙”（例：`iface:` で呼ぶ、`http.blueprints`を登録する等）は持ちます。  
これは贔屓ではなく、OSの syscall 名に近い **互換のための最小共通言語**です。

---

## 6. fail-soft と観測性（Diagnostics）

Mod文化は「壊れる」ことを前提にします。  
だからこのプロジェクトは **fail-soft** を第一原則にします。

- Componentが失敗してもシステムは落ちない
- 失敗理由を必ず診断可能にする
- 起動や処理の記録が残る（Diagnostics / InstallJournal）

---

## 7. 将来：フロントエンドもMod化する

最終的にフロントも ecosystem 側で置換・追加できるようにします。

- setting / chat_ui / chat_input / wallpaper / button などを部品化
- “壁紙Mod”を入れると選択肢が増える
- “ボタンMod”を入れるとUIに部品が追加される
- UI操作は Intent/Event でバックエンドと接続し、固定API依存を減らす

---

## 8. このプロジェクトが目指す世界

- 「AIチャットアプリ」を作るというより、**AI時代のMod OS**を作る
- ベースを固定しない（概念の変化に耐える）
- 互換文化を作る（defaultは参照実装）
- Addonで他Mod対応できる
- Flowで配線を共有し、コミュニティが拡張していける

---

## 9. 開発スタイル（推奨）

- 公式はできるだけ小さく、抽象的に、用途非依存に保つ
- 実験や機能追加は ecosystem に寄せる
- 互換を取りたい場合は Addon/Flow patch で差し込む
- “動くこと”と同じくらい “壊れた時に追えること” を重視する

---

## ライセンス / コントリビューション
（ここはリポジトリ方針に合わせて追記してください）

- どんな形でPack/Component/Addonを配布したいか
- 互換文化（default準拠の推奨）をどう育てるか
- 破壊的変更をどう扱うか（flow_version / schema_version 等）

---
