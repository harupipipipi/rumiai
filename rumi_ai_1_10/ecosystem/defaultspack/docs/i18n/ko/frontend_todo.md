<!-- docs-i18n-links:start -->
[EN](../../frontend_todo.md) | [JP](../ja/frontend_todo.md) | [KR](./frontend_todo.md) | [CN](../zh-cn/frontend_todo.md)
<!-- docs-i18n-links:end -->

# defaultspack Frontend TODO

이 TODO 는 `defaultspack` standalone frontend 를 「본체가 전부 아는 UI」가 아니라 「registry 로 증축되는 shell」로 해 가기 위한 작업 메모입니다.

## Done

- `/api/ui/catalog` 추가
- `/api/ui/settings` 추가
- `/api/ui/conversations/{id}/preview` 추가
- right sidebar를 backend catalog 구동으로 변경
- settings modal 을 schema 구동으로 변경
- preview pane을 conversation preview API 구동으로 변경
- chat renderer에 code/image/widget/unknown fallback 추가

##Next

- `chat_renderers` metadata와 frontend renderer 구현을 완전히 분리
- widget type 당 전용 renderer registry를 `webapp/src/renderers/`로 잘라냅니다.
- preview source를 tool execution event와 stream event에서 직접 생성
- settings 저장을 section 별 validation 으로 한다
- frontend extension manifest 에 JSON schema 붙이기
- `RightSidebar`의 item icon을 manifest 지정 가능하게 한다
- custom renderer bundle의 lazy load 도입
- viewer 측 panel 에서도 같은 registry contract 를 쓸 수 있도록(듯이) 한다

## Nice To Have

- `user_data/shared/frontend_extensions/`용 scaffold CLI
- live reload 와 manifest watcher
- widget renderer error boundary
- preview pane 의 pin/tab/split
- settings 변경 내역
