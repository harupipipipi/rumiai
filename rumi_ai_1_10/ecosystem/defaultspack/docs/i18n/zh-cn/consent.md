<!-- docs-i18n-links:start -->
[EN](../../consent.md) | [JP](../ja/consent.md) | [KR](../ko/consent.md) | [CN](./consent.md)
<!-- docs-i18n-links:end -->

# 同意指南

## 1. 概念和目的

同意工具是一种当人工智能响应属于投资建议、医疗建议和法律建议等专业领域时向用户显示免责声明并请求同意的机制。

默认包提供了完整的同意机制（判断逻辑、处理程序、UI弹出协作、事件通信）。具体来说，以下文件放置在默认包中。

|文件|描述 |
|---|---|
| §鲁米§0§|判断处理者 (`defaults.tool.consent_check`) |
| §鲁米§0§|同意记录处理程序 (`defaults.tool.consent_confirm`) |
| §鲁米§0§| `ConsentChecker`类（判定逻辑/同意记录管理）|

`defaults.tool.consent_check` 和`defaults.tool.consent_confirm` 在`ecosystem.json` 的`tool` 部分的`provides` 中声明。可以使用路由`POST /api/consent/check`和`POST /api/consent/{id}/confirm`访问HTTP传输。


## 2.判断机制

### 基于关键词的判断

轻量且快速的初步判断。检查响应文本是否包含特定关键字。执行`domain/tool/consent.py` 的`ConsentChecker.check_keywords()`。类别和关键字作为 `CATEGORIES` 字典硬编码到模块中。

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

### 基于人工智能的判断

如果将`consent_check`处理程序的`use_ai`参数设置为`true`，`ConsentChecker.check_ai()`将执行基于AI的判断。内部调用`AIClient.complete()`来对文本是否属于敏感类别进行分类。

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

`ConsentChecker.check()`结合了关键词判断和人工智能判断。关键词判断误报多但漏报少，AI判断误报少但速度慢。


## 3. 处理程序 API

### defaults.tool.consent_check

确定文本并返回是否需要同意。

**HTTP**：`POST /api/consent/check`

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 |判断目标文本 |
| §鲁米§0§| §鲁米§1§ |没有 |使用AI判断（默认`false`）|
| §鲁米§0§| §鲁米§1§ |没有 | AI判断时的模型规范（默认`"stub/default"`）|

**返回值**：

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

如果`requires_consent`是`false`，`categories`是一个空数组，`consent_id`是`null`，`disclaimers`是一个空字典。

### defaults.tool.consent_confirm

记录用户同意/拒绝。

**HTTP**：`POST /api/consent/{id}/confirm`

**输入数据**：

|领域 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§| §鲁米§1§ |是的 | `consent_check`返回的consent_id（从HTTP中的路径参数注入）|
| §鲁米§0§| §鲁米§1§ |是的 |用户同意 |

**返回值**：

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

同意记录在`user_data/shared/consent_log/{consent_id}.json`中永久保存（写在`ConsentChecker._persist()`中）。


## 4. 如何集成到chat.send（建议）

建议的集成如`blocks/tool/consent_check.py`的文档字符串中所述：

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


## 5.前端显示

同意弹出窗口显示在`emit_widget`或`emit_event("ui.popup.show", ...)`中。前端的资源接收此事件并绘制一个弹出窗口。

如果Asset的JS收到`event.broadcast`并且`event_type`是`"ui.popup.show"`，它将显示一个弹出窗口。当用户单击按钮时，`event.broadcast` 发送回`"ui.popup.response"` 事件。

将弹出窗口表示为小部件时：

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

同意工具弹出窗口由前端 Asset 绘制。 defaults提供了一个名为emit_event/wait_event/emit_widget的通用通信机制以及用于判断和记录的处理程序。
