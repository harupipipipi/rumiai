```markdown
# Rumi AI OS

**基盤のない基盤 ― AIエコシステムのためのOS**

---

## 🌟 このプロジェクトについて

現在のAI開発は混沌としています：

- APIはプロバイダーごとにバラバラ
- 新機能が毎週のように登場
- 昨日の常識が今日は通用しない
- カスタマイズすると本体更新が困難に

**Rumi AI OS**は、この問題に対する根本的な解決策です。

Minecraftのmodのように、**公式ファイルを一切編集せずに**機能を追加・変更できる。しかしMinecraftと決定的に違うのは、**改造する「本体」が存在しない**ことです。

---

## 💭 思想

### 「基盤のない基盤」とは

Minecraftのmodは「Minecraft」という基盤を改造します。
しかしRumi AI OSには、改造される「本体」がありません。

```
Minecraft の世界:
┌─────────────────────────────────┐
│         Minecraft本体            │  ← これを改造
│  (ブロック、クリーパー、etc.)     │
├─────────────────────────────────┤
│            Mod A                 │
│            Mod B                 │
└─────────────────────────────────┘

Rumi AI OS の世界:
┌─────────────────────────────────┐
│                                 │
│    Component ←→ Component       │
│        ↑           ↓            │  ← 網のように繋がる
│    Component ←→ Component       │
│                                 │
├─────────────────────────────────┤
│     Kernel (実行ルールのみ)       │  ← 「何を」ではなく「どう動くか」だけ
└─────────────────────────────────┘
```

公式が定義するのは**実行ルール**だけです：

- `setup.py` → 起動時に実行される
- `dependency_manager.py` → 環境構築時に実行される
- `runtime_boot.py` → サービス登録時に実行される

**「チャット」「ツール」「プロンプト」「AIクライアント」― これらは全て公式の知らない概念です。**

誰かがそういうComponentを作り、他のComponentがそれを見つけて繋がる。それだけです。

---

### 贔屓なし (No Favoritism)

```
❌ 公式が「チャット機能」を実装
❌ 公式が「ツール」の仕様を定義
❌ 公式が「AIクライアント」のインターフェースを決定

✅ 公式は実行の仕組みだけを提供
✅ 全てのComponentは平等
✅ 「公式Component」という概念すら存在しない
```

`ecosystem/default/` にあるComponentも、あなたが作るComponentも、完全に同じルールで動きます。公式が特別扱いすることはありません。

---

### なぜこの設計なのか

AIの世界は変化が速すぎます。

- 今日の最先端は来月の遺物
- 特定のAPIに依存すると、そのAPI廃止で全てが壊れる
- 「正しい設計」は1年後には「古い設計」

だからこそ、**公式は何も決めない**。

コミュニティが自由に作り、自由に繋げ、自由に置き換える。公式はその「場」を提供するだけです。

---

## 📐 公式と非公式の境界

### 公式ファイル（これだけ）

```
app.py              # Flaskエントリポイント
core_runtime/       # Kernel（Flow実行エンジン）
backend_core/       # エコシステム基盤
```

### 公式が定義するルール

| ファイル名 | 実行タイミング |
|-----------|---------------|
| `dependency_manager.py` | 環境未構築時 |
| `setup.py` | 毎回起動時（冪等であること） |
| `runtime_boot.py` | サービス登録フェーズ |

### 公式が定義しないもの

- Component の「種類」（chat, tool, prompt, ai_client, etc.）
- Component 間の通信プロトコル
- データの保存形式
- UIの構造

**全てはecosystem内のComponentが自己定義します。**

---

## 🕸️ Componentの繋がり方

Componentは**InterfaceRegistry**を通じて互いを発見します。

```python
# Component A: 何かのサービスを提供
def run(context):
    ir = context["interface_registry"]
    ir.register("something.useful", MyService())

# Component B: そのサービスを使う（Aの存在を知らなくてもいい）
def run(context):
    ir = context["interface_registry"]
    service = ir.get("something.useful")
    if service:
        service.do_work()
```

公式は `something.useful` が何なのか知りません。Component AとBが勝手に約束を作り、勝手に繋がっています。

これが「網のように繋がる」ということです。

---

## 📁 ディレクトリ構造

```
project_root/
│
├── app.py                          # 公式：Flaskエントリ
├── core_runtime/                   # 公式：Kernel
│   ├── kernel.py
│   ├── diagnostics.py
│   ├── interface_registry.py
│   └── ...
├── backend_core/                   # 公式：エコシステム基盤
│   └── ecosystem/
│       ├── mounts.py
│       ├── registry.py
│       └── ...
│
├── flow/                           # Flow定義
│   └── project.flow.yaml
│
├── ecosystem/                      # ここから下は全て非公式
│   └── [pack_name]/
│       ├── backend/
│       │   ├── ecosystem.json      # Pack定義
│       │   └── components/
│       │       └── [component]/
│       │           ├── manifest.json
│       │           ├── setup.py
│       │           └── ...
│       └── frontend/               # (将来)
│
└── user_data/                      # ユーザーデータ
```

---

## 🔨 Componentの作り方

### 最小構成

```
ecosystem/my_pack/backend/components/my_thing/
├── manifest.json
└── setup.py
```

### manifest.json

```json
{
  "type": "my_type",
  "id": "my_thing_v1",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["my.service"],
    "requires": []
  }
}
```

`type` は自由です。公式が「これは有効なtype」と定義することはありません。

### setup.py

```python
def run(context):
    ir = context.get("interface_registry")
    
    # 何かを登録
    ir.register("my.service", MyImplementation())
```

### 他のComponentを見つける

```python
def run(context):
    ir = context.get("interface_registry")
    
    # 誰かが登録したかもしれないサービスを探す
    something = ir.get("some.service", strategy="last")
    
    if something:
        # 見つかった！使う
        something.do_work()
    else:
        # 見つからなかった。それでも動く（fail-soft）
        pass
```

---

## 🌊 Flow

`flow/project.flow.yaml` がアプリケーションの動作を決定します。

```yaml
pipelines:
  startup:
    - id: mounts
      run: { handler: "kernel:mounts.init" }
    - id: registry
      run: { handler: "kernel:registry.load" }
    - id: setup
      run: { handler: "component_phase:setup" }
    # ... Componentが追加されれば、ここに自動で組み込まれる
  
  message:
    # メッセージ処理のパイプライン
    # これも ecosystem 内の Component が定義したものを実行
```

Flowは「何を実行するか」ではなく「どの順序で、どう実行するか」を定義します。

---

## 📊 現在の状況

### ✅ 完了

- Kernel（Flow実行エンジン）
- エコシステム基盤（Pack/Component読み込み）
- InterfaceRegistry（サービス発見）
- Diagnostics（診断・デバッグ）
- Backend Componentの移行

### 🚧 TODO

- Frontend のエコシステム移行
- Addon システム
- Pack配布形式（.ecopack）
- より多くのサンプルComponent

---

## 🚀 はじめる

```bash
# 依存インストール
pip install -r requirements.txt

# 起動
python app.py

# 確認
curl http://localhost:5000/api/diagnostics
```

---

## 🤝 コミュニティへ

このプロジェクトは**コミュニティ主導**を目指しています。

技術の進歩が速すぎて、特定の設計に固執することはできません。だから公式は最小限だけを定義し、残りはコミュニティに委ねます。

### 参加方法

1. **Componentを作る** ― 好きな機能を実装
2. **Packを作る** ― 複数のComponentをまとめて配布
3. **繋がりを作る** ― 他のComponentと連携
4. **置き換える** ― 既存のComponentをより良いもので置換

公式の許可は不要です。作って、公開して、使ってもらう。それだけです。

---

## 📜 設計原則

1. **公式ファイルの編集を必要としない**
2. **Fail-soft** ― エラーでもシステムは動き続ける
3. **診断可能** ― 何が起きているか常に見える
4. **贔屓なし** ― 公式Componentは存在しない
5. **用途非依存** ― Kernelは「AI」を知らない



*「基盤がないからこそ、何でも作れる」*
```