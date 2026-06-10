<!-- docs-i18n-links:start -->
[EN](../../port_standards.md) | [JP](../ja/port_standards.md) | [KR](./port_standards.md) | [CN](../zh-cn/port_standards.md)
<!-- docs-i18n-links:end -->

# 항만 표준

포트 표준은 두 포트를 연결할 수 있는지 여부를 결정하는 데 사용되는 문자열 식별자입니다.

의도적으로 일반적입니다. Core는 문자열을 비교하고 교차점을 계산합니다. 생태계는 자신의 도메인 의미를 담고 있습니다.

## 호환성 규칙

1단계 호환성:

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

## 예

```text
rumi.flow.start
rumi.ai.client
rumi.ai.provider
rumi.tool.bundle
rumi.agent.runtime
rumi.memory.store
rumi.prompt.bundle
rumi.ui.surface
rumi.cli.surface
pack.github.repository.v1
company.internal.docs.v1
```

## 네임스페이스 지침

```text
rumi.*       reserved for rumiai standard names
<pack_id>.* pack-owned standards
company.*   organization-owned standards
org.*       organization-owned standards
```

Core는 네임스페이스를 권한 경계로 처리하면 안 됩니다. 네임스페이스는 호환성 레이블일 뿐입니다.

## 다중 표준

포트는 여러 표준을 선언할 수 있습니다.

```json
{
  "id": "tools",
  "direction": "input",
  "standards": [
    "rumi.tool.bundle",
    "defaultspack.tool.bundle.v1",
    "openai.function_tools.compat"
  ]
}
```

이를 통해 하나의 포트는 도메인별 로직을 코어에 도입하지 않고도 여러 호환 가능한 기능 형태를 수용할 수 있습니다.

## 레거시 계약

`contract`은 레거시 입력 호환성만 제공됩니다.

```json
{
  "id": "tools",
  "direction": "input",
  "contract": "rumi.tool.bundle"
}
```

로더는 이를 다음과 같이 정규화합니다.

```json
{
  "id": "tools",
  "direction": "input",
  "standards": ["rumi.tool.bundle"]
}
```

새 파일은 `standards`을 사용해야 합니다.

## 다중 및 필수

입력 포트 검증:

- `multiple: false`는 최대 하나의 들어오는 에지를 허용합니다.
- `multiple: true`은 여러 개의 수신 에지를 허용합니다.
- `required: true`에는 적어도 하나의 들어오는 에지가 필요합니다.

출력 측 `multiple`은 1단계에서 엄격하게 적용되지 않습니다.

## 어댑터

어댑터는 1단계 이후까지 연기됩니다. 초기 검증은 정확한 표준 교차점만 사용합니다.

예약된 미래 형태:

```json
{
  "from": "rumi.cli.surface",
  "to": "rumi.ui.surface",
  "adapter": "defaultspack.frontend.adapt_cli_surface"
}
```
