# Auth · AI Rate Limits (로그인 잠금 · 메일 발송 · OCR/RAG 일일 한도)

날짜: 2026-07-28  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 저장소: `back`  
프론트 계약: `LOGIN_LOCKED` + `quota` 필드로 앱이 비번 재설정 창·남은 횟수를 표시 (앱 코드 수정은 이번 범위 밖)

## Goal

1. 비밀번호를 **5회 이상** 틀리면 로그인을 잠그고, **비밀번호 재설정 완료** 후에만 다시 로그인할 수 있게 한다. 프론트는 `LOGIN_LOCKED`로 비밀번호 변경 창을 연다.
2. 인증 **메일 발송**(가입 발송·재발송·비밀번호 재설정 요청)을 **이메일당 하루 3회**로 제한한다.
3. **OCR 하루 3회**, **RAG 추천 하루 7회**(유저당)로 제한한다.
4. 성공 응답에 `quota`(limit / remaining / used / reset_at)를 넣고, 초과 시 명확한 429 에러 코드를 반환한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 저장소 | Redis 일일 카운터 (Approach 1) |
| 로그인 잠금 해제 | 기존 비밀번호 재설정 confirm 성공 시 (A) |
| 메일 한도 대상 | 발송만: signup issue + email resend + password reset request (A) |
| AI 한도 | OCR 3 / RAG 7 분리 |
| 프론트 공지 | 성공 시 `quota` + 초과 시 에러 코드 (C). 앱 레포 수정은 범위 밖 |
| 일자 경계 | Asia/Seoul (KST) 자정 |
| OCR/RAG 차감 시점 | 외부 API 호출 직전 consume. 외부 실패 시에도 차감 유지. 클라이언트 검증 실패는 미차감 |

## Out of Scope

- `saksak/app` 프론트 UI 구현 (에러 코드·`quota` 계약만 제공)
- IP 기반 전역 Rate Limit / Nginx 한도
- 캡차
- access JWT 블랙리스트
- 로그인 실패 카운트의 DB 영속화
- AI 레시피 에이전트 부활

## Architecture

```
[로그인 잠금]
POST /auth/login
  → user 없음 → 기존 메시지 (카운트 없음)
  → LoginLockStore.is_locked(email) → LOGIN_LOCKED
  → 비밀번호 틀림 → fail++ ; >=5 이면 잠금
  → 비밀번호 맞음 + 잠금 → LOGIN_LOCKED
  → 비밀번호 맞음 + 미잠금 → fail 초기화 후 토큰 발급

POST /auth/password/reset/confirm 성공
  → LoginLockStore.clear(email)

[메일 발송 한도]
signup issue / email resend / password reset request
  → (실제 발송하는 경우만) DailyQuotaStore.consume("email_send", email, limit=3)
  → 초과 → EMAIL_SEND_LIMIT_EXCEEDED (429)
  → 응답에 quota 포함
  → reset request: 유저 없거나 카카오 전용(password null)이면 발송·차감 없음, 응답은 동일 ok

[OCR / RAG]
POST /ocr/... , GET /recipes/recommendations
  → 인증 유저 기준 DailyQuotaStore.consume(kind, user_id, limit)
  → 초과 → OCR_DAILY_LIMIT_EXCEEDED / RAG_DAILY_LIMIT_EXCEEDED (429)
  → 성공 응답에 quota 포함
```

### Components

| 구성 | 역할 |
|------|------|
| `LoginLockStore` | Redis 실패 횟수·잠금 (`login_fail:{email}`) |
| `DailyQuotaStore` | KST 일자 키 일일 카운터 (메일·OCR·RAG 공용) |
| `AuthService` | 로그인 잠금 게이트 + 메일 발송 시 quota |
| `OcrService` / `RagService` | 한도 소비 + 응답에 quota |
| `TooManyRequestsException` | HTTP 429 |
| ErrorCode | `LOGIN_LOCKED`, `EMAIL_SEND_LIMIT_EXCEEDED`, `OCR_DAILY_LIMIT_EXCEEDED`, `RAG_DAILY_LIMIT_EXCEEDED` |

## Redis Keys

| 키 | TTL | 의미 |
|----|-----|------|
| `login_fail:{email}` | 잠금 해제까지 유지 (명시적 clear). 선택: 미잠금 시 24h TTL로 자연 소멸 | 실패 횟수 정수. `>=5`이면 잠금 |
| `quota:email_send:{email}:{YYYYMMDD}` | KST 다음날 00:00까지 | 메일 발송 횟수 |
| `quota:ocr:{user_id}:{YYYYMMDD}` | 동일 | OCR 횟수 |
| `quota:rag:{user_id}:{YYYYMMDD}` | 동일 | RAG 횟수 |

한도:

| kind | limit |
|------|-------|
| email_send | 3 |
| ocr | 3 |
| rag | 7 |

`reset_at`: 해당 KST 날짜의 다음 날 00:00:00+09:00 (ISO8601).

## API Contract

### 에러

| code | HTTP | detail (예시) |
|------|------|----------------|
| `LOGIN_LOCKED` | 401 | 비밀번호를 여러 번 틀려 로그인이 잠겼습니다. 비밀번호 재설정 후 다시 시도해 주세요. |
| `EMAIL_SEND_LIMIT_EXCEEDED` | 429 | 인증 메일 발송 한도를 초과했습니다. 내일 다시 시도해 주세요. |
| `OCR_DAILY_LIMIT_EXCEEDED` | 429 | OCR 일일 사용 한도를 초과했습니다. |
| `RAG_DAILY_LIMIT_EXCEEDED` | 429 | 레시피 추천 일일 사용 한도를 초과했습니다. |

429/잠금 응답에 가능하면 `limit`, `remaining`(0), `reset_at`을 포함한다.

### 성공 응답 `quota` 형태

```json
{
  "quota": {
    "limit": 3,
    "used": 1,
    "remaining": 2,
    "reset_at": "2026-07-29T00:00:00+09:00"
  }
}
```

적용 엔드포인트:

- 가입 인증 메일 발송 응답 (`message: verification_code_sent` 등)
- `POST /auth/email/resend`
- `POST /auth/password/reset/request` — 발송한 경우에만 `quota` 포함. 미발송(유저 없음 등)은 기존처럼 `ok`만 (열거 방지: quota로 존재 여부를 드러내지 않음)
- OCR 성공 응답
- RAG 추천 성공 응답

비밀번호 재설정 요청의 미발송 시 `quota`를 넣지 않아 계정 존재 여부를 숨긴다.

## Login Lock Rules

1. 이메일이 DB에 없는 경우: 실패 카운트하지 않음. 기존 `"이메일 또는 비밀번호가 올바르지 않습니다."`
2. 카카오 전용(`password is None`): 기존처럼 카카오 로그인 안내. 카운트하지 않음.
3. 비밀번호 불일치: `fail += 1`. 응답은 기존과 동일 톤의 401. `fail >= 5`가 되면 이후부터 `LOGIN_LOCKED`.
4. 이미 잠긴 상태에서 로그인 시도(비번 맞든 틀리든): `LOGIN_LOCKED`.
5. 잠기지 않은 상태에서 비밀번호 성공: `login_fail` 키 삭제 후 정상 로그인.
6. `password/reset/confirm` 성공: `login_fail` 키 삭제.

회원가입 미인증 유저(`EMAIL_NOT_VERIFIED`) 경로는 기존과 동일. 이번 잠금은 **이미 가입 완료된 이메일/비밀번호 유저**의 브루트포스 대응이다.

## Quota Consume Rules

### email_send

- `VerificationCodeStore.issue` / `resend`를 호출해 메일을 보내기 **직전**에 consume.
- 한도 초과 시 메일 미발송.
- `resend`의 기존 “코드당 1회 재발송” 규칙과 **병행** (둘 다 통과해야 발송).

### ocr / rag

- 요청 파라미터·이미지 검증 통과 후, 외부 API(Naver OCR / OpenAI embedding·LLM) 호출 **직전** consume.
- 한도 초과 시 외부 호출 없음.
- 외부 API 실패 시에도 차감 유지.
- 빈 이미지·형식 오류 등 `BadRequest`는 차감하지 않음.

## Testing

- 로그인: 4회 실패 후 5회째 성공 → 카운트 초기화 / 5회 실패 후 잠금 / 잠금 중 올바른 비번도 `LOGIN_LOCKED` / reset confirm 후 해제
- 메일: 동일 이메일 발송 3회 성공, 4회째 429 / 다른 이메일은 독립 / reset request 미존재 유저는 차감 없음
- OCR 3회·RAG 7회 초과 429 / 성공 응답 `quota` / 다른 user_id 독립
- 클라이언트 오류(OCR 빈 파일)는 used 미증가

## Implementation Notes

- `DailyQuotaStore.consume`은 Redis `INCR` + 최초 설정 시 TTL(다음날 자정까지 초)로 atomic에 가깝게 구현. 한도 초과 시 `DECR`로 롤백하거나, `INCR` 전 GET 검사 + 초과 시 DECR.
- 의존성 주입: `get_login_lock_store` / `get_daily_quota_store`를 `api/deps.py`에 추가.
- 기존 `CODE_TTL_SECONDS=180`, `MAX_ATTEMPTS=5`(코드 입력)는 유지. 메일 **발송** 일일 한도와는 별개.
