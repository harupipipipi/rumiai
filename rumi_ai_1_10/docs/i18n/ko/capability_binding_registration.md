<!-- docs-i18n-links:start -->
[EN](../../capability_binding_registration.md) | [JP](../ja/capability_binding_registration.md) | [KR](./capability_binding_registration.md) | [CN](../zh-cn/capability_binding_registration.md)
<!-- docs-i18n-links:end -->

# 기능 바인딩 등록

명시적 매니페스트 메타데이터를 통해 레지스터 그래프 바인딩 핸들러를 팩합니다.

```json
{
  "capability_bindings": {
    "register": "my_pack.capability_bindings.register_my_pack_binding_handlers"
  }
}
```

등록은 그래프 컴파일 전에 실행되며, 통과한 검색된 팩에 대해서만 실행됩니다.
승인/해시 검증. 레지스터 경로는 pack 모듈이 소유해야 합니다.
예를 들어 `my_pack.*` 또는 `ecosystem.my_pack.*`입니다.

등록 기능은 `InterfaceRegistry`을 수신하고 안정적으로 등록해야 합니다.
핸들러 ID:

```python
def register_my_pack_binding_handlers(interface_registry):
    interface_registry.register("my_pack:search.compile_node", compile_search_node)
    return {"registered": ["my_pack:search.compile_node"]}
```

그런 다음 컴파일 타임 노드 파일은 등록된 핸들러 ID를 사용합니다.

```json
{"bindings": {"compile": "my_pack:search.compile_node"}}
```
