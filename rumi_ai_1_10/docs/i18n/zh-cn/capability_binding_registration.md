<!-- docs-i18n-links:start -->
[EN](../../capability_binding_registration.md) | [JP](../ja/capability_binding_registration.md) | [KR](../ko/capability_binding_registration.md) | [CN](./capability_binding_registration.md)
<!-- docs-i18n-links:end -->

# 能力绑定注册

包通过显式清单元数据注册图形绑定处理程序：

```json
{
  "capability_bindings": {
    "register": "my_pack.capability_bindings.register_my_pack_binding_handlers"
  }
}
```

注册在图形编译之前运行，仅适用于发现的通过的包
批准/哈希验证。寄存器路径必须由 pack 模块拥有，
例如`my_pack.*`或`ecosystem.my_pack.*`。

寄存器函数接收`InterfaceRegistry`并且应该注册稳定
处理程序 ID：

```python
def register_my_pack_binding_handlers(interface_registry):
    interface_registry.register("my_pack:search.compile_node", compile_search_node)
    return {"registered": ["my_pack:search.compile_node"]}
```

然后编译时节点文件使用注册的处理程序 ID：

```json
{"bindings": {"compile": "my_pack:search.compile_node"}}
```
