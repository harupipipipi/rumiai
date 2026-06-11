<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](../ja/tool-prompt-conversion.md) | [KR](./tool-prompt-conversion.md) | [CN](../zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# 도구/프롬프트 참조

도구 및 프롬프트 정의는 일부 용어를 공유하지만
실행 경계.

- 도구 저작에는 `rumi_function` 또는 `capability` 외관이 사용됩니다.
- 신속한 작성으로 수동적인 텍스트 템플릿이 생성됩니다.
- 새로운 `execution.type="prompt"` 도구는 지원되지 않습니다.

## 메시지를 표시하는 도구

도구 정의는 문서, 예제 또는 생성을 위한 데이터로 읽을 수 있습니다.
프롬프트 변수. 이는 도구를 실행하지 않으며 어떤 도구도 부여하지 않습니다.
허가.

일반적인 용도:

```python
tool_schema = context["call_handler"]("defaults.tool.schema", {
    "tool_name": "file_read"
})
rendered = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "tool_usage_guide",
    "variables": {"tool_schema": tool_schema}
})
```

## 도구 프롬프트

작성 경로에서는 프롬프트에서 도구로의 변환이 비활성화되어 있습니다. 흐름이 필요한 경우
문자 메시지, 전화:

- `defaults.prompt.load_effective`
- `defaults.prompt.resolve_for_conversation`
- `defaults.prompt.render`

사용자에게 보이는 도구가 필요한 경우 일반 기능/능력 파사드를 정의하세요.
이는 적절하고 신뢰할 수 있는 함수를 호출합니다. 프롬프트 렌더링을 다음과 같이 노출하지 마십시오.
신속한 실행 도구.

## 왕복

보장된 도구/프롬프트 왕복은 없습니다. 도구 실행 메타데이터,
기능 부여, 승인 정책 및 프롬프트 소스 체인 메타데이터는
의미론이 다르므로 기본 시스템에 남아 있어야 합니다.
