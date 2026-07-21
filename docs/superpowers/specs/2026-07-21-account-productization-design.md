# 계정·제품화 (users/me, 카카오→이메일 연동, 탈퇴, 위험 API 정리)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 저장소: `back`

## Goal

계정 영역의 제품화 API를 완성한다.

- 인증된 사용자의 프로필 조회·수정 (`/users/me`)
- 카카오 전용 계정에 비밀번호를 설정해 이메일 로그인도 가능하게 함
- soft delete 기반 탈퇴 + 7일 유예·로그인 복구 + 유예 후 물리 삭제
- 디버그성 위험 엔드포인트 제거 및 soft-deleted 유저 차단 강화

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 전부 — `/users/me` + 카카오→이메일(비밀번호 설정) + 탈퇴 + 위험 API 정리 |
| 연동 방향 | 카카오 → 이메일만 (비밀번호 설정). 이메일→카카오·자동 병합 없음 |
| 탈퇴 | Soft delete (`deleted_at`) |
| 유예 | 7일 후 물리 삭제 |
| 복구 | 7일 내 login / kakao 로그인 성공 시 `deleted_at` 해제 |
| `/users/me` | GET + PATCH(nickname) + 비밀번호 변경. 이메일 수정 없음 |
| 아키텍처 | 기존 User/Auth 도메인 확장. Redis refresh 인덱스·access 블랙리스트 없음 |
| 위험 API | `GET /a` 제거 + soft-deleted 유저 게이트 점검 |
| Purge | 서비스 메서드 + 실행 스크립트. 인앱 스케줄러는 범위 밖 |

## Out of Scope

- 이메일 계정에 카카오 연동 / 로그인 시 자동 계정 병합
- 카카오 연결 끊기(unlink) UI·API
- 이메일 변경
- access JWT Redis 블랙리스트 / refresh 유저별 일괄 삭제 인덱스
- 인앱 cron 스케줄러
- rate limit / 캡차
- Google / Apple 로그인

## Architecture

```
Client (JWT)
  │
  ├─ GET/PATCH /users/me
  ├─ PATCH     /users/me/password
  └─ DELETE    /users/me
         │
         ▼
   UserService ── UserRepository ── users (deleted_at)
         │
Auth paths (login / kakao / refresh / get_current_user)
         │
         ├─ deleted_at IS NOT NULL → 차단
         └─ login·kakao + 유예 ≤7일 → deleted_at=NULL 복구 후 토큰 발급

Purge (수동/크론 스크립트)
  UserService.purge_expired_withdrawn_users()
    → deleted_at < now()-7d hard delete (CASCADE)
```

책임 분리:

- **User**: 프로필, 비밀번호 설정/변경, soft delete, purge
- **Auth**: 기존 토큰 발급 + soft-deleted 게이트 + 로그인 시 복구

## Data Model

`users` 추가 컬럼:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `deleted_at` | `timestamptz NULL` | NULL = 활성. 설정 시 soft-deleted |

인덱스: `ix_users_deleted_at` (partial `WHERE deleted_at IS NOT NULL` 권장)

기존 `email` / `kakao_id` unique는 유지한다. 유예 기간 중 동일 식별자로 재가입하는 것을 막고, 복구와 충돌하지 않는다.

물리 삭제 시 `ingredients` / `saved_recipes`는 기존 ORM·FK CASCADE로 정리한다. Redis refresh 키는 TTL(14일)로 자연 만료한다.

## API

### `GET /api/v1/users/me`

인증: JWT  
응답: `UserInfoResponse`

```text
id, email, nickname
has_password: bool   # password IS NOT NULL
has_kakao: bool      # kakao_id IS NOT NULL
deleted_at: datetime | null
```

### `PATCH /api/v1/users/me`

인증: JWT  
Body: `UpdateMeRequest` — `nickname` optional (2~20자). **email 필드 없음**  
닉네임 `lower()` unique 충돌 시 409.

### `PATCH /api/v1/users/me/password`

인증: JWT  
Body: `UpdatePasswordRequest`

- `new_password`, `checked_password` 필수 (8~20, 일치)
- `current_password` optional
  - `has_password == true` → 필수, 불일치 시 401
  - 카카오 전용(`password is NULL`) → 생략 가능 (최초 설정 = 이메일 로그인 연동)
  - 카카오 전용인데 `current_password`가 와도 **무시**

성공 시 갱신된 `UserInfoResponse` (`has_password=true`).

### `DELETE /api/v1/users/me`

인증: JWT  
동작: `deleted_at = now()`  
응답: `204 No Content`

### Auth 경로 강화

| 경로 | soft-deleted 동작 |
|------|-------------------|
| `get_current_user` | 401 — 보호 API 일괄 차단 |
| `POST /auth/refresh` | 401 |
| `POST /auth/login` | 유예 ≤7일 → 복구 후 토큰 / 만료 → 401 (일반 실패와 동일 톤) |
| `POST /auth/kakao` (기존 유저) | login과 동일 복구 규칙 |
| `POST /auth/kakao/complete` | 복구 대상 아님 (신규 가입만) |

### 정리

- `GET /a` (`main.py` 의도적 예외 유발) **제거**

## Flows

### 비밀번호 설정 (카카오 → 이메일 연동)

1. 카카오 전용 유저가 JWT로 `PATCH /users/me/password` 호출
2. `new_password` 해시 저장 (`password` NULL → non-NULL)
3. 이후 `POST /auth/login`으로 이메일+비밀번호 로그인 가능 (`has_kakao` 유지)

### 비밀번호 변경 (기존 이메일 계정)

1. `current_password` 검증
2. 새 비밀번호로 교체

### 탈퇴

1. `DELETE /users/me` → `deleted_at` 설정
2. 이후 access/refresh/보호 API는 `deleted_at` 체크로 거부

### 복구

1. 유예 기간 내 `login` 또는 `kakao` 인증 성공
2. `deleted_at = NULL`
3. 정상 토큰 발급

### Purge

1. `UserService.purge_expired_withdrawn_users()`
2. `deleted_at < now() - 7 days` 유저 hard delete
3. 실행은 스크립트/외부 크론. 인앱 스케줄러 없음

## Error Handling

| 상황 | HTTP |
|------|------|
| 미인증 / 잘못된 JWT | 401 |
| soft-deleted의 API·refresh | 401 |
| 유예 만료 후 로그인 | 401 (열거 완화를 위해 일반 실패 톤) |
| 닉네임 중복 | 409 |
| current_password 불일치 | 401 |
| has_password인데 current 누락 | 400 |
| 이미 탈퇴된 상태로 재탈퇴 | 401 (`get_current_user`에서 차단) |

보안 메모:

- 이메일 변경 API 없음
- 탈퇴·비밀번호·프로필은 JWT 필수
- 비밀번호 해시는 기존 Argon2 재사용
- 복구/실패 응답에서 “탈퇴됨”을 과도하게 노출하지 않음

## Testing

**API**

- `GET` / `PATCH /users/me` (닉네임, 이메일 필드 거부)
- 카카오 유저 비밀번호 최초 설정 → 이메일 로그인 성공
- 이메일 유저 비밀번호 변경 (current 필수/불일치)
- `DELETE /users/me` → 이후 보호 API·refresh 401
- 7일 내 login/kakao 복구
- 7일 경과 로그인 실패
- purge 후 유저·자식 데이터 삭제
- `GET /a` 라우트 부재

**Unit**

- `UserService`: update nickname, set/change password, withdraw, purge
- `AuthService`: deleted_at 게이트, 유예 내 복구, 유예 만료 거부

## Implementation Notes

- 기존 `UserService.get_user_info`를 `GET /users/me`에 연결하고 응답 필드 확장
- `UserRepository`에 `update`, soft-delete, purge 조회/삭제 추가
- 마이그레이션: `deleted_at` + partial index
- 카카오 소셜 로그인 스펙의 “이메일↔카카오 연동 Out of Scope”는 **이번 스펙으로 부분 해제** (카카오→비밀번호 설정만). 반대 방향은 여전히 Out of Scope
