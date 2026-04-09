# 同意（Consent）ガイド

## 1. 概念と目的

同意 tool は、AI の応答が投資助言・医療助言・法律助言など専門領域に該当する場合に、ユーザーに免責事項を表示して同意を求めるための仕組みである。

defaults Pack は同意の仕組み全体（判定ロジック・handler・UI ポップアップ連携・イベント通信）を提供する。具体的には以下のファイルが defaults Pack 内に配置されている。

| ファイル | 説明 |
|---|---|
| `blocks/tool/consent_check.py` | 判定 handler（`defaults.tool.consent_check`） |
| `blocks/tool/consent_confirm.py` | 同意記録 handler（`defaults.tool.consent_confirm`） |
| `domain/tool/consent.py` | `ConsentChecker` クラス（判定ロジック・同意記録管理） |

`ecosystem.json` の `tool` コンポーネントの `provides` に `defaults.tool.consent_check` と `defaults.tool.consent_confirm` が宣言されている。HTTP transport では `POST /api/consent/check` と `POST /api/consent/{id}/confirm` のルートでアクセスできる。


## 2. 判定の仕組み

### キーワードベース判定

軽量・高速な一次判定。応答テキストに特定のキーワードが含まれるかチェックする。`domain/tool/consent.py` の `ConsentChecker.check_keywords()` が実行する。カテゴリとキーワードは `CATEGORIES` dict としてモジュール内にハードコードされている。

```python
# domain/tool/consent.py より抜粋
CATEGORIES = {
    "investment": {
        "keywords": ["投資", "株", "株式", "株価", "銘柄", "ポートフォリオ",
                     "資産運用", "利回り", "配当", "投資信託", "ファンド",
                     "FX", "為替", "仮想通貨", "暗号資産", "ビットコイン",
                     "ETF", "NISA", "iDeCo", "信用取引", "空売り",
                     "investment", "stock", "portfolio", "dividend", "fund",
                     "forex", "crypto", "bitcoin", "trading"],
        "disclaimer": "【免責事項 — 投資に関する情報】..."
    },
    "medical": {
        "keywords": ["診断", "治療", "処方", "薬", "服薬", "投薬",
                     "症状", "病気", "疾患", "手術", "副作用",
                     "医療", "医師", "病院", "クリニック",
                     "diagnosis", "treatment", "prescription", "medication",
                     "symptom", "disease", "surgery", "side effect"],
        "disclaimer": "【免責事項 — 医療に関する情報】..."
    },
    "legal": {
        "keywords": ["訴訟", "裁判", "弁護士", "法律相談", "契約書",
                     "損害賠償", "慰謝料", "示談", "告訴", "起訴",
                     "法的", "判例", "法令", "条文", "権利",
                     "lawsuit", "attorney", "legal advice", "contract",
                     "liability", "damages", "litigation"],
        "disclaimer": "【免責事項 — 法律に関する情報】..."
    },
    "tax": {
        "keywords": ["税金", "確定申告", "所得税", "住民税", "消費税",
                     "法人税", "相続税", "贈与税", "控除", "節税",
                     "税務", "年末調整", "源泉徴収", "経費", "減価償却",
                     "tax", "deduction", "income tax", "tax return"],
        "disclaimer": "【免責事項 — 税務に関する情報】..."
    },
}
```

### AI ベース判定

`consent_check` handler の `use_ai` パラメータを `true` にすると、`ConsentChecker.check_ai()` が AI ベース判定を実行する。内部で `AIClient.complete()` を呼び出し、テキストがセンシティブカテゴリに該当するかを分類する。

```python
# domain/tool/consent.py の AI 判定用システムプロンプト
_AI_JUDGE_SYSTEM = (
    "You are a content classifier. Analyze the given text and determine "
    "if it contains sensitive advice in any of these categories: "
    "investment, tax, medical, legal.\n"
    "Respond with ONLY a JSON object: "
    '{"categories": ["category1", ...], "confidence": 0.0-1.0}\n'
    "If no sensitive content is found, respond: "
    '{"categories": [], "confidence": 1.0}'
)
```

`ConsentChecker.check()` はキーワード判定と AI 判定を組み合わせる。キーワード判定は偽陽性が多いが漏れが少なく、AI 判定は偽陽性が少ないが遅い。


## 3. handler API

### defaults.tool.consent_check

テキストを判定し、同意が必要かどうかを返す。

**HTTP**: `POST /api/consent/check`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `text` | `string` | Yes | 判定対象テキスト |
| `use_ai` | `bool` | No | AI 判定を使うか（デフォルト `false`） |
| `model` | `string` | No | AI 判定時のモデル指定（デフォルト `"stub/default"`） |

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "requires_consent": true,
    "categories": ["investment", "medical"],
    "consent_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "disclaimers": {
      "investment": "【免責事項 — 投資に関する情報】...",
      "medical": "【免責事項 — 医療に関する情報】..."
    }
  }
}
```

`requires_consent` が `false` の場合、`categories` は空配列、`consent_id` は `null`、`disclaimers` は空 dict になる。

### defaults.tool.consent_confirm

ユーザーの同意/拒否を記録する。

**HTTP**: `POST /api/consent/{id}/confirm`

**input_data**:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `consent_id` | `string` | Yes | `consent_check` が返した consent_id（HTTP ではパスパラメータから注入） |
| `accepted` | `bool` | Yes | ユーザーが同意したか |

**戻り値**:

```json
{
  "status": "ok",
  "data": {
    "consent_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "accepted": true,
    "accepted_at": "2025-01-01T00:00:00Z"
  }
}
```

同意記録は `user_data/shared/consent_log/{consent_id}.json` に永続化される（`ConsentChecker._persist()` で書き込み）。


## 4. chat.send への統合方法（案）

`blocks/tool/consent_check.py` のドキュメントストリングに記載されている統合案:

```python
# blocks/chat/send.py の assistant_msg 生成後に追加
consent_result = call_handler("defaults.tool.consent_check", {
    "text": assistant_response_text,
    "use_ai": False,
})
if consent_result["data"]["requires_consent"]:
    context["emit_widget"]({
        "type": "consent_popup",
        "consent_id": consent_result["data"]["consent_id"],
        "disclaimers": consent_result["data"]["disclaimers"],
    })
    user_response = context["wait_event"]("ui.consent_response",
        timeout=300,
        filter={"consent_id": consent_result["data"]["consent_id"]})
    call_handler("defaults.tool.consent_confirm", {
        "consent_id": consent_result["data"]["consent_id"],
        "accepted": user_response.get("accepted", False),
    })
```


## 5. フロントエンドでの表示

同意ポップアップは `emit_widget` または `emit_event("ui.popup.show", ...)` で表示される。フロントエンド側の Asset がこのイベントを受信し、ポップアップを描画する。

Asset の JS が `event.broadcast` を受信し、`event_type` が `"ui.popup.show"` であればポップアップを表示する。ユーザーがボタンをクリックしたら `event.broadcast` で `"ui.popup.response"` イベントを返送する。

Widget としてポップアップを表現する場合:

```json
{
  "type": "card",
  "style_hint": {"variant": "warning"},
  "header": {"type": "text", "text": "投資に関する免責事項"},
  "body": {"type": "markdown", "content": "この情報は一般的な情報提供を目的としており..."},
  "footer": {
    "type": "row",
    "children": [
      {"type": "button", "label": "同意して表示", "action": "consent_accept", "variant": "primary"},
      {"type": "button", "label": "表示しない", "action": "consent_deny", "variant": "secondary"}
    ]
  }
}
```

同意 tool のポップアップはフロントエンドの Asset が描画する。defaults は emit_event / wait_event / emit_widget という汎用通信の仕組みと、判定・記録の handler を提供する。
