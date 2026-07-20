# 카카오 소셜 로그인

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 저장소: `back` + `app`

## Goal

카카오톡 네이티브 SDK로 소셜 로그인을 도입한다.  
기존 이메일/비밀번호 JWT(access 15분 + Redis refresh 14일) 세션 체계를 그대로 재사용한다.  
신규 카카오 유저는 추가 정보(닉네임·이메일) 입력 후에만 가입을 완료한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 앱 + 백엔드 전체 (A) |
| 카카오 키 | 코드·env 플레이스홀더만. 키는 나중에 `.env`에 투입 (C) |
| 클라이언트 UX | 네이티브 카카오 SDK — 카카오톡 앱 우선 (A) |
| 신규 유저 | 카카오 인증 후 추가 정보 화면 → 가입 완료 (B) |
| 추가 정보 | 닉네임 + 이메일. 비밀번호 없음 (B) |
| 서버 검증 | 앱이 보낸 Kakao access token을 서버가 `/v2/user/me`로 검증 (Approach A) |
| 중간 토큰 | `signup_token` — 짧은 TTL JWT (`purpose: kakao_signup`)로 kakao_id 위조 방지 |

## Out of Scope

- 기존 이메일 계정 ↔ 카카오 계정 연동
- Google / Apple 로그인
- 카카오 로그아웃·연결 끊기 UI
- 카카오 개발자 콘솔에서 키 발급 대행 (가이드만 문서화 가능)

## Architecture

```
[login.tsx] "카카오로 시작하기"
       ↓
[카카오 SDK] → Kakao Access Token
       ↓
POST /auth/kakao  { access_token }
       ↓
서버: 카카오 /v2/user/me 검증
       ├─ 기존 kakao_id 유저 → AuthResponse (JWT) → 메인
       └─ 신규 → { status: "needs_profile", signup_token }
                    ↓
            [kakao-profile 화면] 닉네임 + 이메일
                    ↓
            POST /auth/kakao/complete { signup_token, nickname, email }
                    ↓
            유저 생성 + AuthResponse → 메인
```

성공 후 앱 세션은 기존과 동일: `setSession(access, refresh, info)` + SecureStore.

### Components

| 구성 | 역할 |
|------|------|
| `User` 모델 | `password` nullable, `kakao_id` unique nullable 추가 |
| `domains/auth` | 카카오 토큰 검증, signup_token 발급/검증, complete 가입 |
| Auth API | `POST /auth/kakao`, `POST /auth/kakao/complete` |
| 앱 Kakao SDK | `@react-native-seoul/kakao-login` + Expo config plugin |
| 앱 `login.tsx` | 카카오 버튼 |
| 앱 `kakao-profile` 화면 | 닉네임·이메일 입력 → complete |
| 앱 `api/auth.ts` | `loginWithKakao`, `completeKakaoSignup` |

## Data Model

| 필드 | 변경 |
|------|------|
| `password` | nullable (소셜 전용 유저는 `NULL`) |
| `kakao_id` | 추가, unique, nullable (카카오 회원번호 문자열) |
| `email` | 유지 (unique, 필수 — 추가 정보에서 입력) |
| `nickname` | 유지 |

마이그레이션: 기존 이메일 유저의 `kakao_id`는 `NULL`, `password`는 기존 값 유지.

## API

### `POST /auth/kakao`

Request:

```json
{ "access_token": "<kakao access token>" }
```

응답 — 기존 유저:

```json
{
  "status": "authenticated",
  "info": { "id": "...", "email": "...", "nickname": "..." },
  "access_token": "...",
  "refresh_token": "..."
}
```

응답 — 신규:

```json
{
  "status": "needs_profile",
  "signup_token": "<short-lived JWT>"
}
```

서버 동작:
1. `Authorization: Bearer {access_token}`로 카카오 `GET https://kapi.kakao.com/v2/user/me` 호출
2. `id`(kakao_id) 추출
3. DB에서 `kakao_id` 조회 → 있으면 기존 `issue_tokens`와 동일하게 JWT 발급
4. 없으면 `signup_token` 발급 — 기존 `JWT_SECRET_KEY`로 서명하는 JWT, claim에 `kakao_id` + `purpose: "kakao_signup"`, TTL 10분

### `POST /auth/kakao/complete`

Request:

```json
{
  "signup_token": "...",
  "nickname": "...",
  "email": "..."
}
```

응답: `status: "authenticated"` + 기존 `AuthResponse` 필드 (`info` + `access_token` + `refresh_token`).

서버 동작:
1. `signup_token` 검증 → `kakao_id`
2. 이메일 중복 시 409
3. `password=NULL`, `kakao_id` 설정으로 User 생성
4. JWT 발급

### 기존 로그인 규칙

- `POST /auth/login`: `password`가 `NULL`인 계정이면 거부 — “카카오로 로그인해 주세요”
- refresh / logout: 변경 없음

## App (Expo)

### 패키지 · 설정

- `@react-native-seoul/kakao-login` + Expo config plugin
- env: `EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY` (`.env.example`에 플레이스홀더)
- 백엔드: 카카오 `user/me`는 access token만으로 호출하므로 추가 REST 키 불필요 (선택 env는 두지 않음)

### 화면

- `login.tsx`: 이메일 로그인 아래 카카오 버튼
- `(auth)/kakao-profile.tsx`: 닉네임·이메일 폼 → complete → `setSession` → 메인

### API 클라이언트

- `loginWithKakao(accessToken)` → status 분기
- `completeKakaoSignup({ signup_token, nickname, email })`

## Error Handling

| 상황 | 처리 |
|------|------|
| 카카오 로그인 취소 | 조용히 중단 (또는 가벼운 안내) |
| 카카오 토큰 무효/만료 | 400 — “카카오 인증 실패” |
| `signup_token` 만료/위조 | 401 → 로그인 화면으로 |
| 이메일 중복 | 409 → 추가 정보 화면에 필드 에러 |
| 이메일 로그인 + password null | 401 — “카카오로 로그인해 주세요” |

## Testing / Verification

- 백엔드: `/auth/kakao`, `/auth/kakao/complete` 단위·통합 테스트 (카카오 API는 mock)
- 앱: 키 투입 후 수동 — 신규 플로우, 기존 카카오 유저 재로그인, 이메일 로그인과의 분리

## Env Checklist (나중에 채움)

| 위치 | 변수 |
|------|------|
| app `.env` | `EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY` |
| 카카오 콘솔 | 네이티브 앱 키, 플랫폼 패키지명/번들 ID, Redirect URI(SDK 요구 시) |
