<!-- docs-i18n-links:start -->
[EN](../../startup_capability_bridge.md) | [JP](../ja/startup_capability_bridge.md) | [KR](./startup_capability_bridge.md) | [CN](../zh-cn/startup_capability_bridge.md)
<!-- docs-i18n-links:end -->

# 스타트업 역량 브릿지

시작 프로필은 다음과 같은 Rumi 모드의 시작 시 정보 소스로 남아 있습니다.
데스크톱, CLI, 직장 프로필. 기능 프로필은 그래프 컴파일로 유지됩니다.
사전 설정. 시동 기능 브리지는 둘 중 하나를 교체하지 않고 연결합니다.
모델.

## 선택 필드

시작 프로필은 다음 필드를 사용하여 그래프 컴파일을 선택할 수 있습니다.

```json
{
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "launch_capability_graph": true,
  "last_runtime_profile_key": null
}
```

- `default_graph`는 컴파일할 Capability Graph를 선택합니다.
- `capability_profile_id`는 그래프 정책에 사용되는 기능 프로필을 선택하고,
  노드 설정 및 활성화 또는 비활성화된 노드.
- `launch_capability_graph`는 실행 시 그래프 컴파일 여부를 제어합니다.
- `last_runtime_profile_key`은 마지막으로 등록된 런타임 프로필 키를 기록합니다.
  성공적인 출시 컴파일 후.

`launch_capability_graph`을 생략하거나 `false`로 설정한 프로필은
이전 시작 실행 동작. 출시 결과에는 다음이 포함됩니다.
`capability_graph.skipped: true` 이유 있음
§루미§0§; 이것은 치명적이지 않습니다.

## 실행 동작

`launch_capability_graph`이 참일 때, `StartupProfileManager.launch_profile()`
시작 프로필을 시작한 다음 브리지를 호출합니다. 다리:

1. `default_graph` 및 `capability_profile_id`을 해결합니다.
2. defaultspack 기능 그래프 바인딩 핸들러를 등록합니다.
3. 승인된 기능 프로필, 기능 그래프 및 노드 정의를 로드합니다.
4. 일치하는 그래프 가장자리 대상에 `node_overrides`을 적용합니다.
5. 다음에 의해 추가된 노드만으로 실행 전용 기능 프로필 사본을 확장합니다.
`node_overrides`, 해당 팩이 시작 프로필에 나열되어 있는 경우에만 해당됩니다.
6. `CapabilityGraphCompiler`으로 그래프를 컴파일합니다.
7. 선택한 프런트엔드 표면 발사 대상을 추출합니다.
8. 컴파일된 런타임 프로필을 `InterfaceRegistry`에 등록합니다.
9. 실행 결과에 `capability_graph` 메타데이터를 반환합니다.

컴파일 실패는 소프트 실패입니다. 스타트업 출시는 여전히 성공하며,
실행 결과에는 `capability_graph.ok: false` 및 진단이 포함됩니다.

## 출시 결과

성공적인 그래프 컴파일은 다음과 같은 결과를 추가합니다.

```json
{
  "capability_graph": {
    "ok": true,
    "graph_id": "defaultspack.startup",
    "capability_profile_id": "defaultspack.startup",
    "runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup",
    "surface_launch_target": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "node_id": "frontendpack.web_surface"
    }
  }
}
```

소비자는 `runtime_profile_key`를 사용하여 등록된 런타임을 검색해야 합니다.
`InterfaceRegistry`의 프로필. 컴파일하는 기존 명시적 흐름 단계
그래프는 여전히 이전처럼 작동합니다.

`StartupProfileManager`도 `startup_surface_launch_target`를 활성 상태로 유지합니다.
생태계 메타데이터. 다시 시작한 후 `startup_surface_launcher`는 해당 대상을 읽습니다.
항상 시작 기본 팩을 실행하는 대신 `pack_id`을 실행합니다. 만약에
그래프 시작 대상이 없습니다. 시작 시작이 이전으로 돌아갑니다.
`startup_base_pack` 행동.

## 컴파일 미리보기

제어판은 별도의 입력 없이 정확한 시작 프로필 컴파일 경로를 미리 볼 수 있습니다.
시작 또는 저장 상태:

```http
POST /api/panel/startup/profiles/{id}/compile-preview
```

선택적 본문에는 초안 프로필이 포함될 수 있습니다.

```json
{
  "profile": {
    "profile_id": "custom",
    "packs": ["defaultspack", "frontendpack"],
    "node_overrides": {
      "frontend.surface": "frontendpack.web_surface"
    }
  }
}
```

응답은 실행 컴파일 결과를 반영하고 다음을 포함합니다.
`surface_launch_target`, 시작 프로필 편집기에서 프런트엔드를 표시할 수 있음
다시 시작하면 열리는 팩입니다. 미리보기 컴파일은
`InterfaceRegistry`의 런타임 프로필; 컴파일을 실행해도 여전히 등록됩니다.
런타임 프로필을 만들고 해당 키를 유지합니다.
