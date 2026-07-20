# Refresh Token + Redis (Auth & Recipe Cache)

날짜: 2026-07-20  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

Access token 만료 시 재로그인 없이 세션을 유지하도록 opaque refresh token을 도입하고,  
공통 Redis 인프라로 refresh 저장과 레시피 상세 캐시를 함께 이전한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 백엔드 + 앱 (발급/갱신/로그아웃 + SecureStore + Axios silent refresh) |
| Refresh 형태 | Opaque 랜덤 토큰, Redis에 SHA-256 해시로 저장 |
| Rotation | 사용 시마다 회전, 이전 refresh 즉시 폐기 |
| TTL | access 15분 / refresh 14일 / recipe detail 캐시 24시간 |
| Logout | `POST /auth/logout`으로 해당 refresh만 폐기 + 앱 세션 삭제 |
| Redis | `docker-compose`에 Redis 추가, 공유 async 클라이언트, key prefix 분리 |
| Recipe 캐시 | 인메모리 dict → Redis (`recipe_detail:{key}`) |

## Out of Scope

- 전 기기 로그아웃 / 디바이스 메타데이터
- Refresh JWT / Postgres `refresh_tokens` 테이블
- Redis + Postgres 이중 저장
- 소셜 로그인
- Refresh grace period (동시 요청은 앱 단일 flight로 처리)

## Architecture

```
앱 (SecureStore)
  access_token + refresh_token
       │
       ├─ API 요청 ──► Bearer access
       ├─ 401 TOKEN_EXPIRED ──► POST /auth/refresh ──► 새 토큰 저장 후 재시도
       └─ 로그아웃 ──► POST /auth/logout + clearSession

백엔드
  docker-compose: postgresql + redis
  core/redis.py ── 공유 async Redis 클라이언트

  AuthService.issue_tokens
    → access JWT (15분)
    → opaque refresh → SHA-256 → Redis key `refresh:{hash}` (value: user_id, TTL 14일)

  RecipeDetailCache
    → Redis key `recipe_detail:{sha256}` (JSON, TTL 24시간)
```

### Components

| 구성 | 역할 |
|------|------|
| `core/redis.py` | Redis 연결/DI, 앱 기동·종료 수명 관리 |
| `domains/auth` | 발급·refresh rotation·logout revoke |
| Auth API | `POST /auth/login`, `/auth/refresh`, `/auth/logout` (+ signup 응답 확장) |
| `domains/recipe_detail/cache` | Redis get/set (인메모리 제거) |
| 앱 `authStore` + `client` | 이중 토큰 저장 + silent refresh + 단일 flight |

## API · Data Flow

### Auth response (login / signup / refresh)

```json
{
  "info": { "id": "...", "email": "...", "nickname": "..." },
  "access_token": "...",
  "refresh_token": "..."
}
```

login / signup / refresh는 **동일한 `AuthResponse`**를 사용한다.  
refresh 시 `info`는 Redis에서 얻은 `user_id`로 DB 조회해 채운다.

### Endpoints

| Method | Path | Body | 동작 |
|--------|------|------|------|
| `POST` | `/api/v1/auth/login` | email, password | 기존 + refresh 발급·Redis 저장 |
| `POST` | `/api/v1/users/signup` | (기존) | 기존 + refresh 발급·Redis 저장 |
| `POST` | `/api/v1/auth/refresh` | `{ "refresh_token" }` | 해시 조회 → 구 키 삭제 → 새 access/refresh 발급·저장 → 페어 반환 |
| `POST` | `/api/v1/auth/logout` | `{ "refresh_token" }` | 해당 Redis 키 삭제 (없거나 만료여도 200) |

### App flow

1. 로그인/가입 → SecureStore에 access + refresh 저장
2. API 401 + `TOKEN_EXPIRED` → refresh 1회 시도 → 성공 시 원요청 재시도
3. refresh 실패 또는 `INVALID_TOKEN` → `clearSession`
4. 동시 401은 **단일 flight**로 refresh 한 번만 수행 후 대기 요청에 새 access 적용
5. 로그아웃 → `POST /auth/logout` 후 로컬 세션 삭제

### Redis keys

| Prefix | Value | TTL |
|--------|-------|-----|
| `refresh:{sha256(token)}` | `user_id` (string UUID) | 14일 |
| `recipe_detail:{sha256}` | RecipeDetailResponse JSON | 24시간 |

### Access token

- JWT HS256, claims: `sub`, `iat`, `exp`
- `ACCESS_TOKEN_EXPIRE_MINUTES = 15` (기존 30에서 변경)
- `REFRESH_TOKEN_EXPIRE_DAYS = 14` (신규 상수/env)

## Error · Failure · Testing

### Auth errors

| 상황 | 코드 | 클라 동작 |
|------|------|-----------|
| access 만료 | `TOKEN_EXPIRED` | silent refresh |
| access 변조/형식 오류 | `INVALID_TOKEN` | 즉시 로그아웃 |
| refresh 없음·만료·재사용(rotation 후) | `INVALID_TOKEN` | 로그아웃 |
| refresh 성공 | 200 + 새 페어 | SecureStore 갱신 후 재시도 |
| logout | 항상 200 | 로컬도 항상 clear |

### Redis failure

- **Auth (발급/검증/삭제):** Redis 불가 시 5xx. 토큰을 “없는 척”하거나 발급을 스킵하지 않음
- **Recipe 캐시:** get 실패/불가 시 miss로 취급하고 크롤 폴백. set 실패는 로그만 (응답은 정상)

### Testing

- 백엔드: refresh rotation, 재사용 거부, logout 삭제, login/signup에 refresh 포함, recipe cache Redis hit/miss·폴백
- 앱: silent refresh, 단일 flight, refresh 실패 시 clearSession
- 로컬: compose Redis healthcheck, 앱 `depends_on`

## Relation to prior specs

- `2026-07-20-recipe-detail-10000recipe-design.md`의 “인메모리 TTL / Redis Out of Scope”는  
  **캐시 저장소만 이 스펙으로 대체**한다. 검색·매칭·크롤·API 계약은 그대로 유지한다.

## Success criteria

1. access 15분 만료 후에도 앱이 refresh로 세션을 유지한다
2. 사용된 refresh는 재사용 시 `INVALID_TOKEN`이다
3. logout 후 해당 refresh는 더 이상 유효하지 않다
4. 레시피 상세 캐시가 Redis에 저장되고, 프로세스 재시작 후에도 TTL 내 hit 된다
5. Redis 다운 시 레시피 API는 크롤로 동작하고, auth refresh/login은 5xx로 실패한다
