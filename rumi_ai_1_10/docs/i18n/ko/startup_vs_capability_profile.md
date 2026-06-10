<!-- docs-i18n-links:start -->
[EN](../../startup_vs_capability_profile.md) | [JP](../ja/startup_vs_capability_profile.md) | [KR](./startup_vs_capability_profile.md) | [CN](../zh-cn/startup_vs_capability_profile.md)
<!-- docs-i18n-links:end -->

# 시작 프로필과 기능 프로필

시작 프로필은 시작 시 정보의 소스로 남아 있습니다. 팩을 선택하고,
슬롯, 시작 핸드오프 동작, 기능 그래프 컴파일 여부
출시시.

기능 프로필은 그래프/런타임 사전 설정입니다. 그래프 기본값을 선택합니다.
활성화 및 비활성화된 노드, 노드 설정 및 런타임 정책.

시작 프로필의 브리지 필드:

```json
{
  "launch_capability_graph": true,
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "last_runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup"
}
```

`launch_capability_graph`이 활성화되면 시작 시작 시 그래프를 컴파일하고
`InterfaceRegistry`에 런타임 프로필을 등록합니다. 흐름, 에이전트 및 패널
API는 `runtime_profile_key`를 컴파일된 런타임 프로필로 다시 확인할 수 있습니다.

시작 프로필 `node_overrides`은 컴파일 시작 전에 적용됩니다. 예를 들어,
`{"frontend.surface": "frontendpack.web_surface"}`는 그래프 가장자리를 다시 작성합니다.
`frontend.surface`를 피드하여 선택한 표면 노드가
컴파일된 런타임 프로필. 재정의 노드는 팩이 다음과 같은 경우에만 활성화됩니다.
시작 프로필 `packs` 목록에 포함되어 있습니다.

브리지는 활성 메타데이터에서 선택된 `surface_launch_target`를 유지하므로
재시작 핸드오프는 그래프 배선으로 선택된 프런트엔드를 열 수 있습니다. 발사하지 않고
대상에서 핸드오프를 다시 시작하면 시작 프로필 기본 팩이 계속 열립니다.
