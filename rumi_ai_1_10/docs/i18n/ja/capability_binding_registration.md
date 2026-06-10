<!-- docs-i18n-links:start -->
[EN](../../capability_binding_registration.md) | [JP](./capability_binding_registration.md) | [KR](../ko/capability_binding_registration.md) | [CN](../zh-cn/capability_binding_registration.md)
<!-- docs-i18n-links:end -->

# 機能バインディングの登録

パックは、明示的なマニフェスト メタデータを通じてグラフ バインディング ハンドラーを登録します。

```json
{
  "capability_bindings": {
    "register": "my_pack.capability_bindings.register_my_pack_binding_handlers"
  }
}
```

登録は、合格した検出されたパックに対してのみ、グラフのコンパイル前に実行されます。
承認/ハッシュ検証。レジスタ パスはパック モジュールによって所有されている必要があります。
たとえば、`my_pack.*` または `ecosystem.my_pack.*` などです。

レジスタ関数は`InterfaceRegistry`を受け取り、安定して登録する必要があります
ハンドラーID:

```python
def register_my_pack_binding_handlers(interface_registry):
    interface_registry.register("my_pack:search.compile_node", compile_search_node)
    return {"registered": ["my_pack:search.compile_node"]}
```

コンパイル時のノード ファイルは、登録されたハンドラー ID を使用します。

```json
{"bindings": {"compile": "my_pack:search.compile_node"}}
```
