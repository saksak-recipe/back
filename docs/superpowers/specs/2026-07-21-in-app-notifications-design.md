# 인앱 알림 (In-App Notifications)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

사용자가 **받은 그룹 초대**와 **유통기한 임박/만료**를 한곳(알림함)에서 볼 수 있게 한다.

이번 범위는 **백엔드 API + DB만** 포함한다. 푸시(FCM/APNs)·스케줄러는 포함하지 않는다.

## Decisions

| 항목 | 선택 |
|------|------|
| 채널 | 인앱 알림함만 (폴링). 푸시 없음 |
| 아키텍처 | 통합 `notifications` 테이블 + `domains/notification/` |
| 초대 알림 | 닉네임 초대(`GroupInvite`) 생성 시 수신자에게 1건. 초대 코드 공유 알림은 제외 |
| 유통기한 알림 | 알림 목록/미읽음 조회 시 재료 스캔 후 생성 (스케줄러 없음) |
| 유통기한 대상 | 개인 재료 → 본인, 그룹 재료 → 소속 멤버 전원 |
| 임박 기준 | 기존 `compute_status` / `SOON_WITHIN_DAYS = 3` 재사용 |
| 중복 방지 | 재료당 상태당 1회 (`soon` 1회 + `expired` 1회). `reference_key` UNIQUE |
| 읽음 | 단건 + 전체 읽음. 삭제 API 없음 |
| 초대 수락/거절 | 기존 group invite API 유지. 알림은 표시·읽음만 담당 |

## Out of Scope

- 프론트엔드 UI
- 푸시 알림 (FCM/APNs), device token
- 일/주기 배치 스케줄러 (cron/Celery)
- 초대 코드 공유를 “보낸 알림”으로 기록
- 알림 삭제 API, 알림 on/off 설정
- 초대 거절·재료 삭제 시 알림 자동 삭제
- WebSocket/SSE 실시간 전달
- 목록 페이지네이션 (MVP는 전량 최신순 반환)

## Problem

1. **초대:** `POST /groups/me/invites`로 닉네임 초대는 되지만, 수신 측 “알림” 표면이 없다.  
   받은 초대는 `GET /groups/invites`에만 있어, “보냈다는데 어디에 나타나지?” 혼란이 난다.  
   (초대 **코드**는 공유 문자열 + `POST /groups/join` 플로우이며, 이번 알림 대상이 아니다.)

2. **유통기한:** `ingredients`에 `status`(ok/soon/expired/unknown)는 있으나,  
   “임박/만료”를 알림함 항목으로 쌓는 파이프라인이 없다.

## Architecture

```
[초대 생성]
  POST /api/v1/groups/me/invites
       ↓
  GroupService.create_invite
       ↓ (같은 트랜잭션)
  NotificationService.create_group_invite_notification(invitee)
       → notifications row (type=group_invite, reference_key=group_invite:{invite_id})

[알림 조회 — 유통기한 sync + 목록]
  GET /api/v1/notifications
  GET /api/v1/notifications/unread-count
       ↓
  NotificationService.list / unread_count
    1. sync_expiry_notifications(user):
         - 개인 ingredients + 소속 group ingredients 로드
         - compute_status → soon / expired 인 것만
         - reference_key 없으면 insert (이미 있으면 skip)
    2. 해당 user_id 알림 조회 / 미읽음 count

[읽음]
  PATCH /api/v1/notifications/{id}/read
  POST  /api/v1/notifications/read-all
```

### Domain layout

기존 `shopping` / `group` 패턴을 따른다.

```
src/domains/notification/
  model.py
  schemas.py
  repository.py
  service.py

src/api/v1/endpoints/notification.py
alembic/versions/..._add_notifications.py
```

`api_router`에 notification 라우터를 등록한다.

## Data Model

### `notifications`

| 컬럼 | 타입 | 제약 / 설명 |
|------|------|-------------|
| `id` | UUID | PK |
| `user_id` | UUID FK → users | 수신자, index |
| `type` | enum/string | `group_invite` \| `expiry_soon` \| `expiry_expired` |
| `title` | string | 표시 제목 |
| `body` | string | 표시 본문 |
| `reference_key` | string | 중복 방지 키 |
| `payload` | JSON | 딥링크/부가 정보 |
| `is_read` | bool | default false |
| `created_at` | timestamptz | server default now() |

**Unique:** `(user_id, reference_key)`

**`reference_key` 규칙**

| type | key |
|------|-----|
| `group_invite` | `group_invite:{invite_id}` |
| `expiry_soon` | `expiry_soon:{ingredient_id}` |
| `expiry_expired` | `expiry_expired:{ingredient_id}` |

**`payload` 예시**

```json
// group_invite
{
  "invite_id": "...",
  "group_id": "...",
  "group_name": "...",
  "inviter_nickname": "..."
}

// expiry_soon / expiry_expired
{
  "ingredient_id": "...",
  "ingredient_name": "...",
  "expiration_date": "2026-07-24",
  "group_id": null
}
```

**표시 문구**

| type | title | body |
|------|-------|------|
| `group_invite` | `그룹 초대` | `"{inviter_nickname}님이 '{group_name}'에 초대했습니다"` |
| `expiry_soon` | `유통기한 임박` | `"{ingredient_name} 유통기한이 {expiration_date}까지입니다"` |
| `expiry_expired` | `유통기한 만료` | `"{ingredient_name} 유통기한이 지났습니다"` |

## API

Prefix: `/api/v1/notifications`  
인증: 기존 JWT 필수.

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 내 알림 목록 (최신순). 응답 전 expiry sync 수행 |
| GET | `/unread-count` | `{ "count": N }`. 응답 전 expiry sync 수행 |
| PATCH | `/{id}/read` | 단건 읽음. 본인 소유만 |
| POST | `/read-all` | 내 미읽음 전부 읽음 |

### Response shape (목록 항목)

```json
{
  "id": "...",
  "type": "group_invite",
  "title": "...",
  "body": "...",
  "payload": {},
  "is_read": false,
  "created_at": "..."
}
```

### Errors

| 상황 | 코드 | HTTP |
|------|------|------|
| 없는 id 또는 타인 알림 | `NOTIFICATION_NOT_FOUND` | 404 |

초대 생성 시 알림 insert 실패는 초대 트랜잭션과 함께 롤백한다 (부분 성공 없음).

## Flows (detail)

### Group invite

1. `GroupService`가 pending invite를 생성(또는 기존 pending 멱등 반환).
2. **새로 생성된 초대**에만 notification insert. 기존 pending 재반환이면 알림을 다시 만들지 않음 (`reference_key`로도 방어).
3. 수신자는 알림함에서 확인 후 `POST /groups/invites/{id}/accept|reject`로 처리.

### Expiry sync

1. 대상 재료: `user_id == me` 인 개인 재료 + `group_id in my_groups` 인 그룹 재료.
2. `compute_status(expiration_date)` 결과가 `soon` 또는 `expired`인 행만 후보.
3. 각 후보에 대해 `(user_id, reference_key)`가 없으면 insert.
4. `ok` / `unknown` 이거나 이미 키가 있으면 스킵.
5. 같은 재료가 soon이었다가 expired가 되면 **별도 키**이므로 두 번째 알림이 생성될 수 있다 (의도된 동작).

그룹 재료: sync를 호출한 유저뿐 아니라, **그 유저가 속한 그룹의 재료**에 대해 **그 유저 본인**에게만 알림을 만든다.  
(다른 멤버의 알림은 각 멤버가 자신의 `GET /notifications`를 호출할 때 각자 sync된다.)

## Testing

- 초대 생성 → 수신자에게 `group_invite` 1건, 초대자/제3자에게 없음
- 동일 pending 초대 재요청 → 알림 추가 생성 없음
- soon 재료 + `GET /notifications` → `expiry_soon` 1건; 재조회 시 추가 없음
- soon → expired(날짜 조작/고정) 후 재조회 → `expiry_expired` 추가 1건
- 그룹 재료 soon → 멤버 A가 조회 시 A에게만 생성; 멤버 B 조회 시 B에게도 생성
- 타인 `PATCH .../read` → 404
- `read-all` 후 `unread-count == 0`
- 초대 알림 payload에 `invite_id` 포함

## Migration

Alembic으로 `notifications` 테이블 + `(user_id, reference_key)` unique index 추가.  
`NOTIFICATION_NOT_FOUND`를 exception codes에 등록.
