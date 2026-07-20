# 카카오 소셜 로그인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이티브 카카오 SDK + 서버 토큰 검증으로 소셜 로그인을 추가하고, 신규 유저는 닉네임·이메일 입력 후 가입 완료한다.

**Architecture:** 앱이 Kakao access token을 받아 `POST /auth/kakao`로 보내고, 서버가 카카오 `/v2/user/me`로 검증한다. 기존 유저는 JWT를 발급하고, 신규는 짧은 `signup_token`(JWT)을 준 뒤 `POST /auth/kakao/complete`에서 유저를 생성한다.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, httpx, PyJWT, Expo 57, `@react-native-seoul/kakao-login`, TanStack Query, Zustand

## Global Constraints

- 비밀번호 없는 소셜 유저: `password=NULL`, `kakao_id` unique
- `signup_token`: 기존 `JWT_SECRET_KEY`, TTL 10분, claim `purpose=kakao_signup` + `kakao_id`
- 기존 JWT access/refresh·SecureStore 흐름 재사용
- 카카오 키는 env 플레이스홀더만 (실제 키는 나중에)
- 계정 연동·Google/Apple·연결 끊기 UI는 범위 밖

---

## File Structure

### Backend
| File | Responsibility |
|------|----------------|
| `src/domains/user/model.py` | `password` nullable, `kakao_id` 추가 |
| `alembic/versions/..._kakao_login.py` | 마이그레이션 |
| `src/domains/user/repository.py` | `get_user_by_kakao_id` |
| `src/domains/auth/schemas.py` (new) | Kakao request/response schemas |
| `src/domains/auth/kakao_client.py` (new) | 카카오 user/me 호출 |
| `src/core/security.py` | signup_token create/decode |
| `src/domains/auth/service.py` | `login_with_kakao`, `complete_kakao_signup` |
| `src/api/v1/endpoints/auth.py` | `/kakao`, `/kakao/complete` |
| `tests/unit/test_auth_service.py` | 카카오 플로우 테스트 |

### App
| File | Responsibility |
|------|----------------|
| `package.json` / `app.json` | SDK + config plugin |
| `.env.example` | `EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY` |
| `src/types/api.ts` | Kakao 응답 타입 |
| `src/api/auth.ts` | `loginWithKakao`, `completeKakaoSignup` |
| `src/app/(auth)/login.tsx` | 카카오 버튼 |
| `src/app/(auth)/kakao-profile.tsx` | 닉네임·이메일 폼 |

---

### Task 1: User 모델 + 마이그레이션

**Files:**
- Modify: `back/src/domains/user/model.py`
- Create: `back/alembic/versions/<rev>_add_kakao_id_nullable_password.py`
- Modify: `back/src/domains/user/repository.py`

- [ ] **Step 1:** `password` → `Mapped[str | None]`, `kakao_id: Mapped[str | None]` unique nullable 추가
- [ ] **Step 2:** Alembic revision — `password` nullable, `kakao_id` String(64) unique nullable
- [ ] **Step 3:** `get_user_by_kakao_id(kakao_id: str)` 추가
- [ ] **Step 4:** Commit

### Task 2: signup_token + Kakao client + Auth schemas/service

**Files:**
- Modify: `back/src/core/security.py`
- Create: `back/src/domains/auth/kakao_client.py`
- Create: `back/src/domains/auth/schemas.py` (또는 user/schemas에 추가)
- Modify: `back/src/domains/auth/service.py`
- Modify: `back/src/api/v1/endpoints/auth.py`
- Modify: `back/tests/unit/test_auth_service.py`

- [ ] **Step 1:** `create_kakao_signup_token(kakao_id)` / `decode_kakao_signup_token(token) -> str`
- [ ] **Step 2:** `fetch_kakao_user_id(access_token) -> str` (httpx, 실패 시 BadRequest/ExternalService)
- [ ] **Step 3:** Schemas — `KakaoLoginRequest`, `KakaoNeedsProfileResponse`, `KakaoAuthResponse`, `KakaoCompleteRequest`
- [ ] **Step 4:** `login_with_kakao` / `complete_kakao_signup`; 이메일 로그인 시 password null → “카카오로 로그인해 주세요”
- [ ] **Step 5:** 엔드포인트 연결
- [ ] **Step 6:** 단위 테스트 (카카오 client mock) 통과
- [ ] **Step 7:** Commit

### Task 3: 앱 API 타입 + 카카오 SDK 설정

**Files:**
- Modify: `app/package.json`, `app/app.json`, `app/.env.example`
- Modify: `app/src/types/api.ts`, `app/src/api/auth.ts`

- [ ] **Step 1:** `@react-native-seoul/kakao-login` 설치 + config plugin (`kakaoAppKey` from env)
- [ ] **Step 2:** 타입·API 함수 추가
- [ ] **Step 3:** Commit

### Task 4: 로그인 UI + 프로필 완료 화면

**Files:**
- Modify: `app/src/app/(auth)/login.tsx`
- Create: `app/src/app/(auth)/kakao-profile.tsx`

- [ ] **Step 1:** 로그인 화면에 카카오 버튼 — SDK 로그인 → `/auth/kakao` → authenticated면 세션 / needs_profile이면 `kakao-profile`로 `signup_token` 전달
- [ ] **Step 2:** 프로필 화면 — 닉네임·이메일 → complete → setSession → main
- [ ] **Step 3:** Commit

---

## Verification

```bash
cd back && uv run pytest tests/unit/test_auth_service.py -v
cd app && npx tsc --noEmit
```
