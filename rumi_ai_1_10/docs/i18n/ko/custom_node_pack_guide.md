<!-- docs-i18n-links:start -->
[EN](../../custom_node_pack_guide.md) | [JP](../ja/custom_node_pack_guide.md) | [KR](./custom_node_pack_guide.md) | [CN](../zh-cn/custom_node_pack_guide.md)
<!-- docs-i18n-links:end -->

# 사용자 정의 노드 팩 가이드

기능 그래프 팩은 핵심 런타임 코드를 변경하지 않고도 노드를 추가할 수 있습니다.

최소 레이아웃:

```text
my_pack/
  ecosystem.json
  capability_bindings.py
  nodes/search.node.json
  components/write_guard/node.json
  graphs/my_pack.graph.yaml
  profiles/my_pack.profile.yaml
```

독립형 노드 문서에는 `nodes/*.node.json`를 사용하세요. 사용
`components/*/node.json` 노드가 구성 요소 폴더에 속하는 경우. 는
런타임은 승인/해시 검증된 팩에 대해서만 이러한 명시적 위치를 로드합니다.

노드 바인딩은 다음과 같은 등록된 핸들러 ID를 참조해야 합니다.
§루미§0§. 노드에서 점으로 구분된 Python 가져오기 경로를 사용하지 마세요.
파일.
