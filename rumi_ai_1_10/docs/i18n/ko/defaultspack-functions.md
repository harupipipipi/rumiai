<!-- docs-i18n-links:start -->
[EN](../../defaultspack-functions.md) | [JP](../ja/defaultspack-functions.md) | [KR](./defaultspack-functions.md) | [CN](../zh-cn/defaultspack-functions.md)
<!-- docs-i18n-links:end -->

# Defaultspack 함수

Defaultspack은 기본 기능을 Rumi 함수로 노출합니다. HTTP 경로, AI 도구 및 Flow 노드는 기능을 안정적인 공개 운영 계약으로 취급해야 합니다.

## 함수 호출하기

알고 있는 경우 정식 정규 이름을 사용하세요.

```json
{
  "type": "function.call",
  "qualified_name": "defaultspack:ai_set_thinking_level",
  "args": {
    "scope": "profile",
    "profile_id": "openrouter/tencent/hy3-preview:free",
    "level": "high"
  }
}
```

함수는 `defaults.ai.set_thinking_level` 및 `defaultspack.ai.set_thinking_level`과 같은 어휘 별칭도 게시합니다. 정식 함수 id에는 점이 포함되지 않습니다. 별칭은 그렇습니다.

## 기능 대 도구

함수는 런타임/API 작업입니다. 도구는 AI 모델에 표시되는 외관일 뿐입니다.

```json
{
  "tool_id": "set_thinking_level",
  "name": "set_thinking_level",
  "execution": {
    "type": "rumi_function",
    "qualified_name": "defaultspack:ai_set_thinking_level"
  }
}
```

`ToolExecutor`은 공유 `CapabilityExecutor`를 통해 `rumi_function` 호출을 전송하므로 도구 사용과 팩 간 호출은 동일한 권한 경계를 통과합니다.

## 사고수준

모델 런타임 설정은 `ModelRuntimeSettingsService`의 소유입니다. 주요 진입점은 다음과 같습니다.

- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§

채팅 또는 AI 완료 매개변수에 `thinking_level`이 포함되지 않은 경우 defaultspack은 대화, 프로필, 전역 설정을 통해 서버 측의 유효 수준을 확인합니다.

## 모델 기능 및 라우팅

이제 모델 카탈로그는 프로필 인식 라우팅에서 사용되는 기능 메타데이터를 공개합니다.

- §루미§0§ / §루미§1§
- §루미§0§ / §루미§1§
- §루미§0§ / §루미§1§
- §루미§0§ / §루미§1§
- §루미§0§ / §루미§1§

기능 필드에는 `supports_vision`, `supports_tool_calling`, `supports_thinking`, `supports_fast`, `speed_tier`, `quality_tier`, `knowledge_level`, `knowledge_band` 및 역할 권장 사항이 포함됩니다. `knowledge_level`은 상대적인 루미아이 라우팅 점수이지 지능에 대한 절대적인 주장이 아닙니다.

비전 브리지 및 호환성 유틸리티 라우팅은 다음을 통해 사용할 수 있습니다.

- §루미§0§ / §루미§1§
- `defaultspack:agent_run_subagent` / `defaults.agent.run_subagent`(유틸리티 라우팅 또는 위임 실행에 대한 호환성 별칭)
- §루미§0§ / §루미§1§
- §루미§0§ / §루미§1§

## 흐름 예시

```yaml
- id: set_reasoning
  phase: prepare
  priority: 10
  type: function
  function: defaultspack.ai.set_thinking_level
  input:
    scope: turn
    level: high
  output: thinking_level_result
```

## 보안

읽기/목록/검색/상태 기능은 위험이 낮습니다. 채팅, AI 호출, 메모리 및 아티팩트 변형은 일반적으로 중간 위험입니다. 파일 쓰기, 터미널 실행, Git 푸시/커밋, 공급자 키 변경, 브라우저/컴퓨터 제어, 클립보드 쓰기 및 강제 팩 패치 작업은 위험이 높으며 `caller_requires`을 선언합니다.

팩 작성자는 호출자 주체가 보존되도록 `ToolExecutor` 또는 공유 `CapabilityExecutor`을 통해 defaultspack 함수를 호출해야 합니다. `domain.function_runtime.bridge.invoke_function()`는 HTTP 경로 어댑터 및 기타 defaultspack 소유 폴백에 대한 내부 `defaultspack` 주체를 기본값으로 사용합니다. 이를 직접 호출하는 외부 팩은 명시적인 `principal_id`를 전달해야 합니다.
