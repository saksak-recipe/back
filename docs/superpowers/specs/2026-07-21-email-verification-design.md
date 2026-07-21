# 이메일 인증 (회원가입 · 비밀번호 찾기)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 저장소: `back`

## Goal

이메일 회원가입과 비밀번호 찾기에 6자리 코드 기반 이메일 인증을 도입한다.  
미인증 계정은 로그인할 수 없고, 카카오 가입 유저는 이메일 인증을 생략한다.  
메일 발송은 SMTP를 사용하고, 인증 코드는 Redis에 저장한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 인증 방식 | 6자리 숫자 코드 (A) |
| 가입 타이밍 | 계정 생성 후 인증 완료 전까지 로그인 불가 (A) |
| 메일 전송 | SMTP (A) |
| 비밀번호 찾기 | 코드 + 새 비밀번호를 한 요청으로 확인·변경 (A) |
| 카카오 유저 | 이메일 인증 생략, 가입 시 `is_email_verified=True` (A) |
| 코드 저장 | Redis + TTL (Approach 1) |

## Out of Scope

- 이메일 링크(매직 링크) 인증
- SendGrid / SES / Resend 등 외부 메일 API
- 기존 이메일 계정 ↔ 카카오 계정 연동
- 프론트엔드(앱) UI 구현 (백엔드 API만)
- 이메일 변경 시 재인증

## Architecture

```
[회원가입]
POST /users/signup
  → User 생성 (is_email_verified=False)
  → Redis에 signup 코드 저장 + SMTP 발송
  → 토큰 미발급

POST /auth/email/verify { email, code }
  → 코드 검증 → is_email_verified=True
  → access + refresh 발급

POST /auth/login
  → is_email_verified=False 이면 EMAIL_NOT_VERIFIED

[비밀번호 찾기]
POST /auth/password/reset/request { email }
  → (계정 존재·이메일 유저일 때만) Redis에 password_reset 코드 + SMTP
  → 응답은 항상 동일 (존재 여부 숨김)

POST /auth/password/reset/confirm { email, code, password, checked_password }
  → 코드 검증 → 비밀번호 변경 → 코드 삭제
```

### Components

| 구성 | 역할 |
|------|------|
| `EmailService` | SMTP로 인증 코드 메일 발송. 미설정 시 console 백엔드로 코드 로그 |
| `VerificationCodeStore` | Redis에 코드(해시)·쿨다운·시도 횟수 관리 |
| `User.is_email_verified` | 이메일 가입 인증 여부 |
| Auth/User API | signup 변경 + verify / resend / password reset 엔드포인트 |

## Data Model

| 필드 | 변경 |
|------|------|
| `is_email_verified` | `bool`, NOT NULL, 기본 `False` |

마이그레이션:
- 기존 이메일 유저: `is_email_verified=True`로 백필 (이미 사용 중인 계정 차단 방지)
- 카카오 전용 유저: `True`
- 신규 이메일 가입: `False`

## Redis 코드 저장

| 항목 | 값 |
|------|-----|
| Key | `email_code:{purpose}:{email}` — `purpose`는 `signup` \| `password_reset` |
| Value | 코드의 단방향 해시 (+ 필요 시 메타) |
| TTL | 10분 |
| 재발송 쿨다운 | 60초 (`email_code_cooldown:{purpose}:{email}`) |
| 검증 실패 | 5회 초과 시 해당 코드 키 삭제(무효화) |
| 보안 | 평문 코드는 메일에만 포함. Redis에는 해시만 저장 |

## API

### `POST /api/v1/users/signup` (변경)

요청: 기존과 동일 (`email`, `password`, `checked_password`, `nickname`)

동작:
1. 중복 검사 후 User 생성 (`is_email_verified=False`)
2. signup용 6자리 코드 발송
3. **토큰을 발급하지 않음**

응답: `{ email, message }` (예: `message: "verification_code_sent"`). 기존 `access_token`/`refresh_token`/`info`는 제거.

### `POST /api/v1/auth/email/verify`

요청: `{ email, code }`  
성공: `is_email_verified=True` + `AuthResponse` (access/refresh/info)  
실패: `INVALID_VERIFICATION_CODE`, `USER_NOT_FOUND`, `EMAIL_ALREADY_VERIFIED`

### `POST /api/v1/auth/email/resend`

요청: `{ email }`  
성공: 새 코드 발송 (쿨다운 통과 시)  
실패: `VERIFICATION_COOLDOWN`, `USER_NOT_FOUND`, `EMAIL_ALREADY_VERIFIED`

### `POST /api/v1/auth/password/reset/request`

요청: `{ email }`  
응답: 항상 동일 성공 메시지 (계정 유무·카카오 전용 여부 노출하지 않음)  
내부: 이메일+비밀번호 계정이 있을 때만 코드 발송

### `POST /api/v1/auth/password/reset/confirm`

요청: `{ email, code, password, checked_password }`  
성공: 비밀번호 변경, 코드 삭제  
실패: `INVALID_VERIFICATION_CODE` 등. 카카오 전용(`password is None`)은 리셋 대상이 아님

### `POST /api/v1/auth/login` (변경)

`is_email_verified=False`이면 로그인 거부 → `EMAIL_NOT_VERIFIED`

카카오 플로우 (`/auth/kakao`, `/auth/kakao/complete`)는 기존 유지. complete 시 `is_email_verified=True`.

## SMTP / Settings

| 설정 | 설명 |
|------|------|
| `EMAIL_BACKEND` | `smtp` \| `console` (기본: 개발 `console`, 운영 `smtp`) |
| `SMTP_HOST` | SMTP 호스트 |
| `SMTP_PORT` | 포트 (예: 587) |
| `SMTP_USER` | 인증 사용자 |
| `SMTP_PASSWORD` | 인증 비밀번호 |
| `SMTP_FROM_EMAIL` | 발신 주소 |
| `SMTP_FROM_NAME` | 발신 표시명 (선택) |
| `SMTP_USE_TLS` | 기본 `True` |

메일 본문: 용도별 제목(회원가입 인증 / 비밀번호 재설정) + 6자리 코드 + 유효 시간(10분) 안내.

## Error Codes

| 코드 | 상황 |
|------|------|
| `EMAIL_NOT_VERIFIED` | 미인증 계정 로그인 |
| `INVALID_VERIFICATION_CODE` | 코드 불일치·만료·시도 초과 |
| `VERIFICATION_COOLDOWN` | 재발송 쿨다운 중 |
| `EMAIL_ALREADY_VERIFIED` | 이미 인증된 계정에 verify/resend |
| `USER_NOT_FOUND` | verify/resend 대상 사용자 없음 (reset request는 숨김) |

## Testing

- 유닛: 코드 생성·해시 검증·TTL·쿨다운·5회 실패 무효화
- API: signup → verify → login 성공
- API: 미인증 login → `EMAIL_NOT_VERIFIED`
- API: password reset request → confirm → 새 비밀번호로 login
- API: 존재하지 않는 이메일 reset request도 동일 성공 응답
- API: 카카오 complete 후 `is_email_verified=True`, 이메일 verify 불필요
- console 백엔드에서 메일 발송이 예외 없이 동작

## Success Criteria

1. 이메일 가입 직후 토큰이 발급되지 않고, verify 후에만 로그인·토큰 발급이 된다.
2. 비밀번호 찾기가 코드 한 번으로 재설정까지 완료된다.
3. 카카오 유저는 추가 이메일 인증 없이 기존처럼 로그인된다.
4. SMTP 또는 console 백엔드로 코드가 전달된다.
5. 계정 존재 여부가 password reset request 응답으로 드러나지 않는다.
