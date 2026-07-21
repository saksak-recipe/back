# 가구 그룹 (Household Group) — 공유 냉장고·장보기

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 스펙:
- `2026-07-21-shopping-list-design.md`
- `2026-07-21-account-productization-design.md`

## Goal

가족·동거 시나리오를 위해 **유저당 활성 그룹 최대 1개**를 두고,  
멤버가 **냉장고(`ingredients`)와 장보기(`shopping_items`)** 를 함께 쓰게 한다.

- 개인 냉장고·장보기는 **그대로 유지**
- 원할 때 개인 항목을 골라 그룹에 **복사 또는 이동**으로 합칠 수 있다
- 초대는 **닉네임 검색**과 **초대 코드/링크** 모두 지원

이번 범위는 **백엔드 API + DB** 를 우선한다. (프론트는 별도)

## Decisions

| 항목 | 선택 |
|------|------|
| 공유 대상 | 냉장고 + 장보기 |
| 개인 데이터 | 유지 (그룹과 별도 공간) |
| 합치기 | 항목 선택 + `copy` \| `move` |
| 초대 | 닉네임 초대 + 초대 코드/링크 |
| 소속 | 유저당 활성 그룹 **최대 1개** |
| 데이터 모델 | 기존 테이블 + nullable `group_id` |
| 권한 | `owner` / `member` 두 역할만 (읽기전용 없음) |
| owner 나가기 | MVP는 **해산만** (소유권 이전 없음) |
| 그룹 아이템 이탈 시 | 그룹에 잔류 (개인으로 자동 환원 없음) |
| 해산 시 | 그룹 아이템 CASCADE 삭제 |
| 추천(RAG/AI) | MVP는 **개인 냉장고만** 계속 사용 |
| 아키텍처 | `domains/group/` + 기존 ingredient/shopping에 `group_id` 스코프 |

## Out of Scope

- 프론트엔드 UI
- 저장 레시피 공유
- 유저당 여러 그룹 / 멀티 스페이스
- 역할별 세밀 권한 (읽기전용, 초대 금지 등)
- 소유권 이전
- 실시간 동기화 (WebSocket)
- 그룹 채팅·멘션
- 그룹 냉장고 기반 레시피 추천
- Space 추상화(개인=1인 그룹) 리팩터

## Problem

닉네임은 가입·표시용 유니크 식별자로만 쓰이고,  
가족·룸메가 **같은 냉장고·장보기**를 쓸 제품 축이 없다.  
개인 데이터를 없애고 그룹만 쓰면 혼자 쓰는 UX가 깨지고,  
그룹을 아예 안 두면 동거 시나리오를 못 담는다.

## Architecture

```
[클라이언트]
  POST /groups                    생성
  POST /groups/me/invites         닉네임 초대
  POST /groups/join               코드 가입
  GET  /groups/me/ingredients     그룹 냉장고
  POST /groups/me/merge           개인 → 그룹 합치기
       │
       ▼
┌─────────────────┐
│  GroupService   │── GroupRepository (groups, members, invites)
│                 │── IngredientRepository (group_id 스코프)
│                 │── ShoppingRepository (group_id 스코프)
└─────────────────┘
       │
       ▼
 users ──< group_members >── groups
                │
 ingredients.group_id ──┐
 shopping_items.group_id ┘  NULL = 개인, NOT NULL = 그룹
```

개인 API (`/ingredients`, `/shopping-items`)는 **변경 없음** — 항상 `group_id IS NULL` 만 다룬다.  
그룹 API는 멤버십 확인 후 `group_id = me.group_id` 로 스코프한다.

### Domain layout

```
src/domains/group/
  model.py          # Group, GroupMember, GroupInvite
  repository.py
  service.py
  schemas.py
  router.py
  exceptions.py     # 필요 시. ErrorCode는 core에 그룹 코드 추가
```

재료/장보기 그룹 경로는 GroupService가 기존 repo/service에 `group_id`를 넘겨 재사용한다.  
로직 복제(그룹 전용 테이블)는 하지 않는다.

## Data Model

### `groups`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | UUID PK | |
| `name` | String(40) | 그룹 표시명 |
| `invite_code` | String(8) unique | 코드/링크 가입용 |
| `owner_id` | UUID FK → users | 생성자 |
| `created_at` | timestamptz | |

### `group_members`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `group_id` | UUID FK → groups ON DELETE CASCADE | |
| `user_id` | UUID FK → users ON DELETE CASCADE | **UNIQUE** (유저당 1그룹) |
| `role` | String / Enum | `owner` \| `member` |
| `joined_at` | timestamptz | |

PK: `(group_id, user_id)`.

### `group_invites`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | UUID PK | |
| `group_id` | UUID FK → groups ON DELETE CASCADE | |
| `inviter_id` | UUID FK → users | |
| `invitee_id` | UUID FK → users | |
| `status` | Enum | `pending` \| `accepted` \| `rejected` \| `cancelled` |
| `created_at` | timestamptz | |

동일 `(group_id, invitee_id)` 에 `pending` 이 있으면 재초대 시 **기존 pending 행을 그대로 반환**(멱등).

### 기존 테이블 변경

`ingredients` / `shopping_items`:

| 변경 | 설명 |
|------|------|
| `group_id` | nullable UUID FK → groups ON DELETE CASCADE |
| `user_id` | 유지 — 생성자(기여자). 개인 행은 소유자, 그룹 행은 작성자 |

**Unique / 중복 정책**

| 테이블 | 개인 (`group_id IS NULL`) | 그룹 (`group_id IS NOT NULL`) |
|--------|---------------------------|------------------------------|
| `shopping_items` | `(user_id, name)` partial unique (기존 UNIQUE를 교체) | `(group_id, name)` partial unique |
| `ingredients` | **이름 unique 없음** (기존과 동일, 중복 허용) | `(group_id, ingredient_name)` partial unique — 공유 냉장고는 이름당 1행 |

합치기 시 그룹에 동일 이름이 있으면 해당 항목 **skipped**.  
이름 비교: shopping=`name`, ingredient=`ingredient_name` (trim 후 비교; 대소문자 정책은 기존 도메인과 동일).

길이·검증 규칙은 기존과 동일.

## Permissions

| 동작 | owner | member |
|------|--------|--------|
| 그룹 재료/장보기 CRUD | ✅ | ✅ |
| 개인→그룹 merge | ✅ | ✅ |
| 닉네임 초대 / 코드 공유 | ✅ | ✅ |
| 초대 코드 재발급 | ✅ | ❌ |
| 멤버 추방 | ✅ | ❌ |
| 그룹명 변경 / 해산 | ✅ | ❌ |
| 나가기 | ❌ (해산만) | ✅ |

## API

Base: `/api/v1`. 인증 JWT 필수.

### 그룹 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/groups` | 생성. body: `{ "name" }`. 이미 소속 시 409. 생성자를 owner로 멤버십 insert, invite_code 발급 |
| `GET` | `/groups/me` | 내 그룹 + 멤버(nickname, role). 없으면 **404** |
| `PATCH` | `/groups/me` | `{ "name" }` owner만 |
| `DELETE` | `/groups/me` | 해산 owner만 — 멤버·초대·그룹 아이템 CASCADE |
| `POST` | `/groups/me/leave` | member만. owner면 400 |
| `DELETE` | `/groups/me/members/{user_id}` | 추방 owner만. 자기 자신·owner 추방 불가 |

### 초대 · 가입

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/groups/me/invites` | `{ "nickname" }` 대소문자 무시 매칭 |
| `GET` | `/groups/invites` | 내게 온 `pending` 목록 |
| `POST` | `/groups/invites/{id}/accept` | 수락. 이미 다른 그룹이면 409 |
| `POST` | `/groups/invites/{id}/reject` | 거절 |
| `POST` | `/groups/join` | `{ "invite_code" }` |
| `POST` | `/groups/me/rotate-code` | owner — 새 코드 발급, 이전 코드 무효 |

### 그룹 냉장고 · 장보기

개인 API와 대칭. 스코프만 `group_id` 고정.

- `GET` / `POST` / `PATCH` / `DELETE` `/groups/me/ingredients` (단건; 전체 삭제는 `DELETE /groups/me/ingredients`)
- `GET` / `POST` / `PATCH` / `DELETE` `/groups/me/shopping-items` (단건·다건·전체는 개인 shopping API와 동일 계약)
- `POST` `/groups/me/shopping-items/{id}/to-ingredient` — 그룹 장보기 → **그룹** 냉장고

요청/응답 스키마는 개인 API와 동일한 필드를 재사용한다.  
그룹 ingredient 단건 `POST`/`PATCH`에서 이름 충돌 시 **409**. 그룹 shopping 다건 추가는 개인과 같이 중복 **skip**.

### 합치기

```
POST /groups/me/merge
{
  "mode": "copy" | "move",
  "ingredients": [1, 2, 5],
  "shopping_items": [3, 4]
}
```

처리 순서:

1. 호출자 멤버십 확인
2. 각 id가 **본인 + `group_id IS NULL`** 인지 검증 (아니면 404)
3. 그룹에 동일 이름 있으면 해당 항목 **skipped**
4. `copy`: 그룹 행 insert, 개인 유지  
   `move`: 그룹 행 insert 후 개인 행 삭제
5. 응답 예:

```json
{
  "created_ingredients": [...],
  "created_shopping_items": [...],
  "skipped_ingredient_ids": [2],
  "skipped_shopping_item_ids": [],
  "deleted_ingredient_ids": [1, 5],
  "deleted_shopping_item_ids": [3, 4]
}
```

`copy` 모드면 `deleted_*` 는 빈 배열.

## Error cases

| 상황 | 코드 | ErrorCode (예시) |
|------|------|------------------|
| 이미 그룹 소속인데 생성/수락/join | 409 | `ALREADY_IN_GROUP` |
| 그룹 없음 (`GET /groups/me`) | 404 | `GROUP_NOT_FOUND` |
| 잘못된 초대 코드 | 404 | `INVITE_CODE_INVALID` |
| 자기 자신 초대 | 400 | `INVALID_INVITE` |
| 닉네임 유저 없음 | 404 | `USER_NOT_FOUND` |
| pending 중복 초대 | 200 — 기존 pending 반환 (멱등) | — |
| 비멤버 그룹 API | 404 | `GROUP_NOT_FOUND` |
| owner leave | 400 | `OWNER_CANNOT_LEAVE` |
| merge 대상 부적절 | 404 | |
| 권한 부족 (추방·해산 등) | 403 | `FORBIDDEN` |

닉네임 매칭은 기존과 같이 `lower()` 기준.  
탈퇴(soft-deleted) 유저는 계정 스펙과 동일하게 그룹 API·초대 대상에서 제외한다.

초대 수락 시점에만 “이미 다른 그룹”을 검사한다. (초대 생성 시점에는 상대가 그룹에 있어도 pending 초대는 가능 — 상대가 나간 뒤 수락할 수 있음.)

## Testing

- 그룹 생성 → 멤버십 1 + invite_code
- 두 번째 그룹 생성/수락/join → 409
- 닉네임 초대 → accept → 멤버 증가, invitee `user_id` unique 유지
- 코드 join / rotate-code 후 구코드 실패
- 그룹 ingredient/shopping CRUD·to-ingredient
- merge copy: 개인 유지 + 그룹 추가, 중복 이름 skipped
- merge move: 개인 삭제 + 그룹 추가
- member leave / owner dissolve / kick
- 개인 API가 그룹 행을 반환하지 않음 (회귀)

## Migration notes

1. `groups`, `group_members`, `group_invites` 생성
2. `ingredients.group_id`, `shopping_items.group_id` 추가
3. 기존 `shopping_items` UNIQUE → 개인/그룹 partial unique 교체; `ingredients`에 그룹 partial unique 추가
4. 기존 행은 모두 `group_id = NULL` (개인) — 데이터 백필 불필요
