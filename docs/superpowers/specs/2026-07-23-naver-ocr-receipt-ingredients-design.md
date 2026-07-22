# 네이버 OCR 영수증 → 식재료 후보 추출

날짜: 2026-07-23  
상태: Approved (대화에서 섹션별 승인 완료)  
관련: 식재료 CRUD (`domains/ingredient/`), RAG 임베딩용 `OPENAI_API_KEY`

## Goal

마트/가게 **영수증 이미지**를 업로드하면, 서버가 **Naver CLOVA OCR**로 텍스트를 읽고  
**OpenAI Chat**으로 식재료명만 필터·정규화한 뒤, 클라이언트가 확인·수정할 수 있도록  
**후보 목록만** 반환한다. 실제 냉장고 등록은 기존 `POST /ingredients`(또는 그룹 API)를 사용한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 이미지 종류 | 영수증 (포장지·손글씨 1차 범위 제외) |
| 추출 필드 | **식재료 이름만** (구매일·유통기한 추출 없음) |
| 등록 방식 | **B.** LLM 결과를 응답으로만 반환 → 클라이언트가 확인 후 기존 추가 API 호출 |
| 비식재료 | **A.** LLM이 식재료만 반환 (봉투·할인·세제 등 제외) |
| 이름 정규화 | **A.** 짧은 일반명 (브랜드·용량 제거, 레시피 매칭에 유리) |
| LLM | **A.** OpenAI Chat (`OPENAI_API_KEY` 재사용, 기본 `gpt-4o-mini`) |
| 아키텍처 | **A.** 단일 파이프라인 `POST /ocr/receipt` (OCR → LLM → JSON) |
| DB 저장 | OCR 결과·임시 테이블 **없음** |
| 그룹 전용 API | 없음 (클라이언트가 개인/그룹 등록 엔드포인트 선택) |

## Out of Scope

- 식재료 DB 직접 insert / confirm 2단계 API / 비동기 job
- 구매일·유통기한·가격·수량 추출
- OCR 원문 반환 API와 파싱 API 분리
- 포장지·손글씨·냉장고 사진 전용 파이프라인
- 프론트엔드 UI
- 이미지 영구 저장(S3 등)

## Problem

영수증에는 식재료와 무관한 항목이 많고, OCR 원문은 브랜드·용량·프로모션 문구가 섞여 있다.  
바로 `POST /ingredients`에 넣으면 노이즈가 냉장고에 쌓인다.  
OCR → LLM 가공 → 사용자 확인 → 기존 등록 API 순으로 분리하면,  
추출 품질과 등록 책임(유통기한 autofill 등)을 기존 도메인에 맡길 수 있다.

## Architecture

```
[앱]
  POST /api/v1/ocr/receipt (multipart image)
       → domains/ocr/
            Naver CLOVA OCR  → 원문 텍스트
            OpenAI Chat      → ingredients: string[]
       ← { "ingredients": ["왕교자", "계란", ...] }

  (사용자 확인·수정)

  POST /api/v1/ingredients          (기존, 변경 없음)
  또는 POST /api/v1/groups/me/ingredients
```

- `domains/ocr/`는 **추출·가공만** 담당. `IngredientService`를 호출하지 않는다.
- 등록·shelf-life 해석은 기존 ingredient 경로를 그대로 사용한다.

## Components

| 구성 | 역할 |
|------|------|
| `api/v1/endpoints/ocr.py` | `POST /ocr/receipt`, JWT, multipart 수신 |
| `domains/ocr/schemas.py` | 응답 `OcrReceiptResponse { ingredients: list[str] }` |
| `domains/ocr/naver_client.py` | CLOVA OCR HTTP 호출, 필드 텍스트 합치기 |
| `domains/ocr/llm_parser.py` | OpenAI Chat + structured JSON, 필터·정규화 |
| `domains/ocr/service.py` | 이미지 검증 → OCR → LLM 오케스트레이션 |
| `api/deps.py`, `api/api.py` | DI·라우터 등록 |
| `core/config.py` | OCR/LLM 관련 설정 |

모델·repository·Alembic은 **불필요** (상태 없음).

## API Contract

| | |
|---|---|
| Method / Path | `POST /api/v1/ocr/receipt` |
| Auth | JWT 필수 (`get_current_user`) |
| Content-Type | `multipart/form-data` |
| Field | `image` — jpg / jpeg / png / webp |
| Size limit | 10MB (초과 시 400) |
| 성공 200 | `{ "ingredients": ["왕교자", "계란"] }` |
| 식재료 없음 | 200 + `ingredients: []` (에러 아님) |

요청 body에 구매일 등은 두지 않는다. 등록 시 날짜는 클라이언트가 기존 `AddIngredientRequest`로 넘긴다.

## Config

| Env | 용도 | 비고 |
|-----|------|------|
| `NAVER_OCR_API_URL` | CLOVA OCR invoke URL | 필수 |
| `NAVER_OCR_SECRET_KEY` | `X-OCR-SECRET` | 필수 |
| `OPENAI_API_KEY` | Chat + 기존 RAG 임베딩 | 기존 유지 |
| `OCR_LLM_MODEL` | Chat 모델명 | 기본 `gpt-4o-mini` |

## LLM Rules

프롬프트/시스템 지시로 다음을 강제한다.

1. 입력은 영수증 OCR 원문이다.
2. **식재료(식품)만** 출력. 봉투, 배달비, 할인, 세제, 포인트 등 제외.
3. 이름을 **짧은 일반명**으로 정규화 (예: `CJ 비비고 왕교자 1.05kg` → `왕교자`). 제품에서 가장 식별되는 짧은 식품명을 고른다.
4. 각 이름은 DB `ingredient_name` 한도(45자) 이내. 초과 시 잘라낸다.
5. 중복 제거. 순서는 OCR 등장 순을 유지한다.
6. 출력은 JSON만: `{ "ingredients": ["...", "..."] }`.

구현은 OpenAI **JSON mode(또는 structured output) + Pydantic 검증**을 사용한다. 파싱 실패 시 외부 서비스 에러로 처리한다.

## Error Handling

| 상황 | 응답 |
|------|------|
| `image` 누락, 미지원 MIME, 10MB 초과 | 400 validation |
| Naver OCR HTTP/타임아웃/비정상 응답 | `ExternalServiceException` (OCR) |
| OpenAI 실패, JSON 스키마 불일치 | `ExternalServiceException` (LLM) |
| OCR 성공 + 식재료 0개 | 200 `[]` |

기존 `ExternalServiceException` 패턴을 재사용하고, 구분용 `ErrorCode`(예: `OCR_FAILED`, `OCR_LLM_FAILED`)를 추가한다.

## Testing

- **단위 `llm_parser`**: mock OpenAI — 비식품 제외, 정규화, 중복 제거, 잘못된 JSON → 예외
- **단위 `service`**: OCR/LLM mock — 호출 순서, 빈 목록 통과
- **API**: multipart fixture + 외부 mock — 200 스키마, 400(잘못된 파일), 외부 실패 시 에러 코드

실 Naver/OpenAI 호출 E2E는 CI에서 스킵(또는 수동) 가능.

## Implementation Notes

- 빈 디렉터리 `src/domains/ocr/`를 이 스펙의 구현 위치로 사용한다.
- 이미지 바이트는 요청 범위에서만 사용하고 디스크에 저장하지 않는다.
- Naver 호출은 `httpx` 비동기 클라이언트.
- OpenAI Chat은 공식 `openai` SDK의 얇은 래퍼(`llm_parser.py`). RAG용 LangChain embeddings와는 분리한다.

## Success Criteria

1. 인증된 사용자가 영수증 이미지를내면 `ingredients` 문자열 배열을 받는다.
2. 비식재료가 결과에 포함되지 않는다(프롬프트+단위 테스트로 검증).
3. 서버가 식재료 테이블에 row를 만들지 않는다.
4. 클라이언트가 반환 목록으로 기존 `POST /ingredients`를 호출해 등록할 수 있다.
