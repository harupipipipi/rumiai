<!-- docs-i18n-links:start -->
[EN](../../consent.md) | [JP](./consent.md) | [KR](../ko/consent.md) | [CN](../zh-cn/consent.md)
<!-- docs-i18n-links:end -->

# 同意ガイド

## 1. コンセプトと目的

同意ツールは、AIの回答が投資アドバイスや医療アドバイス、法律アドバイスなどの専門分野に該当する場合に、ユーザーに免責事項を表示し、同意を求める仕組みです。

デフォルト パックは、同意メカニズム全体 (判断ロジック、ハンドラー、UI ポップアップ コラボレーション、イベント通信) を提供します。具体的には、次のファイルがデフォルト パックに配置されます。

| File | Description |
|---|---|
| `blocks/tool/consent_check.py` | Judgment handler (`defaults.tool.consent_check`) |
| `blocks/tool/consent_confirm.py` | Consent record handler (`defaults.tool.consent_confirm`) |
| `domain/tool/consent.py` | `ConsentChecker` Class (determination logic/consent record management) |

`defaults.tool.consent_check` および `defaults.tool.consent_confirm` は、`ecosystem.json` の `tool` コンポーネントの `provides` で宣言されています。 HTTP トランスポートには、ルート `POST /api/consent/check` および `POST /api/consent/{id}/confirm` を使用してアクセスできます。


## 2. 判定の仕組み

### キーワードによる判断

軽量かつ迅速な一次判定。応答テキストに特定のキーワードが含まれているかどうかを確認します。 `domain/tool/consent.py`の`ConsentChecker.check_keywords()`が実行されます。カテゴリとキーワードは、`CATEGORIES` 辞書としてモジュールにハードコーディングされています。

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

### AIによる判断

`consent_check`ハンドラの`use_ai`パラメータを`true`に設定すると、`ConsentChecker.check_ai()`がAI判定を行います。 `AIClient.complete()` を内部的に呼び出して、テキストが機密カテゴリに分類されるかどうかを分類します。

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

`ConsentChecker.check()`はキーワード判定とAI判定を組み合わせたものです。キーワード判定は誤検知は多いが抜けは少なく、AI判定は誤検知は少ないが遅い。


## 3. ハンドラー API

### defaults.tool.consent_check

テキストを決定し、同意が必要かどうかを返します。

**HTTP**: `POST /api/consent/check`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | `string` | Yes | Judgment target text |
| `use_ai` | `bool` | No | Use AI judgment (default `false`) |
| `model` | `string` | No | Model specification during AI judgment (default `"stub/default"`) |

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

`requires_consent` が `false` である場合、`categories` は空の配列、`consent_id` は `null`、`disclaimers` は空の辞書です。

### defaults.tool.consent_confirm

ユーザーの同意/拒否を記録します。

**HTTP**: `POST /api/consent/{id}/confirm`**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `consent_id` | `string` | Yes | consent_id returned by `consent_check` (injected from path parameter in HTTP) |
| `accepted` | `bool` | Yes | User consent |

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

同意記録は `user_data/shared/consent_log/{consent_id}.json` で永続化されます (`ConsentChecker._persist()` で記述)。


## 4. chat.send への統合方法 (提案)

`blocks/tool/consent_check.py` の docstring に記載されている推奨される統合:

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

`emit_widget`または`emit_event("ui.popup.show", ...)`で同意ポップアップが表示されます。フロントエンドのアセットはこのイベントを受け取り、ポップアップを描画します。

Asset の JS が `event.broadcast` を受け取り、`event_type` が `"ui.popup.show"` である場合、ポップアップが表示されます。ユーザーがボタンをクリックすると、`event.broadcast` は `"ui.popup.response"` イベントを送り返します。

ポップアップをウィジェットとして表現する場合:

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

同意ツールのポップアップは、フロントエンド アセットによって描画されます。 defaults は、emit_event / wait_event / Emit_widget という汎用の通信機構と、判定・記録用のハンドラを提供します。
