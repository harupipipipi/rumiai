<!-- docs-i18n-links:start -->
[EN](../../operations.md) | [JP](../ja/operations.md) | [KR](./operations.md) | [CN](../zh-cn/operations.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 운영 가이드

운영자를 위한 안내입니다. 전체 디자인은 [architecture.md](./architecture.md)를, 팩 개발은 [pack-development.md](./pack-development.md)을 참조하세요.

---

## 목차

1. [설정](#설정)
2. [시작](#시작)
3. [보안 모드](#보안-모드)
4. [HTTP API 개요](#http-api-개요)
5. [팩 승인 관리](#팩-승인-관리)
6. [네트워크 권한 관리](#network-privilege-management)
7. [기능 처리자 승인](#capability-handler-approval)
8. [역량 부여 관리](#역량-부여-관리)
9. [pip 종속 라이브러리 관리](#pip-dependency-library-management)
10. [비밀관리](#비밀-관리)
11. [Pack Import / Apply](#pack-import--apply)
12. [공유점포관리](#공유-매장-관리)
13. [Docker / Container management](#docker--container-management)
14. [플로우 실행](#흐름-실행)
15. [권한 관리](#권한-관리)
16. [UDS 소켓 설정](#uds-소켓-설정)
17. [감사기록 읽는 방법](#감사-로그를-읽는-방법)
18. [수출 보류 중](#내보내기-보류-중)
19. [인증 토큰](#인증-토큰)
20. [구조화된 로그 설정](#구조화된-로그-설정)
21. [더 이상 사용되지 않는 경고 수준 제어](#지원-중단-경고-수준-제어)
22. [건강검진 업무](#건강검진-운영)
23. [지표 확인](#측정항목-확인)
24. [팩 템플릿 생성(스캐폴드)](#팩-템플릿-생성스캐폴드)
25. [오류 코드 참조](#오류-코드-참조)
26. [환경변수 참고](#환경-변수-참조)
27. [문제 해결](#문제-해결)

---

## 설정

### 요구 사항

- 파이썬 3.10+
- Docker(프로덕션 환경에 필요)
- 힘내

### 설치

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10

# セットアップ（CLI）
python bootstrap.py --cli init

# または手動
pip install -r requirements.txt
```

### 설정 도구

설정 도구는 CLI와 웹이라는 두 가지 인터페이스를 제공합니다.

```bash
# CLI モード
python bootstrap.py --cli              # 対話メニュー
python bootstrap.py --cli check        # 環境チェック
python bootstrap.py --cli init         # 初期セットアップ
python bootstrap.py --cli doctor       # 診断
python bootstrap.py --cli recover      # リカバリー
python bootstrap.py --cli run          # アプリ起動

# Web モード
python bootstrap.py --web              # ブラウザ操作（デフォルトポート 8080）
python bootstrap.py --web --port 9000  # ポート指定
```

설정 도구는 다음 작업을 자동화합니다. Python/Git/Docker 확인, 가상 환경(.venv) 생성, 종속성 설치, user_data 디렉터리 초기화, 기본 팩 설치(선택 사항).

---

## 시작

```bash
# 本番環境（Docker 必須）
python app.py

# 開発環境（Docker 不要）
python app.py --permissive

# ヘッドレスモード
python app.py --headless

# ヘルスチェック実行
python app.py --health

# Pack バリデーション実行
python app.py --validate
```

`--health`은 상태 확인을 수행하고 JSON의 결과를 stdout으로 인쇄한 후 종료됩니다. 상태가 `"UP"`이면 종료 코드는 0이고, 그렇지 않은 경우 종료 코드는 1입니다. 내장 프로브에는 디스크(디스크 여유 공간) 및 writable_tmp(`/tmp` 쓰기 가능성)가 포함됩니다. CI/CD의 상태 확인 및 컨테이너 오케스트레이션에 사용할 수 있습니다.

`--validate`은 팩 유효성 검사를 실행하고 결과를 인쇄한 후 종료됩니다.

---

## 보안 모드

환경 변수 `RUMI_SECURITY_MODE`으로 설정합니다.

| 모드 | 도커 | 행동 |
|--------|--------|------|
| `strict`(기본값) | 필수 | Docker를 사용할 수 없는 경우 실행 거부 |
| `permissive` | 필요하지 않음 | 경고와 함께 호스트 실행 허용 |

```bash
# 本番
export RUMI_SECURITY_MODE=strict

# 開発
export RUMI_SECURITY_MODE=permissive
```

---

## HTTP API 개요

모든 엔드포인트에는 `Authorization: Bearer YOUR_TOKEN`이 필요합니다.

### 팩 관리

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/packs` | 모든 팩 목록 |
| 받기 | `/api/packs/pending` | 승인 대기 중인 팩 목록 |
| 받기 | `/api/packs/{pack_id}/status` | 팩 상태 가져오기 |
| 포스트 | `/api/packs/scan` | 팩 스캔 |
| 포스트 | `/api/packs/{pack_id}/approve` | 팩 승인 |
| 포스트 | `/api/packs/{pack_id}/reject` | 팩이 거부됨 |
| 포스트 | `/api/packs/import` | 팩 수입 |
| 포스트 | `/api/packs/apply` | 팩 적용 |
| 삭제 | `/api/packs/{pack_id}` | 팩 제거 |

### 네트워크 권한

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/network/list` | 모든 보조금 목록 |
| 포스트 | `/api/network/grant` | 네트워크 권한 부여 |
| 포스트 | `/api/network/revoke` | 네트워크 권한 취소 |
| 포스트 | `/api/network/check` | 액세스 확인 |

### 기능 처리기 후보

| 방법 | 경로 | 설명 |
|----------|------|------|
| 포스트 | `/api/capability/candidates/scan` | 후보자 스캔 |
| 받기 | `/api/capability/requests?status=pending` | 지원서 목록 |
| 포스트 | `/api/capability/requests/{key}/approve` | 승인(신뢰+복사) |
| 포스트 | `/api/capability/requests/{key}/reject` | 거부됨 |
| 받기 | `/api/capability/blocked` | 차단 목록 |
| 포스트 | `/api/capability/blocked/{key}/unblock` | 차단 해제 |

### 기능 부여

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/capability/grants?principal_id=xxx` | 보조금 목록 |
| 포스트 | `/api/capability/grants/grant` | 그랜트 |
| 포스트 | `/api/capability/grants/revoke` | 부여 취소 |
| 포스트 | `/api/capability/grants/batch` | 일괄 부여(최대 50개) |

### pip 종속 라이브러리

| 방법 | 경로 | 설명 |
|----------|------|------|
| 포스트 | `/api/pip/candidates/scan` | 후보자 스캔 |
| 받기 | `/api/pip/requests?status=pending` | 지원서 목록 |
| 포스트 | `/api/pip/requests/{key}/approve` | 승인 + 설치 |
| 포스트 | `/api/pip/requests/{key}/reject` | 거부됨 |
| 받기 | `/api/pip/blocked` | 차단 목록 |
| 포스트 | `/api/pip/blocked/{key}/unblock` | 차단 해제 |

### 비밀

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/secrets` | 키 목록(값이 마스크됨) |
| 포스트 | `/api/secrets/set` | 비밀 값 설정 |
| 포스트 | `/api/secrets/delete` | 비밀 값 삭제 |

### 흐름 실행

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/flows` | 등록된 흐름 목록 |
| 포스트 | `/api/flows/{flow_id}/run` | 흐름 실행 |

### 매장

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/stores` | 매장 목록 |
| 포스트 | `/api/stores/create` | 매장 만들기 |
| 받기 | `/api/stores/shared` | 공유스토어 목록 |
| 포스트 | `/api/stores/shared/approve` | 공유스토어 인증 |
| 포스트 | `/api/stores/shared/revoke` | 공유점포 취소 |

### 단위

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/units?store_id=xxx` | 단위 목록 |
| 포스트 | `/api/units/publish` | 게시 단위 |
| 포스트 | `/api/units/execute` | 실행 단위 |

### 권한

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/privileges` | 특전 목록 |
| 포스트 | `/api/privileges/{pack_id}/grant/{privilege_id}` | 특권부여 |
| 포스트 | `/api/privileges/{pack_id}/execute/{privilege_id}` | 특권 실행 |

### 원래 경로 팩

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/routes` | 등록된 경로 목록 |
| 포스트 | `/api/routes/reload` | 경로 테이블 다시 로드 |

### 도커/컨테이너

| 방법 | 경로 | 설명 |
|----------|------|------|
| 받기 | `/api/docker/status` | 도커 가용성 |
| 받기 | `/api/containers` | 컨테이너 목록 |
| 포스트 | `/api/containers/{pack_id}/start` | 컨테이너 시작 |
| 포스트 | `/api/containers/{pack_id}/stop` | 컨테이너 중지 |
| 삭제 | `/api/containers/{pack_id}` | 컨테이너 삭제 |

---

## 팩 승인 관리

### 승인 보류 확인

```bash
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 팩 승인

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 팩 거부

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'
```

### 재인증(수정된 상태로 포장)

파일 변경으로 인해 해시 불일치가 발생하면 `modified` 상태가 되고 자동으로 비활성화됩니다.

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 네트워크 권한 관리

### 그랜트 그랜트

```bash
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "my_pack",
    "allowed_domains": ["api.openai.com", "*.anthropic.com"],
    "allowed_ports": [443]
  }'
```

### 보조금 목록

```bash
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 접속 확인

```bash
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.openai.com", "port": 443}'
```

### 부여 취소

```bash
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'
```

---

## 기능 처리기 인증

> **참고**: core_pack에서 제공하는 기능(store/secrets/flow/communication/docker)은 이 후보 소개 워크플로를 거치지 않으며 커널 시작 시 자동으로 FunctionRegistry에 등록됩니다. 유저팩에 포함된 커스텀 기능 핸들러에는 아래와 같은 후보자 소개 워크플로우(스캔 → 승인 → 승인)가 적용됩니다.

기능 처리기는 2단계 작업을 통해 사용할 수 있게 됩니다.

1. **신뢰 등록**(핸들러 승인) : 스캔으로 검출된 후보를 승인하고, 핸들러 코드(sha256)를 신뢰할 수 있는 것으로 등록합니다.
2. **Grant**(허가 부여): 승인된 핸들러에게 Pack에 대한 권한을 부여합니다.

```
候補スキャン (scan)
    ↓
pending（承認待ち）
    ↓
approve → Trust 登録 + コピー + Registry reload
    ↓
Grant 付与（principal × permission）
    ↓
Pack が capability を使用可能
```

후보자는 스캔 → 보류 중 → 승인/거부 → 차단됨의 상태 전환을 따릅니다.

### 후보자 검색

```bash
curl -X POST http://localhost:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 승인 대기자 명단

```bash
curl "http://localhost:8765/api/capability/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 스캔 응답

후보 스캔 후 응답 예시:

```json
{
  "success": true,
  "data": {
    "scanned": 3,
    "new_candidates": 2,
    "candidates": [
      {
        "candidate_key": "my_pack:fs_read_v1:fs_read_handler:a1b2c3d4e5f6...",
        "pack_id": "my_pack",
        "slug": "fs_read_v1",
        "handler_id": "fs_read_handler",
        "permission_id": "fs.read",
        "sha256": "a1b2c3d4e5f6...",
        "status": "pending",
        "description": "ファイルシステム読み取り handler",
        "risk": "ファイルシステムへの読み取りアクセスを提供"
      }
    ]
  }
}
```

`candidate_key`의 형식은 `{pack_id}:{slug}:{handler_id}:{sha256}`입니다. sha256을 포함하여 handler.py의 내용이 변경되면 다른 후보로 처리됩니다.

### 후보자 승인

`candidate_key`에 포함된 `:`에는 URL 인코딩이 필요합니다.

```bash
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123..."

curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

레지스터 승인 신뢰(sha256 허용 목록) + `user_data/capabilities/handlers/`에 복사 + 레지스트리를 다시 로드합니다. 실제 사용을 위해서는 별도의 보조금이 필요합니다.

### 후보자 거부

```bash
curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なファイルシステムアクセス"}'
```

첫 번째와 두 번째 사용에는 `rejected`(1시간 재사용 대기시간)이 적용되며, 세 번째 사용에는 `blocked`가 적용됩니다.

### 차단 해제

```bash
curl -X POST "http://localhost:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## 역량 부여 관리

기능 처리기가 승인된 후 Pack이 실제로 기능을 사용하려면 Grant(주체 × 권한)가 필요합니다.

### 그랜트 그랜트

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 보조금 목록

```bash
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 부여 취소

```bash
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 일괄 부여(일괄)

한 번에 최대 50개의 보조금을 부여하세요. 최선을 다해 처리합니다(개별 실패로 인해 다른 승인이 방해되지 않음).

```bash
curl -X POST http://localhost:8765/api/capability/grants/batch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "grants": [
      {"principal_id": "pack_a", "permission_id": "store.get"},
      {"principal_id": "pack_a", "permission_id": "store.set"},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "config": {"allowed_keys": ["API_KEY"]}}
    ]
  }'
```

| 매개변수 | 필수 | 설명 |
|-----------|------|------|
| `grants` | ✅ | Grant 객체 배열(최대 50개) |
| `grants[].principal_id` | ✅ | 대상 팩 ID |
| `grants[].permission_id` | ✅ | 승인 ID |
| `grants[].config` | 선택사항 | 부여 설정(`allowed_keys` 등) |

예시 응답:

```json
{
  "success": true,
  "data": {
    "total": 3,
    "succeeded": 3,
    "failed": 0,
    "results": [
      {"principal_id": "pack_a", "permission_id": "store.get", "success": true},
      {"principal_id": "pack_a", "permission_id": "store.set", "success": true},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "success": true}
    ]
  }
}
```

### 전체적인 흐름

```
1. capability handler 候補をスキャン
   POST /api/capability/candidates/scan

2. 候補を承認（Trust 登録 + コピー）
   POST /api/capability/requests/{key}/approve

3. Grant を付与（principal × permission）
   POST /api/capability/grants/grant

4. Pack が capability を使用可能に
```

---

## pip 종속 라이브러리 관리

팩의 종속성을 스캔 → 승인 → pip 종속성 설치하는 워크플로입니다.

### 후보자 검색

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 승인 대기자 명단

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 승인(설치실행)

`candidate_key`에는 URL 인코딩이 필요합니다.

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123...', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

기본값은 휠만(`--only-binary=:all:`)입니다. 휠에 존재하지 않는 패키지가 포함된 경우 `"allow_sdist": true`을 지정하세요.

### 거부됨

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

첫 번째와 두 번째 사용에는 `rejected`(1시간 재사용 대기시간)이 적용되며, 세 번째 사용에는 `blocked`가 적용됩니다.

### 차단 해제

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

### 전제조건

팩이 승인된 상태인 것으로 가정됩니다. 승인되지 않은 팩의 종속 배포는 엄격 모드에서 거부됩니다.

---

## 비밀 관리

### 키 목록(값이 마스킹됨)

```bash
curl http://localhost:8765/api/secrets \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 비밀 값 설정

```bash
curl -X POST http://localhost:8765/api/secrets/set \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY", "value": "sk-..."}'
```

### 비밀값 삭제

```bash
curl -X POST http://localhost:8765/api/secrets/delete \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY"}'
```

비밀 값은 `user_data/secrets/`에 키 1개 = 파일 1개로 저장됩니다. API를 사용하여 다시 표시할 수 없습니다(설정 및 삭제만 가능). 비밀 값은 로그에 출력되지 않습니다.

### 암호화

비밀 값은 Fernet(AES-128-CBC + HMAC-SHA256)을 사용하여 암호화되어 저장됩니다. 암호화 키는 다음 우선순위에 따라 획득됩니다.

1. 환경 변수 `RUMI_SECRETS_KEY`(Base64로 인코딩된 Fernet 키)
2. `user_data/settings/.secrets_key` 파일
3. 위의 항목이 없으면 자동으로 키를 생성하여 `.secrets_key`에 저장합니다.

### 키 백업

암호화 키가 손실되면 기존 비밀 값을 해독할 수 없습니다. `user_data/settings/.secrets_key`을 안전한 장소에 백업해 주세요. 환경 변수 `RUMI_SECRETS_KEY`을 사용하여 외부에서 키를 관리하는 경우에도 백업이 필요합니다.

### 일반 텍스트 모드

`RUMI_SECRETS_ALLOW_PLAINTEXT`으로 암호화되지 않은 저장소를 제어할 수 있습니다.

| 가치 | 행동 |
|-----|------|
| `auto`(기본값) | 암호화 키가 있으면 암호화하고, 그렇지 않으면 일반 텍스트로 저장 |
| `true` | 항상 일반 텍스트로 저장 허용 |
| `false` | 암호화 키가 필요합니다. 키가 누락된 경우 비밀 값 저장 거부 |

`RUMI_SECRETS_ALLOW_PLAINTEXT=false`은 프로덕션 환경에 권장됩니다.

---

## 팩 가져오기/적용

### 가져오기(스테이징으로)

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

폴더 / `.zip` / `.rumipack`(zip 호환)을 지원합니다.

### 적용(스테이징부터 생태계까지 적용)

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

적용 중에 백업이 자동으로 생성됩니다. `pack_id` 및 `pack_identity`가 기존 팩과 일치하지 않으면 거부됩니다.

---

## 공유 매장 관리

팩 간에 스토어를 공유하기 위한 관리 API입니다. 공유 요청에는 수동 승인이 필요합니다(SharedStoreManager).

### 공유 매장 목록

```bash
curl http://localhost:8765/api/stores/shared \
  -H "Authorization: Bearer YOUR_TOKEN"
```

예시 응답:

```json
{
  "success": true,
  "data": {
    "shared_stores": [
      {
        "store_id": "shared_data",
        "owner_pack": "pack_a",
        "shared_with": ["pack_b", "pack_c"],
        "status": "approved",
        "approved_at": "2026-01-15T10:00:00Z"
      }
    ]
  }
}
```

### 공유스토어 인증

```bash
curl -X POST http://localhost:8765/api/stores/shared/approve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

| 매개변수 | 필수 | 설명 |
|-----------|------|------|
| `store_id` | ✅ | 공유할 매장ID |
| `owner_pack` | ✅ | 매장 소유 팩 ID |
| `target_pack` | ✅ | 공유할 팩 ID |

예시 응답:

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b",
    "status": "approved",
    "approved_at": "2026-01-15T10:00:00Z"
  }
}
```

### 공유스토어 취소

```bash
curl -X POST http://localhost:8765/api/stores/shared/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

| 매개변수 | 필수 | 설명 |
|-----------|------|------|
| `store_id` | ✅ | 대상 매장ID |
| `owner_pack` | ✅ | 매장 소유 팩 ID |
| `target_pack` | ✅ | 팩 ID 공유 취소 |

예시 응답:

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "target_pack": "pack_b",
    "status": "revoked"
  }
}
```

---

## 도커/컨테이너 관리

### 도커 상태 확인

```bash
curl http://localhost:8765/api/docker/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 컨테이너 목록

```bash
curl http://localhost:8765/api/containers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 컨테이너 시작/중지

```bash
# 起動
curl -X POST http://localhost:8765/api/containers/{pack_id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# 停止
curl -X POST http://localhost:8765/api/containers/{pack_id}/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 흐름 실행

### 흐름 목록 가져오기

```bash
curl http://localhost:8765/api/flows \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 흐름 실행

```bash
curl -X POST http://localhost:8765/api/flows/hello/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"name": "World"}, "timeout": 300}'
```

`inputs`은 Flow 입력 데이터(dict)이고, `timeout`은 최대 실행 시간(초, 기본값 300, 최대 600)입니다.

동시 실행 수는 `RUMI_MAX_CONCURRENT_FLOWS` 환경 변수(기본값 10)에 의해 제한됩니다. 제한에 도달하면 상태 코드 `429`이 반환됩니다.

### 성공적인 응답

```json
{
  "success": true,
  "flow_id": "hello",
  "result": {
    "greeting": {"message": "Hello, World!"}
  },
  "execution_time": 1.234
}
```

`result`은 흐름 출력을 저장합니다. 단, `_` 접두사로 시작하는 키(`_kernel_step_status` 등 내부 키)는 자동으로 제외됩니다.

### 오류 응답

```json
{
  "success": false,
  "error": "Flow not found: nonexistent_flow",
  "flow_id": "nonexistent_flow",
  "status_code": 404
}
```

| 상태_코드 | 설명 |
|-------------|------|
| `404` | 지정된 `flow_id`이 존재하지 않습니다 |
| `408` | 흐름 실행 시간이 초과되었습니다 |
| `429` | 동시 실행 제한(`RUMI_MAX_CONCURRENT_FLOWS`) 도달 |
| `500` | Flow를 실행하는 동안 예기치 않은 오류가 발생했습니다 |
| `503` | 시스템을 일시적으로 사용할 수 없습니다(시작 등) |

### 응답 크기 제한

`RUMI_MAX_RESPONSE_BYTES`(기본값 4MB)을 초과하면 흐름 실행 결과가 잘립니다. 잘림이 발생하면 응답은 `"truncated": true`로 표시됩니다.

---

## 권한 관리

Pack에서 권한 있는 작업(예: `pack.update`, `system.restart` 등)을 허용하고 실행하기 위한 API입니다. 이는 Capability Grant와는 독립적인 메커니즘으로, 호스트 측에서 위험한 작업을 명시적으로 허용하는 데 사용됩니다.

### 권한 목록

```bash
curl http://localhost:8765/api/privileges \
  -H "Authorization: Bearer YOUR_TOKEN"
```

예시 응답:

```json
{
  "success": true,
  "data": {
    "privileges": [
      {
        "privilege_id": "pack.update",
        "description": "Pack の更新適用を許可",
        "granted_packs": ["updater_pack"]
      },
      {
        "privilege_id": "system.diagnostics",
        "description": "システム診断情報の取得を許可",
        "granted_packs": []
      }
    ]
  }
}
```

### 권한 부여

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/grant/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

| 매개변수 | 필수 | 설명 |
|-----------|------|------|
| `pack_id`(경로 매개변수) | ✅ | 대상 팩 ID |
| `privilege_id`(경로 매개변수) | ✅ | 부여할 권한 ID |

예시 응답:

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "granted_at": "2026-02-15T10:00:00Z"
  }
}
```

### 특권 실행

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/execute/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"target_pack": "my_pack", "staging_id": "abc123"}}'
```

| 매개변수 | 필수 | 설명 |
|-----------|------|------|
| `pack_id`(경로 매개변수) | ✅ | 실행 소스 팩 ID |
| `privilege_id`(경로 매개변수) | ✅ | 실행할 권한 ID |
| `args`(본문) | 선택사항 | 권한 있는 작업에 전달될 인수 |

예시 응답:

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "result": {"status": "applied", "target_pack": "my_pack"},
    "executed_at": "2026-02-15T10:05:00Z"
  }
}
```

권한이 없는 팩의 실행 요청은 `403 Forbidden`으로 거부됩니다.

---

## UDS 소켓 설정

엄격 모드의 Pack 실행 컨테이너에서 UDS 소켓에 액세스하기 위한 설정입니다.

### 환경 변수

| 환경 변수 | 설명 | 기본값 |
|----------|------|-----------|
| `RUMI_EGRESS_SOCKET_GID` | 송신 소켓 GID | 없음 |
| `RUMI_CAPABILITY_SOCKET_GID` | 기능 소켓 GID | 없음 |
| `RUMI_EGRESS_SOCKET_MODE` | 송신 소켓 권한 | `0660` |
| `RUMI_CAPABILITY_SOCKET_MODE` | 기능 소켓 권한 | `0660` |
| `RUMI_EGRESS_SOCK_DIR` | 송신 소켓 기본 디렉터리 | `/run/rumi/egress/packs` |
| `RUMI_CAPABILITY_SOCK_DIR` | 기능 소켓 기본 디렉터리 | `/run/rumi/capability/principals` |

### 구성 단계

1. 전용 GID를 결정합니다(예: 1099)
2. 환경 변수를 설정합니다.
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3. 소켓 생성 시 지정된 GID의 그룹이 자동으로 설정됩니다.
4. `--group-add=1099`는 `docker run` 시 자동 부여됩니다.

GID가 설정되지 않으면 컨테이너(nobody:65534)에서 소켓에 액세스할 수 없습니다.

---

## 감사 로그를 읽는 방법

감사 로그는 `user_data/audit/`에 `{category}_{YYYY-MM-DD}.jsonl` 형식으로 저장됩니다.

### 기본 읽기

```bash
# 今日のネットワークログ
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 拒否されたリクエスト
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.success == false)'

# 権限操作のログ
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq .

# lib 実行ログ
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# capability grant 操作
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq 'select(.details.permission_type == "capability_grant")'

# principal_id 上書き警告
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.action == "principal_id_overridden")'

# 共有辞書の操作履歴
cat user_data/settings/shared_dict/journal.jsonl | jq .

# 循環検出された共有辞書操作
cat user_data/settings/shared_dict/journal.jsonl | jq 'select(.result == "cycle_detected")'
```

### 카테고리 목록

| 카테고리 | 내용 |
|----------|------|
| `flow_execution` | 흐름 실행 |
| `modifier_application` | 수정자 적용 |
| `python_file_call` | 실행 차단 |
| `approval` | 팩 승인작업 |
| `permission` | 권한 운영 |
| `network` | 네트워크 통신 |
| `security` | 보안 이벤트 |
| `system` | 시스템 이벤트 |

---

## 내보내기 보류 중

`user_data/pending/summary.json`은 시작 시 자동으로 생성됩니다. 외부 도구는 이 파일을 읽는 것만으로도 승인 상태를 이해할 수 있습니다.

```bash
cat user_data/pending/summary.json | jq .
```

---

## 인증 토큰

모든 HTTP API 엔드포인트에는 `Authorization: Bearer YOUR_TOKEN` 헤더를 사용한 인증이 필요합니다. 토큰은 HMAC 키에서 파생됩니다.

### 토큰 확인

토큰은 시작 시 콘솔에 표시됩니다. 또한 HMAC 키 파일(`user_data/settings/.hmac_key`)에서 파생되므로 동일한 키 파일이 존재하는 한 토큰은 변경할 수 없습니다.

키 파일이 없으면 처음 시작할 때 자동으로 생성됩니다.

### 토큰 순환

HMAC 키를 순환(재생성)하여 토큰이 변경됩니다.

```bash
# HMAC 鍵ローテーションを有効にして起動
export RUMI_HMAC_ROTATE=true
python app.py
```

`RUMI_HMAC_ROTATE=true`을 설정하면 다음 부팅 시 기존 HMAC 키가 새 키로 대체됩니다. 교체 후에는 이전 토큰이 더 이상 유효하지 않으므로 모든 API 클라이언트의 구성을 업데이트하시기 바랍니다.

회전은 한 번만 수행됩니다. 순환이 완료되면 `RUMI_HMAC_ROTATE`를 `false`로 반환하거나 환경 변수를 삭제합니다.

---

## 구조화된 로그 설정

### 환경 변수

| 환경 변수 | 설명 | 기본값 |
|----------|------|-----------|
| `RUMI_LOG_LEVEL` | 로그 수준. 디버그/정보/경고/오류/위험 | `INFO` |
| `RUMI_LOG_FORMAT` | 출력 형식. JSON/텍스트 | `json` |

### 설정 방법

```bash
export RUMI_LOG_LEVEL=DEBUG
export RUMI_LOG_FORMAT=text
python app.py --headless
```

`configure_logging()`은 app.py가 시작될 때 자동으로 호출되고 `rumi.*` 네임스페이스의 로거에 적용됩니다.

### JSON 형식 출력 예시

```json
{"timestamp": "2026-02-24T12:00:00.000000Z", "level": "INFO", "module": "rumi.kernel.core", "message": "Flow loaded", "correlation_id": "req-123"}
```

### 텍스트 형식 출력 예

```
2026-02-24T12:00:00.000000Z [INFO] rumi.kernel.core - Flow loaded (correlation_id=req-123)
```

---

## 지원 중단 경고 수준 제어

### 환경 변수

| 환경 변수 | 설명 | 기본값 |
|----------|------|-----------|
| `RUMI_DEPRECATION_LEVEL` | 더 이상 사용되지 않는 API 호출 시 동작 | `warn` |

| 가치 | 행동 |
|-----|------|
| `warn` | `DeprecationWarning` 출판 `warnings.warn` |
| `error` | `DeprecationWarning` 예외 발생 |
| `silent` | 아무것도 하지 않음 |
| `log` | `logging`에서 경고 수준 출력 |

### 설정 예

```bash
export RUMI_DEPRECATION_LEVEL=error
python app.py --headless
```

---

## 헬스체크 작업

### CLI로 확인

```bash
python app.py --health
```

상태가 `"UP"`이면 종료 코드 0이 반환되고, 그렇지 않으면 종료 코드 1이 반환됩니다.

### 프로그래밍 방식 사용

```python
from core_runtime.health import get_health_checker, probe_disk_space
checker = get_health_checker()
checker.register_probe("disk", lambda: probe_disk_space("/"))
result = checker.aggregate_health()
# result["status"]: "UP" / "DOWN" / "DEGRADED" / "UNKNOWN"
```

### 사용자 정의 프로브 추가

```python
from core_runtime.health import HealthStatus
def my_probe() -> HealthStatus:
    # カスタムチェックロジック
    return HealthStatus.UP
checker.register_probe("my_service", my_probe)
```

---

## 측정항목 확인

### 스냅샷 찍기

```python
from core_runtime.metrics import get_metrics_collector
collector = get_metrics_collector()
snapshot = collector.snapshot()
# snapshot["counters"], snapshot["gauges"], snapshot["histograms"]
```

### 자동으로 수집된 측정항목

Wave 15에서는 다음 지표가 자동으로 수집됩니다.

| 측정항목 이름 | 유형 | 설명 | 라벨 |
|-------------|------|------|--------|
| `flow.step.success` | 카운터 | 단계 실행 성공 횟수 | 핸들러 |
| `flow.step.error` | 카운터 | 단계 실행 실패 횟수 | 핸들러 |
| `flow.execution.complete` | 카운터 | 흐름 실행 완료 횟수 | 흐름_ID |
| `docker.available` | 게이지 | 도커 가용성 | — |
| `container.start.success` | 카운터 | 컨테이너 시작 성공 횟수 | — |
| `container.start.failed` | 카운터 | 컨테이너 시작 실패 횟수 | — |
| `flows.registered` | 게이지 | 등록된 흐름 수 | — |
| `python_file_call.duration_ms` | 히스토그램 | Python 파일 실행 시간(ms) | — |

---

## 팩 템플릿 생성(스캐폴드)

새로운 Pack 템플릿을 생성하는 명령줄 도구입니다.

### 사용방법

```bash
python -m core_runtime.pack_scaffold <pack_id> [--template TEMPLATE] [--output-dir DIR]
```

### 템플릿 목록

| 템플릿 | 설명 |
|-------------|------|
| `minimal`(기본값) | 최소 구성(ecosystem.json + run.py) |
| `capability` | 기능 처리기 포함 |
| `flow` | 흐름 정의 포함 |
| `full` | 모두 포함됨 |

### 실행 예

```bash
python -m core_runtime.pack_scaffold my-pack --template full --output-dir ecosystem/
```

---

## 오류 코드 참조

오류 코드는 `RUMI-{CATEGORY}-{3_DIGIT_NUMBER}` 형식으로 구성됩니다. 각 오류에는 제안 사항이 포함됩니다.

### 카테고리 목록

| 카테고리 | 설명 | 예 |
|---------|------|-----|
| `AUTH` | 인증/권한 부여 | `RUMI-AUTH-001`(토큰이 유효하지 않음) |
| `NET` | 네트워크 | `RUMI-NET-001`(연결 실패) |
| `FLOW` | 흐름 실행 | `RUMI-FLOW-001`(흐름이 발견되지 않음) |
| `PACK` | 팩 관리 | `RUMI-PACK-001`(pack_id가 잘못됨) |
| `CAP` | 능력 | `RUMI-CAP-001`(능력이 발견되지 않음) |
| `VAL` | 검증 | `RUMI-VAL-001`(빈 값) |
| `SYS` | 시스템 일반 | `RUMI-SYS-001`(내부 오류) |

---

## 환경 변수 참조

Rumi AI OS 동작을 제어하는 환경 변수 목록입니다.

| 변수 이름 | 기본값 | 설명 |
|--------|-----------|------|
| `RUMI_SECURITY_MODE` | `strict` | 보안 모드. `strict`(Docker 필요) 또는 `permissive`(Docker 필요하지 않음, 개발용) |
| `RUMI_LOG_LEVEL` | `INFO` | 로그 수준. `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `RUMI_LOG_FORMAT` | `json` | 로그 출력 형식. `json`(구조화된 JSON) 또는 `text`(사람 텍스트) |
| `RUMI_DEPRECATION_LEVEL` | `warn` | 더 이상 사용되지 않는 API를 호출할 때의 동작입니다. `warn` / `error` / `silent` / `log` |
| `RUMI_SECRETS_KEY` | 없음 | 비밀의 Fernet 암호화에 사용되는 키(Base64 인코딩) 설정되지 않은 경우 `.secrets_key` 파일로 대체하거나 자동 생성 |
| `RUMI_SECRETS_ALLOW_PLAINTEXT` | `auto` | 일반 텍스트 비밀을 허용합니다. `auto`(암호화 키가 없는 경우 일반 텍스트로 저장), `true`(항상 일반 텍스트 허용), `false`(암호화 키 필요, 키 없이 저장 거부) |
| `RUMI_MAX_RESPONSE_BYTES` | `4194304`(4MB) | Flow 실행 결과 및 Egress Proxy 응답의 최대 크기(바이트) |
| `RUMI_MAX_CONCURRENT_FLOWS` | `10` | 동시 Flow 실행 횟수 상한 |
| `RUMI_MAX_REQUEST_BODY_BYTES` | `1048576`(1MB) | HTTP API에서 허용하는 요청 본문의 최대 크기(바이트) |
| `RUMI_API_BIND_ADDRESS` | `127.0.0.1` | API 서버 바인드 주소. 외부에 게시하는 경우 `0.0.0.0`로 변경(권장하지 않음) |
| `RUMI_CORS_ORIGINS` | 없음 | 쉼표로 구분된 CORS 허용 원본 목록(예: `http://localhost:3000,http://localhost:8080`) |
| `RUMI_HMAC_ROTATE` | `false` | `true`로 설정하면 다음 시작 시 HMAC 키가 순환됩니다 |
| `RUMI_DIAGNOSTICS_VERBOSE` | `false` | 진단 로그에 자세한 정보를 포함하려면 `true`로 설정 |
| `RUMI_EGRESS_SOCKET_GID` | 없음 | 송신 UDS 소켓의 GID입니다. | `RUMI_EGRESS_SOCKET_GID` | 없음 | 송신 UDS 소켓의 GID입니다. 엄격 모드의 컨테이너에서 소켓에 액세스하는 데 필요 |
| `RUMI_CAPABILITY_SOCKET_GID` | 없음 | 기능 UDS 소켓 GID. 엄격 모드의 컨테이너에서 소켓에 액세스하는 데 필요 |
| `RUMI_EGRESS_SOCKET_MODE` | `0660` | 송신 UDS 소켓 권한 |
| `RUMI_CAPABILITY_SOCKET_MODE` | `0660` | 기능 UDS 소켓 권한 |
| `RUMI_EGRESS_SOCK_DIR` | `/run/rumi/egress/packs` | 송신 UDS 소켓 기본 디렉터리 |
| `RUMI_CAPABILITY_SOCK_DIR` | `/run/rumi/capability/principals` | 기능 UDS 소켓 기본 디렉터리 |
| `RUMI_SECRET_GET_RATE_LIMIT` | `60` | `secrets.get` 속도 제한(회/분/팩, 슬라이딩 윈도우) |
| `RUMI_LOCAL_PACK_MODE` | `off` | local_pack 호환 모드. `off`(비활성화) 또는 `require_approval`(승인이 필요한 경우 유효, 권장되지 않음) |

---

## 문제 해결

### 도커를 사용할 수 없음

```
Error: Docker is required but not available
```

개발 시에는 `--permissive` 플래그를 사용하거나 환경변수 `RUMI_SECURITY_MODE=permissive`을 설정하시기 바랍니다.

### 팩이 승인되지 않음

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 팩 수정됨

파일 변경으로 인해 해시 불일치가 발생하면 자동으로 비활성화됩니다. 다시 승인해 주세요.

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 네트워크 액세스가 거부되었습니다.

```bash
# Grant 状態を確認
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# 権限を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'
```

### 기능을 사용할 수 없습니다

승인(신뢰+복사)만 사용할 수는 없습니다. 그랜트가 필요합니다.

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### SHA-256 불일치로 인해 기능 처리기 승인 실패

검사 후 handler.py의 내용이 변경되었습니다. 스캔을 다시 실행하고 새 Candidate_key로 보류 중인 항목을 다시 생성한 후 다시 승인해 주세요.

### pip 종속성 설치가 거부되었습니다.

1. 팩이 승인되었는지 확인합니다(엄격 모드에서 필요).
2. `requirements.lock` 구문이 올바른지 확인하세요(`NAME==VERSION`만 허용됨).
3. `index_url`이 https를 사용하는 외부 호스트인지 확인하세요.

### UDS 소켓에 액세스할 수 없습니다.

1. `RUMI_EGRESS_SOCKET_GID` / `RUMI_CAPABILITY_SOCKET_GID`이 설정되어 있는지 확인하세요.
2. 소켓 파일 권한 확인: `ls -la /run/rumi/egress/packs/`
3. 최후의 수단: `RUMI_EGRESS_SOCKET_MODE=0666`(권장하지 않음)

### 팩 업데이트 시 신원 오류

```
Error: pack_identity mismatch
```

`pack_identity`이 다른 팩으로 기존 팩을 덮어쓰려고 합니다. 의도적인 교체인 경우 기존 팩을 먼저 삭제한 후 다시 적용해 보세요.

### lib가 실행되지 않습니다

```bash
# 監査ログで確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# 記録を確認（Kernel ハンドラ kernel:lib.list_records）
# 記録をクリアして再実行を強制（Kernel ハンドラ kernel:lib.clear_record）
```

### 수정자가 적용되지 않았습니다.

1. `target_flow_id`이 맞는지 확인하세요
2. 대상 Flow에 `phase`이 존재하는지 확인
3. `requires`의 조건이 충족되는지 확인
4. 감사 로그를 확인하세요.
   ```bash
   cat user_data/audit/modifier_application_$(date +%Y-%m-%d).jsonl | jq .
   ```

### 이전 디렉터리 경고

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

`flow/` 또는 `ecosystem/flows/`에서 `flows/`, `user_data/shared/flows/` 또는 `flows/`로 팩으로 마이그레이션하세요.
