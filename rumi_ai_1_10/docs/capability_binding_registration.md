<!-- docs-i18n-links:start -->
[EN](./capability_binding_registration.md) | [JP](./i18n/ja/capability_binding_registration.md) | [KR](./i18n/ko/capability_binding_registration.md) | [CN](./i18n/zh-cn/capability_binding_registration.md)
<!-- docs-i18n-links:end -->

# Capability Binding Registration

Packs register graph binding handlers through explicit manifest metadata:

```json
{
  "capability_bindings": {
    "register": "my_pack.capability_bindings.register_my_pack_binding_handlers"
  }
}
```

Registration runs before graph compile, only for discovered packs that pass
approval/hash verification. The register path must be owned by the pack module,
for example `my_pack.*` or `ecosystem.my_pack.*`.

The register function receives `InterfaceRegistry` and should register stable
handler ids:

```python
def register_my_pack_binding_handlers(interface_registry):
    interface_registry.register("my_pack:search.compile_node", compile_search_node)
    return {"registered": ["my_pack:search.compile_node"]}
```

Compile-time node files then use the registered handler id:

```json
{"bindings": {"compile": "my_pack:search.compile_node"}}
```
