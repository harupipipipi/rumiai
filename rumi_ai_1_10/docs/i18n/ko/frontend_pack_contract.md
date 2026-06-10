<!-- docs-i18n-links:start -->
[EN](../../frontend_pack_contract.md) | [JP](../ja/frontend_pack_contract.md) | [KR](./frontend_pack_contract.md) | [CN](../zh-cn/frontend_pack_contract.md)
<!-- docs-i18n-links:end -->

# 프론트엔드 팩 계약

프런트엔드 팩은 다음을 노출하여 시작 기능 그래프 실행에 참여할 수 있습니다.
`rumi.surface` 출력과 `metadata.launch`이 있는 노드.

필수:

- 승인된 팩
- 시작 프로필에는 `packs`에 팩이 포함되어 있습니다.
- `standards: ["rumi.surface"]`이 포함된 노드 포트
- 노드 메타데이터 `pack_id`
- 노드 메타데이터 `launch.kind: desktop_app`
- 노드 팩 ID와 일치하는 노드 메타데이터 `launch.pack_id`
- `ecosystem.json` `desktop_app.command` 데스크탑 앱 관리자가 실행할 수 있도록 합니다.

예시 노드:

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "frontendpack.web_surface",
      "kind": "ecosystem.surface",
      "display_name": {
        "en": "Frontendpack Web Surface",
        "ja": "Frontendpack Web Surface"
      },
      "ports": [
        {
          "id": "surface",
          "direction": "output",
          "standards": ["rumi.surface"],
          "multiple": true
        }
      ],
      "metadata": {
        "pack_id": "frontendpack",
        "component_type": "frontend",
        "component_id": "web",
        "category": "surface",
        "launch": {
          "kind": "desktop_app",
          "pack_id": "frontendpack",
          "surface": "browser",
          "default": true,
          "env": {
            "FRONTENDPACK_SURFACE": "web"
          }
        }
      }
    }
  ]
}
```

예 `ecosystem.json` 데스크톱 앱 섹션:

```json
{
  "pack_id": "frontendpack",
  "desktop_app": {
    "command": "python desktop_app.py",
    "working_dir": "",
    "env": {
      "FRONTENDPACK_PORT": "8770"
    },
    "window": {
      "title": "Frontendpack",
      "width": 1280,
      "height": 800
    }
  }
}
```

시작 프로필이 이 노드에 대해 `frontend.surface`을 재정의하면 그래프 컴파일이 수행됩니다.
`runtime_profile.launch.surface`에 표준 대상을 저장하고 활성 상태입니다.
메타데이터 저장소 `startup_surface_launch_target`. 재시작 후 시동
표면 발사기는 기본 팩 대신 `frontendpack`을 엽니다.

실행 대상은 의도적으로 팩 로컬입니다. `frontendpack`의 노드는 다음을 수행할 수 없습니다.
`launch.pack_id: otherpack` 또는 `principal_id: otherpack` 청구; 컴파일하고
시작 시작 정규화는 해당 대상을 거부하고 시작으로 돌아갑니다.
필요한 경우 프로필 베이스 팩.
