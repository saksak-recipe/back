# 네이버 OCR 영수증 식재료 추출 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영수증 이미지를 `POST /api/v1/ocr/receipt`로 받아 Naver CLOVA OCR → OpenAI Chat으로 식재료명 후보만 반환한다. DB에는 쓰지 않으며, 등록은 기존 `POST /ingredients`가 담당한다.

**Architecture:** `domains/ocr/`에 상태 없는 파이프라인(naver_client → llm_parser → service → endpoint)을 둔다. 설정은 env, 에러는 `ExternalServiceException`(+ OCR 전용 ErrorCode). 이미지는 요청 메모리에서만 사용한다.

**Tech Stack:** FastAPI, httpx, openai (`AsyncOpenAI`), Pydantic, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-07-23-naver-ocr-receipt-ingredients-design.md`

## Global Constraints

- 추출 필드: **식재료 이름만** (구매일·유통기한 추출 없음)
- 응답만 반환, **IngredientService / DB insert 금지**
- LLM: OpenAI Chat, 기본 모델 `gpt-4o-mini` (`OCR_LLM_MODEL`)
- 이미지: jpg/jpeg/png/webp, **10MB** 초과 시 400
- 이름 정규화: 짧은 일반명, **최대 45자** (`ingredient_name` 한도)
- 식재료 0개 → **200 + `[]`**
- 프론트·비동기 job·OCR/파싱 분리 API Out of Scope
- 커밋은 유저가 요청할 때만 (스텝에 commit이 있어도 요청 전 skip)

---

## File Structure

| 동작 | 경로 | 책임 |
|------|------|------|
| Create | `src/domains/ocr/schemas.py` | `OcrReceiptResponse` |
| Create | `src/domains/ocr/llm_parser.py` | OpenAI → `list[str]` |
| Create | `src/domains/ocr/naver_client.py` | CLOVA OCR → 원문 텍스트 |
| Create | `src/domains/ocr/service.py` | 검증 + 오케스트레이션 |
| Create | `src/api/v1/endpoints/ocr.py` | `POST /ocr/receipt` |
| Create | `tests/unit/test_ocr_llm_parser.py` | LLM 파서 단위 테스트 |
| Create | `tests/unit/test_ocr_naver_client.py` | Naver 클라이언트 단위 테스트 |
| Create | `tests/unit/test_ocr_service.py` | 서비스 단위 테스트 |
| Create | `tests/api/test_ocr_api.py` | API 테스트 |
| Modify | `src/core/config.py` | `NAVER_OCR_*`, `OCR_LLM_MODEL` |
| Modify | `src/core/exception/codes.py` | `OCR_FAILED`, `OCR_LLM_FAILED` |
| Modify | `src/core/exception/exceptions.py` | `ExternalServiceException`에 optional `code` |
| Modify | `src/api/deps.py` | `get_ocr_service` |
| Modify | `src/api/api.py` | ocr router 등록 |
| Modify | `tests/conftest.py` | OCR 관련 env 기본값 |

---

### Task 1: Config · ErrorCode · ExternalServiceException

**Files:**
- Modify: `src/core/config.py`
- Modify: `src/core/exception/codes.py`
- Modify: `src/core/exception/exceptions.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `Settings.NAVER_OCR_API_URL: str` (default `""`)
- Produces: `Settings.NAVER_OCR_SECRET_KEY: SecretStr` (default empty)
- Produces: `Settings.OCR_LLM_MODEL: str` (default `"gpt-4o-mini"`)
- Produces: `ErrorCode.OCR_FAILED`, `ErrorCode.OCR_LLM_FAILED`
- Produces: `ExternalServiceException(detail=..., code=ErrorCode.EXTERNAL_SERVICE_ERROR)` — `code` 인자 optional, 기존 호출 호환

- [ ] **Step 1: 설정·에러 코드 추가**

`src/core/config.py` — `OPENAI_API_KEY` 아래에:

```python
    NAVER_OCR_API_URL: str = ""
    NAVER_OCR_SECRET_KEY: SecretStr = SecretStr("")
    OCR_LLM_MODEL: str = "gpt-4o-mini"
```

`src/core/exception/codes.py` — 공통 섹션 `EXTERNAL_SERVICE_ERROR` 다음에:

```python
    OCR_FAILED = "OCR_FAILED"
    OCR_LLM_FAILED = "OCR_LLM_FAILED"
```

`src/core/exception/exceptions.py` — `ExternalServiceException`을 다음으로 교체:

```python
class ExternalServiceException(BaseCustomException):
    def __init__(
        self,
        detail: str = "외부 서비스 연동 중 오류가 발생하였습니다.",
        code: str | ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
    ):
        super().__init__(status_code=502, code=code, detail=detail)
```

`tests/conftest.py` — env setdefault 블록에:

```python
os.environ.setdefault("NAVER_OCR_API_URL", "https://ocr.test.example/invoke")
os.environ.setdefault("NAVER_OCR_SECRET_KEY", "test-ocr-secret")
os.environ.setdefault("OCR_LLM_MODEL", "gpt-4o-mini")
```

Settings는 `@lru_cache`이므로, 테스트에서 settings를 다시 읽어야 하면 `get_settings.cache_clear()`를 호출한다. conftest의 setdefault는 `import main` **이전**에 두어 앱 로드 시 값이 들어가게 한다(기존 `OPENAI_API_KEY`와 동일 위치).

- [ ] **Step 2: 기존 ExternalService 테스트가 깨지지 않는지 확인**

Run: `uv run pytest tests/unit/test_rag_retriever.py -v`

Expected: PASS (기존 `ExternalServiceException(detail=...)` 호출 호환)

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add src/core/config.py src/core/exception/codes.py src/core/exception/exceptions.py tests/conftest.py
git commit -m "feat(ocr): OCR 설정과 ExternalService ErrorCode 확장"
```

---

### Task 2: schemas + llm_parser (TDD)

**Files:**
- Create: `src/domains/ocr/schemas.py`
- Create: `src/domains/ocr/llm_parser.py`
- Create: `tests/unit/test_ocr_llm_parser.py`

**Interfaces:**
- Produces: `OcrReceiptResponse(ingredients: list[str])`
- Produces: `async def parse_receipt_text(ocr_text: str, *, api_key: str, model: str) -> list[str]`
- Consumes: `ErrorCode.OCR_LLM_FAILED`, `ExternalServiceException`
- Side effects: OpenAI Chat Completions JSON; 실패 시 `ExternalServiceException(code=OCR_LLM_FAILED)`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ocr_llm_parser.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from httpx import Request

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.llm_parser import parse_receipt_text


@pytest.mark.asyncio
async def test_parse_receipt_text_returns_ingredients_and_truncates():
    long_name = "가" * 50
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"ingredients": ["왕교자", "계란", "' + long_name + '", "왕교자"]}'
            )
        )
    ]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.llm_parser.AsyncOpenAI", return_value=mock_client):
        result = await parse_receipt_text(
            "비비고 왕교자\n계란\n...",
            api_key="test-key",
            model="gpt-4o-mini",
        )

    assert result == ["왕교자", "계란", "가" * 45]
    mock_client.chat.completions.create.assert_awaited_once()
    call_kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_parse_receipt_text_empty_ingredients():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"ingredients": []}'))
    ]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.llm_parser.AsyncOpenAI", return_value=mock_client):
        result = await parse_receipt_text("봉투 100원", api_key="k", model="gpt-4o-mini")

    assert result == []


@pytest.mark.asyncio
async def test_parse_receipt_text_invalid_json_raises():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not-json"))]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.llm_parser.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await parse_receipt_text("x", api_key="k", model="gpt-4o-mini")

    assert exc_info.value.code == ErrorCode.OCR_LLM_FAILED


@pytest.mark.asyncio
async def test_parse_receipt_text_openai_error_raises():
    mock_client = AsyncMock()
    request = Request("POST", "https://api.openai.com/v1/chat/completions")
    mock_client.chat.completions.create = AsyncMock(
        side_effect=openai.APIError("fail", request=request, body=None)
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.llm_parser.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await parse_receipt_text("x", api_key="k", model="gpt-4o-mini")

    assert exc_info.value.code == ErrorCode.OCR_LLM_FAILED
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/unit/test_ocr_llm_parser.py -v`

Expected: FAIL (`ModuleNotFoundError` 또는 import 실패)

- [ ] **Step 3: Implement schemas + llm_parser**

`src/domains/ocr/schemas.py`:

```python
from pydantic import BaseModel, Field


class OcrReceiptResponse(BaseModel):
    ingredients: list[str] = Field(default_factory=list)


class _LlmIngredientsPayload(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
```

`src/domains/ocr/llm_parser.py`:

```python
import json

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.schemas import _LlmIngredientsPayload

INGREDIENT_NAME_MAX_LEN = 45

SYSTEM_PROMPT = """당신은 마트 영수증 OCR 텍스트에서 식재료만 추출하는 도우미입니다.
규칙:
1. 식재료(식품)만 포함하세요. 봉투, 배달비, 할인, 세제, 포인트, 쿠폰 등은 제외합니다.
2. 이름은 짧은 일반명으로 정규화하세요. 브랜드·용량·프로모션 문구를 제거합니다.
   예: "CJ 비비고 왕교자 1.05kg" → "왕교자"
3. 중복을 제거하고, OCR에 나온 순서를 유지합니다.
4. 반드시 JSON만 출력합니다: {"ingredients": ["이름1", "이름2"]}
5. 식재료가 없으면 {"ingredients": []} 입니다."""


def _normalize_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        name = raw.strip()[:INGREDIENT_NAME_MAX_LEN]
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


async def parse_receipt_text(
    ocr_text: str,
    *,
    api_key: str,
    model: str,
) -> list[str]:
    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": ocr_text},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = _LlmIngredientsPayload.model_validate(json.loads(content))
        return _normalize_names(payload.ingredients)
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError, IndexError, TypeError) as exc:
        raise ExternalServiceException(
            detail="영수증 식재료 분석 중 오류가 발생했습니다.",
            code=ErrorCode.OCR_LLM_FAILED,
        ) from exc
```

참고: `AsyncOpenAI`를 context manager로 쓰지 않아도 된다. 테스트의 `__aenter__` mock은 구현이 context manager를 쓰지 않으면 불필요하다 — **구현에 맞춰 테스트를 단순화**한다. 권장 테스트 mock:

```python
with patch("domains.ocr.llm_parser.AsyncOpenAI") as mock_cls:
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    ...
```

Step 1 테스트도 위 패턴으로 작성한다 (`__aenter__`/`__aexit__` 제거).

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/unit/test_ocr_llm_parser.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시에만)

```bash
git add src/domains/ocr/schemas.py src/domains/ocr/llm_parser.py tests/unit/test_ocr_llm_parser.py
git commit -m "feat(ocr): 영수증 OCR 텍스트 LLM 식재료 파서 추가"
```

---

### Task 3: naver_client (TDD)

**Files:**
- Create: `src/domains/ocr/naver_client.py`
- Create: `tests/unit/test_ocr_naver_client.py`

**Interfaces:**
- Produces: `async def extract_text(image_bytes: bytes, *, format: str, api_url: str, secret_key: str) -> str`
- Consumes: `ErrorCode.OCR_FAILED`, `ExternalServiceException`, `httpx`
- `format`: `"jpg"` | `"jpeg"` | `"png"` | `"webp"` — CLOVA `images[].format`용. `jpeg`는 CLOVA에 `"jpg"`로 보낸다.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ocr_naver_client.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.naver_client import extract_text


@pytest.mark.asyncio
async def test_extract_text_joins_infer_text():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "images": [
            {
                "fields": [
                    {"inferText": "왕교자"},
                    {"inferText": "1,200"},
                    {"inferText": "계란"},
                ]
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        text = await extract_text(
            b"fake-image",
            format="jpeg",
            api_url="https://ocr.test/invoke",
            secret_key="secret",
        )

    assert text == "왕교자\n1,200\n계란"
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["headers"]["X-OCR-SECRET"] == "secret"
    message = call_kwargs["data"]["message"]
    assert '"format": "jpg"' in message  # jpeg → jpg


@pytest.mark.asyncio
async def test_extract_text_http_error_raises():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await extract_text(
                b"x",
                format="png",
                api_url="https://ocr.test/invoke",
                secret_key="secret",
            )

    assert exc_info.value.code == ErrorCode.OCR_FAILED


@pytest.mark.asyncio
async def test_extract_text_non_200_raises():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "boom"
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await extract_text(
                b"x",
                format="png",
                api_url="https://ocr.test/invoke",
                secret_key="secret",
            )

    assert exc_info.value.code == ErrorCode.OCR_FAILED
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/unit/test_ocr_naver_client.py -v`

Expected: FAIL (import)

- [ ] **Step 3: Implement naver_client**

`src/domains/ocr/naver_client.py`:

```python
import json
import time
import uuid

import httpx

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException

_FORMAT_MAP = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}


async def extract_text(
    image_bytes: bytes,
    *,
    format: str,
    api_url: str,
    secret_key: str,
) -> str:
    if not api_url or not secret_key:
        raise ExternalServiceException(
            detail="Naver OCR 설정이 없습니다.",
            code=ErrorCode.OCR_FAILED,
        )

    clova_format = _FORMAT_MAP.get(format.lower())
    if clova_format is None:
        raise ExternalServiceException(
            detail="지원하지 않는 이미지 형식입니다.",
            code=ErrorCode.OCR_FAILED,
        )

    message = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{"format": clova_format, "name": "receipt"}],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                headers={"X-OCR-SECRET": secret_key},
                data={"message": json.dumps(message)},
                files={"file": ("receipt." + clova_format, image_bytes, f"image/{format}")},
            )
    except httpx.HTTPError as exc:
        raise ExternalServiceException(
            detail="Naver OCR 서버와 통신에 실패했습니다.",
            code=ErrorCode.OCR_FAILED,
        ) from exc

    if response.status_code != httpx.codes.OK:
        raise ExternalServiceException(
            detail="Naver OCR 요청이 실패했습니다.",
            code=ErrorCode.OCR_FAILED,
        )

    try:
        payload = response.json()
        fields = payload["images"][0].get("fields") or []
        lines = [f.get("inferText", "").strip() for f in fields]
        return "\n".join(line for line in lines if line)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExternalServiceException(
            detail="Naver OCR 응답을 해석하지 못했습니다.",
            code=ErrorCode.OCR_FAILED,
        ) from exc
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/unit/test_ocr_naver_client.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시에만)

```bash
git add src/domains/ocr/naver_client.py tests/unit/test_ocr_naver_client.py
git commit -m "feat(ocr): Naver CLOVA OCR 클라이언트 추가"
```

---

### Task 4: OcrService (TDD)

**Files:**
- Create: `src/domains/ocr/service.py`
- Create: `tests/unit/test_ocr_service.py`

**Interfaces:**
- Produces: `class OcrService` with `async def parse_receipt(self, image_bytes: bytes, content_type: str | None, filename: str | None) -> OcrReceiptResponse`
- Consumes: `extract_text`, `parse_receipt_text`, `settings` (또는 생성자 주입)
- 허용 MIME: `image/jpeg`, `image/jpg`, `image/png`, `image/webp`
- 크기: `len(image_bytes) > 10 * 1024 * 1024` → `BadRequestException`
- MIME/확장자 불가 → `BadRequestException`

생성자 주입으로 테스트 가능하게:

```python
class OcrService:
    def __init__(
        self,
        *,
        api_url: str,
        secret_key: str,
        openai_api_key: str,
        llm_model: str,
        extract_text_fn=extract_text,
        parse_receipt_text_fn=parse_receipt_text,
    ): ...
```

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ocr_service.py`:

```python
from unittest.mock import AsyncMock

import pytest

from core.exception.exceptions import BadRequestException
from domains.ocr.service import OcrService


@pytest.mark.asyncio
async def test_parse_receipt_happy_path():
    extract = AsyncMock(return_value="왕교자\n계란")
    parse = AsyncMock(return_value=["왕교자", "계란"])
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract,
        parse_receipt_text_fn=parse,
    )

    result = await service.parse_receipt(
        b"img",
        content_type="image/jpeg",
        filename="receipt.jpg",
    )

    assert result.ingredients == ["왕교자", "계란"]
    extract.assert_awaited_once()
    parse.assert_awaited_once_with(
        "왕교자\n계란",
        api_key="openai",
        model="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_parse_receipt_rejects_oversize():
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/png",
            filename="big.png",
        )


@pytest.mark.asyncio
async def test_parse_receipt_rejects_bad_type():
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x",
            content_type="application/pdf",
            filename="a.pdf",
        )
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/unit/test_ocr_service.py -v`

Expected: FAIL (import)

- [ ] **Step 3: Implement service**

`src/domains/ocr/service.py`:

```python
from collections.abc import Awaitable, Callable

from core.exception.exceptions import BadRequestException
from domains.ocr.llm_parser import parse_receipt_text
from domains.ocr.naver_client import extract_text
from domains.ocr.schemas import OcrReceiptResponse

MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MIME_TO_FORMAT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_EXT_TO_FORMAT = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".webp": "webp",
}

ExtractTextFn = Callable[..., Awaitable[str]]
ParseReceiptTextFn = Callable[..., Awaitable[list[str]]]


class OcrService:
    def __init__(
        self,
        *,
        api_url: str,
        secret_key: str,
        openai_api_key: str,
        llm_model: str,
        extract_text_fn: ExtractTextFn = extract_text,
        parse_receipt_text_fn: ParseReceiptTextFn = parse_receipt_text,
    ) -> None:
        self._api_url = api_url
        self._secret_key = secret_key
        self._openai_api_key = openai_api_key
        self._llm_model = llm_model
        self._extract_text = extract_text_fn
        self._parse_receipt_text = parse_receipt_text_fn

    def _resolve_format(
        self, content_type: str | None, filename: str | None
    ) -> str:
        if content_type:
            fmt = _MIME_TO_FORMAT.get(content_type.lower())
            if fmt:
                return fmt
        if filename and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
            fmt = _EXT_TO_FORMAT.get(ext)
            if fmt:
                return fmt
        raise BadRequestException(detail="지원하지 않는 이미지 형식입니다.")

    async def parse_receipt(
        self,
        image_bytes: bytes,
        content_type: str | None,
        filename: str | None,
    ) -> OcrReceiptResponse:
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise BadRequestException(detail="이미지 크기는 10MB 이하여야 합니다.")
        if not image_bytes:
            raise BadRequestException(detail="이미지 파일이 비어 있습니다.")

        image_format = self._resolve_format(content_type, filename)
        ocr_text = await self._extract_text(
            image_bytes,
            format=image_format,
            api_url=self._api_url,
            secret_key=self._secret_key,
        )
        ingredients = await self._parse_receipt_text(
            ocr_text,
            api_key=self._openai_api_key,
            model=self._llm_model,
        )
        return OcrReceiptResponse(ingredients=ingredients)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/unit/test_ocr_service.py tests/unit/test_ocr_llm_parser.py tests/unit/test_ocr_naver_client.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시에만)

```bash
git add src/domains/ocr/service.py tests/unit/test_ocr_service.py
git commit -m "feat(ocr): OCR→LLM 오케스트레이션 서비스 추가"
```

---

### Task 5: Endpoint · deps · API 테스트

**Files:**
- Create: `src/api/v1/endpoints/ocr.py`
- Modify: `src/api/deps.py`
- Modify: `src/api/api.py`
- Create: `tests/api/test_ocr_api.py`

**Interfaces:**
- Produces: `POST /api/v1/ocr/receipt` → `OcrReceiptResponse`
- Produces: `get_ocr_service() -> OcrService` (JWT `get_current_user` 의존 — 인증만 강제, user는 서비스에 불필요하지만 Depends로 게이트)
- Consumes: Task 4 `OcrService`

- [ ] **Step 1: Write the failing API tests**

`tests/api/test_ocr_api.py`:

```python
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from api.deps import get_ocr_service
from core.exception.codes import ErrorCode
from domains.ocr.schemas import OcrReceiptResponse
from main import app


async def test_ocr_receipt_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/ocr/receipt",
        files={"image": ("r.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_ocr_receipt_success(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock_service = AsyncMock()
    mock_service.parse_receipt = AsyncMock(
        return_value=OcrReceiptResponse(ingredients=["왕교자", "계란"])
    )
    app.dependency_overrides[get_ocr_service] = lambda: mock_service
    try:
        response = await client.post(
            "/api/v1/ocr/receipt",
            headers=auth_headers,
            files={"image": ("receipt.jpg", b"fake-bytes", "image/jpeg")},
        )
    finally:
        app.dependency_overrides.pop(get_ocr_service, None)

    assert response.status_code == 200
    assert response.json() == {"ingredients": ["왕교자", "계란"]}
    mock_service.parse_receipt.assert_awaited_once()
    args = mock_service.parse_receipt.await_args.args
    assert args[0] == b"fake-bytes"


async def test_ocr_receipt_rejects_missing_file(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.post(
        "/api/v1/ocr/receipt",
        headers=auth_headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run API tests — expect FAIL**

Run: `uv run pytest tests/api/test_ocr_api.py -v`

Expected: FAIL (404 또는 import — 라우트 없음)

- [ ] **Step 3: Implement endpoint + wiring**

`src/api/v1/endpoints/ocr.py`:

```python
from fastapi import APIRouter, Depends, File, UploadFile, status

from api.deps import get_current_user, get_ocr_service
from core.exception.exceptions import (
    BadRequestException,
    ExternalServiceException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ocr.schemas import OcrReceiptResponse
from domains.ocr.service import OcrService
from domains.user.model import User

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post(
    "/receipt",
    status_code=status.HTTP_200_OK,
    response_model=OcrReceiptResponse,
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ExternalServiceException,
    ),
)
async def parse_receipt(
    image: UploadFile = File(...),
    _: User = Depends(get_current_user),
    service: OcrService = Depends(get_ocr_service),
) -> OcrReceiptResponse:
    image_bytes = await image.read()
    return await service.parse_receipt(
        image_bytes,
        content_type=image.content_type,
        filename=image.filename,
    )
```

`src/api/deps.py` — imports와 factory 추가:

```python
from domains.ocr.service import OcrService
from core.config import settings

def get_ocr_service(
    _: User = Depends(get_current_user),
) -> OcrService:
    return OcrService(
        api_url=settings.NAVER_OCR_API_URL,
        secret_key=settings.NAVER_OCR_SECRET_KEY.get_secret_value(),
        openai_api_key=settings.OPENAI_API_KEY.get_secret_value(),
        llm_model=settings.OCR_LLM_MODEL,
    )
```

참고: endpoint에서도 `get_current_user`를 쓰면 이중 호출된다. **둘 중 하나만** 쓰도록 정리한다.

권장: endpoint는 `service: OcrService = Depends(get_ocr_service)`만 두고, `get_ocr_service` 안에서 `get_current_user`로 인증 게이트. endpoint의 `_` 파라미터와 `get_current_user` import는 제거.

`src/api/api.py`:

```python
from api.v1.endpoints.ocr import router as ocr_router
# ...
api_router.include_router(ocr_router)
```

- [ ] **Step 4: Run all OCR tests — expect PASS**

Run: `uv run pytest tests/unit/test_ocr_*.py tests/api/test_ocr_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시에만)

```bash
git add src/api/v1/endpoints/ocr.py src/api/deps.py src/api/api.py tests/api/test_ocr_api.py
git commit -m "feat(ocr): 영수증 OCR 식재료 추출 API 추가"
```

---

## Verification

```bash
uv run pytest tests/unit/test_ocr_llm_parser.py tests/unit/test_ocr_naver_client.py tests/unit/test_ocr_service.py tests/api/test_ocr_api.py -v
uv run pytest tests/unit/test_rag_retriever.py -v
```

수동(선택): `.env`에 실제 `NAVER_OCR_API_URL`, `NAVER_OCR_SECRET_KEY`, `OPENAI_API_KEY`를 넣고 multipart로 `POST /api/v1/ocr/receipt` 호출.

---

## Spec Coverage Checklist

| Spec 항목 | Task |
|-----------|------|
| `POST /ocr/receipt` multipart | Task 5 |
| JWT 필수 | Task 5 (`get_ocr_service` → `get_current_user`) |
| jpg/png/webp, 10MB | Task 4 |
| Naver CLOVA OCR | Task 3 |
| OpenAI Chat 필터·정규화 | Task 2 |
| 응답 `{ ingredients }` only, DB 없음 | Task 4–5 |
| `OCR_FAILED` / `OCR_LLM_FAILED` | Task 1–3 |
| 빈 배열 200 | Task 2 (+ API는 서비스 결과 그대로) |
| 45자 truncate | Task 2 |
| config env | Task 1 |
