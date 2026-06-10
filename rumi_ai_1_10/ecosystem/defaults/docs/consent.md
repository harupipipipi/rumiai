<!-- docs-i18n-links:start -->
[EN](./consent.md) | [JP](./i18n/ja/consent.md) | [KR](./i18n/ko/consent.md) | [CN](./i18n/zh-cn/consent.md)
<!-- docs-i18n-links:end -->

# Consent Guide

## 1. Concept and purpose

The consent tool is a mechanism that displays a disclaimer to the user and requests consent when the AI response falls under specialized fields such as investment advice, medical advice, and legal advice.

The defaults pack provides the entire consent mechanism (judgment logic, handler, UI popup collaboration, event communication). Specifically, the following files are placed in the defaults pack.

| File | Description |
|---|---|
| `blocks/tool/consent_check.py` | Judgment handler (`defaults.tool.consent_check`) |
| `blocks/tool/consent_confirm.py` | Consent record handler (`defaults.tool.consent_confirm`) |
| `domain/tool/consent.py` | `ConsentChecker` Class (determination logic/consent record management) |

`defaults.tool.consent_check` and `defaults.tool.consent_confirm` are declared in `provides` of the `tool` component of `ecosystem.json`. HTTP transport can be accessed using the routes `POST /api/consent/check` and `POST /api/consent/{id}/confirm`.


## 2. Judgment mechanism

### Keyword-based judgment

Lightweight and fast primary judgment. Check if the response text contains a specific keyword. `ConsentChecker.check_keywords()` of `domain/tool/consent.py` is executed. Categories and keywords are hard-coded into modules as `CATEGORIES` dicts.

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

### AI based judgment

If you set the `use_ai` parameter of `consent_check` handler to `true`, `ConsentChecker.check_ai()` will perform AI-based judgment. Calls `AIClient.complete()` internally to classify whether the text falls into a sensitive category.

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

`ConsentChecker.check()` combines keyword judgment and AI judgment. Keyword judgment has many false positives but few omissions, and AI judgment has few false positives but is slow.


## 3. handler API

### defaults.tool.consent_check

Determines the text and returns whether consent is required.

**HTTP**: `POST /api/consent/check`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | `string` | Yes | Judgment target text |
| `use_ai` | `bool` | No | Use AI judgment (default `false`) |
| `model` | `string` | No | Model specification during AI judgment (default `"stub/default"`) |

**Return value**:

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

If `requires_consent` is `false`, `categories` is an empty array, `consent_id` is `null`, and `disclaimers` is an empty dict.

### defaults.tool.consent_confirm

Record user consent/refusal.

**HTTP**: `POST /api/consent/{id}/confirm`

**input_data**:

| Field | Type | Required | Description |
|---|---|---|---|
| `consent_id` | `string` | Yes | consent_id returned by `consent_check` (injected from path parameter in HTTP) |
| `accepted` | `bool` | Yes | User consent |

**Return value**:

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

The consent record is made permanent in `user_data/shared/consent_log/{consent_id}.json` (written in `ConsentChecker._persist()`).


## 4. How to integrate into chat.send (proposed)

Suggested integration as described in the docstring for `blocks/tool/consent_check.py`:

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


## 5. Display on front end

Consent pop-up is displayed in `emit_widget` or `emit_event("ui.popup.show", ...)`. Asset on the front end receives this event and draws a popup.

If Asset's JS receives `event.broadcast` and `event_type` is `"ui.popup.show"`, it will display a popup. When the user clicks the button, `event.broadcast` sends back the `"ui.popup.response"` event.

When expressing a popup as a widget:

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

The consent tool popup is drawn by the front end Asset. defaults provides a general-purpose communication mechanism called emit_event / wait_event / emit_widget and a handler for judgment and recording.
