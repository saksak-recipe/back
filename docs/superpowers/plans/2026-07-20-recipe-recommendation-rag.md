# Recipe Recommendation RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인한 사용자의 식재료로 PGVector에서 유사 레시피 top-5를 검색해 `GET /api/v1/recipes/recommendations`로 반환한다.

**Architecture:** JWT로 식재료를 앱 DB에서 읽고, `parsed_ingredients: ...` 쿼리로 `text-embedding-3-small` + `recipe_vectors` similarity 검색한다. LLM은 쓰지 않는다. Sync PGVector는 `asyncio.to_thread`로 감싼다.

**Tech Stack:** FastAPI, SQLAlchemy async, LangChain `OpenAIEmbeddings` + `PGVector`, `psycopg`, pytest/httpx

**Spec:** `docs/superpowers/specs/2026-07-20-recipe-recommendation-rag-design.md`

## Global Constraints

- 반환 개수 고정 5개 (`k=5`)
- LLM 호출 금지 (임베딩만)
- 프론트엔드 변경 금지
- score는 distance float (작을수록 유사)
- 식재료 0개면 임베딩/DB 미호출, 빈 배열 200
- Collection: `recipe_vectors`, model: `text-embedding-3-small`
- 커밋 메시지 스타일: `Feat:` / `Test:` / `Docs:` / `refact:` (기존 저장소)

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/core/config.py` | `database_rag_sync_url` 추가 (기존 `OPENAI_API_KEY`, `database_rag_url` 유지) |
| `src/domains/rag/schemas.py` | 응답 DTO |
| `src/domains/rag/mapper.py` | page_content 파싱 + Document→DTO |
| `src/domains/rag/retriever.py` | Embeddings + PGVector 검색 |
| `src/domains/rag/service.py` | 식재료 조회 → 검색 → 매핑 |
| `src/api/v1/endpoints/rag.py` | HTTP 엔드포인트 |
| `src/api/deps.py` | `get_rag_service` |
| `src/api/api.py` | rag 라우터 등록 (이미 uncommitted로 추가됨 — 유지) |
| `tests/conftest.py` | `OPENAI_API_KEY` env 추가 |
| `tests/unit/test_rag_mapper.py` | 파싱 단위 테스트 |
| `tests/unit/test_rag_service.py` | 서비스 단위 테스트 |
| `tests/api/test_rag_api.py` | API 테스트 |

---

### Task 1: Config sync URL + 테스트 env

**Files:**
- Modify: `src/core/config.py`
- Modify: `tests/conftest.py`
- Modify (이미 있으면 유지): `pyproject.toml` (langchain-* / openai), `uv.lock`

**Interfaces:**
- Produces: `Settings.database_rag_sync_url -> str` (`postgresql+psycopg://.../saksak_rag`)

- [ ] **Step 1: `OPENAI_API_KEY`를 conftest에 추가**

`tests/conftest.py` 상단 env 설정 블록에 다음을 넣는다 (`JWT_SECRET_KEY` 설정 바로 아래):

```python
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
```

`Settings`가 `OPENAI_API_KEY`를 필수로 읽으므로, `from main import app` 전에 반드시 설정되어야 한다.

- [ ] **Step 2: `database_rag_sync_url` 추가**

`src/core/config.py`의 `database_rag_url` 아래에:

```python
@property
def database_rag_sync_url(self) -> str:
    return (
        f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD.get_secret_value()}"
        f"@{self.DB_HOST}:{self.DB_PORT}/saksak_rag"
    )
```

`OPENAI_API_KEY: SecretStr`와 `database_rag_url`이 아직 없으면 함께 추가한다 (현재 working tree에 이미 있을 수 있음).

- [ ] **Step 3: 의존성 확인**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv sync
python -c "from langchain_postgres import PGVector; from langchain_openai import OpenAIEmbeddings; import psycopg; print('ok')"
```

Expected: `ok`. `psycopg`가 없으면:

```bash
uv add "psycopg[binary]"
```

- [ ] **Step 4: Commit**

```bash
git add src/core/config.py tests/conftest.py pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
Feat: RAG용 sync DB URL 및 OpenAI 설정 준비

EOF
)"
```

---

### Task 2: Schemas + Document mapper (TDD)

**Files:**
- Create: `src/domains/rag/schemas.py`
- Create: `src/domains/rag/mapper.py`
- Create: `tests/unit/test_rag_mapper.py`
- Create (필요 시): `src/domains/rag/__init__.py` (빈 파일)

**Interfaces:**
- Produces:
  - `RecipeRecommendation(recipe_name, parsed_ingredients, board_name, author_name, recipe_difficulty, time, score: float)`
  - `RecipeRecommendationResponse(ingredients_used: list[str], recipes: list[RecipeRecommendation])`
  - `build_ingredient_query(names: list[str]) -> str`
  - `parse_page_content(page_content: str) -> tuple[str, str]`  # (recipe_name, parsed_ingredients)
  - `map_document_to_recipe(doc, score: float) -> RecipeRecommendation | None`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rag_mapper.py`:

```python
from langchain_core.documents import Document

from domains.rag.mapper import (
    build_ingredient_query,
    map_document_to_recipe,
    parse_page_content,
)


def test_build_ingredient_query():
    assert (
        build_ingredient_query(["계란", "양파"])
        == "parsed_ingredients: 계란, 양파"
    )


def test_parse_page_content():
    name, ingredients = parse_page_content(
        "recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 밥, 대파"
    )
    assert name == "계란볶음밥"
    assert ingredients == "계란, 밥, 대파"


def test_parse_page_content_missing_fields_returns_empty():
    name, ingredients = parse_page_content("garbage")
    assert name == ""
    assert ingredients == ""


def test_map_document_to_recipe():
    doc = Document(
        page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 밥",
        metadata={
            "board_name": "한식",
            "author_name": "kim",
            "recipe_difficulty": "초급",
            "time": "15분",
        },
    )
    recipe = map_document_to_recipe(doc, 0.42)
    assert recipe is not None
    assert recipe.recipe_name == "계란볶음밥"
    assert recipe.parsed_ingredients == "계란, 밥"
    assert recipe.board_name == "한식"
    assert recipe.author_name == "kim"
    assert recipe.recipe_difficulty == "초급"
    assert recipe.time == "15분"
    assert recipe.score == 0.42


def test_map_document_skips_when_recipe_name_empty():
    doc = Document(page_content="parsed_ingredients: only", metadata={})
    assert map_document_to_recipe(doc, 0.1) is None
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_rag_mapper.py -v
```

Expected: FAIL (`ModuleNotFoundError` or import error)

- [ ] **Step 3: Implement schemas**

Create `src/domains/rag/schemas.py`:

```python
from pydantic import BaseModel, Field


class RecipeRecommendation(BaseModel):
    recipe_name: str
    parsed_ingredients: str
    board_name: str = ""
    author_name: str = ""
    recipe_difficulty: str = ""
    time: str = ""
    score: float = Field(
        description="PGVector distance. Smaller means more similar."
    )


class RecipeRecommendationResponse(BaseModel):
    ingredients_used: list[str]
    recipes: list[RecipeRecommendation]
```

- [ ] **Step 4: Implement mapper**

Create `src/domains/rag/mapper.py`:

```python
from langchain_core.documents import Document

from domains.rag.schemas import RecipeRecommendation


def build_ingredient_query(names: list[str]) -> str:
    return "parsed_ingredients: " + ", ".join(names)


def parse_page_content(page_content: str) -> tuple[str, str]:
    recipe_name = ""
    parsed_ingredients = ""
    for line in page_content.splitlines():
        if line.startswith("recipe_name:"):
            recipe_name = line.removeprefix("recipe_name:").strip()
        elif line.startswith("parsed_ingredients:"):
            parsed_ingredients = line.removeprefix("parsed_ingredients:").strip()
    return recipe_name, parsed_ingredients


def map_document_to_recipe(
    doc: Document, score: float
) -> RecipeRecommendation | None:
    recipe_name, parsed_ingredients = parse_page_content(doc.page_content)
    if not recipe_name:
        return None
    meta = doc.metadata or {}
    return RecipeRecommendation(
        recipe_name=recipe_name,
        parsed_ingredients=parsed_ingredients,
        board_name=str(meta.get("board_name", "") or ""),
        author_name=str(meta.get("author_name", "") or ""),
        recipe_difficulty=str(meta.get("recipe_difficulty", "") or ""),
        time=str(meta.get("time", "") or ""),
        score=float(score),
    )
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_rag_mapper.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add src/domains/rag/schemas.py src/domains/rag/mapper.py src/domains/rag/__init__.py tests/unit/test_rag_mapper.py
git commit -m "$(cat <<'EOF'
Feat: RAG 레시피 DTO 및 Document 매퍼 추가

EOF
)"
```

---

### Task 3: Retriever

**Files:**
- Create: `src/domains/rag/retriever.py`
- Create: `tests/unit/test_rag_retriever.py`

**Interfaces:**
- Consumes: `settings.OPENAI_API_KEY`, `settings.database_rag_sync_url`
- Produces:
  - `class RecipeRetriever`
  - `RecipeRetriever.search(query: str, k: int = 5) -> list[tuple[Document, float]]`
  - `get_recipe_retriever() -> RecipeRetriever` (lazy singleton ok)

- [ ] **Step 1: Write failing test (mock PGVector)**

Create `tests/unit/test_rag_retriever.py`:

```python
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from domains.rag.retriever import RecipeRetriever


def test_search_delegates_to_vector_store():
    store = MagicMock()
    doc = Document(page_content="recipe_name: a\nparsed_ingredients: b")
    store.similarity_search_with_score.return_value = [(doc, 0.3)]

    retriever = RecipeRetriever(vector_store=store)
    result = retriever.search("parsed_ingredients: 계란", k=5)

    store.similarity_search_with_score.assert_called_once_with(
        "parsed_ingredients: 계란", k=5
    )
    assert result == [(doc, 0.3)]
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run pytest tests/unit/test_rag_retriever.py -v
```

Expected: FAIL (import error)

- [ ] **Step 3: Implement retriever**

Create `src/domains/rag/retriever.py`:

```python
from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from core.config import settings
from core.exception.exceptions import DatabaseException, ExternalServiceException


class RecipeRetriever:
    def __init__(self, vector_store: PGVector):
        self._vector_store = vector_store

    def search(self, query: str, k: int = 5) -> list[tuple[Document, float]]:
        try:
            return self._vector_store.similarity_search_with_score(query, k=k)
        except Exception as e:
            message = str(e).lower()
            if "openai" in message or "embedding" in message or "api" in message:
                raise ExternalServiceException(
                    detail="레시피 임베딩 요청 중 오류가 발생했습니다."
                ) from e
            raise DatabaseException(
                detail="레시피 벡터 검색 중 DB 오류가 발생했습니다."
            ) from e


@lru_cache
def get_recipe_retriever() -> RecipeRetriever:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
    )
    vector_store = PGVector(
        embeddings=embeddings,
        connection=settings.database_rag_sync_url,
        collection_name="recipe_vectors",
    )
    return RecipeRetriever(vector_store=vector_store)
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest tests/unit/test_rag_retriever.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/rag/retriever.py tests/unit/test_rag_retriever.py
git commit -m "$(cat <<'EOF'
Feat: PGVector RecipeRetriever 추가

EOF
)"
```

---

### Task 4: RagService (TDD)

**Files:**
- Create: `src/domains/rag/service.py`
- Create: `tests/unit/test_rag_service.py`

**Interfaces:**
- Consumes: `IngredientRepository.get_ingredients(user_id)`, `RecipeRetriever.search`, mapper helpers
- Produces:
  - `class RagService`
  - `async def recommend_recipes(self) -> RecipeRecommendationResponse`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rag_service.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
import uuid6
from langchain_core.documents import Document

from domains.ingredient.model import Ingredient
from domains.rag.retriever import RecipeRetriever
from domains.rag.service import RagService
from domains.user.model import User


@pytest.fixture
def user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password="hashed",
        nickname="testuser",
    )


@pytest.fixture
def ingredient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def retriever() -> MagicMock:
    return MagicMock(spec=RecipeRetriever)


@pytest.fixture
def rag_service(user, ingredient_repo, retriever) -> RagService:
    return RagService(
        user=user,
        ingredient_repo=ingredient_repo,
        retriever=retriever,
    )


async def test_recommend_returns_empty_when_no_ingredients(
    rag_service: RagService, ingredient_repo: AsyncMock, retriever: MagicMock
):
    ingredient_repo.get_ingredients.return_value = []

    result = await rag_service.recommend_recipes()

    assert result.ingredients_used == []
    assert result.recipes == []
    retriever.search.assert_not_called()


async def test_recommend_maps_search_results(
    rag_service: RagService,
    ingredient_repo: AsyncMock,
    retriever: MagicMock,
    user: User,
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="계란",
            purchase_date=date.today(),
        ),
        Ingredient(
            id=2,
            user_id=user.id,
            ingredient_name="양파",
            purchase_date=date.today(),
        ),
    ]
    doc = Document(
        page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 양파, 밥",
        metadata={
            "board_name": "한식",
            "author_name": "kim",
            "recipe_difficulty": "초급",
            "time": "15분",
        },
    )
    retriever.search.return_value = [(doc, 0.2)]

    result = await rag_service.recommend_recipes()

    assert result.ingredients_used == ["계란", "양파"]
    assert len(result.recipes) == 1
    assert result.recipes[0].recipe_name == "계란볶음밥"
    assert result.recipes[0].score == 0.2
    retriever.search.assert_called_once_with(
        "parsed_ingredients: 계란, 양파", k=5
    )


async def test_recommend_skips_unparsable_documents(
    rag_service: RagService,
    ingredient_repo: AsyncMock,
    retriever: MagicMock,
    user: User,
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="계란",
            purchase_date=date.today(),
        )
    ]
    bad = Document(page_content="no name here", metadata={})
    good = Document(
        page_content="recipe_name: 된장찌개\nparsed_ingredients: 계란",
        metadata={},
    )
    retriever.search.return_value = [(bad, 0.9), (good, 0.5)]

    result = await rag_service.recommend_recipes()

    assert len(result.recipes) == 1
    assert result.recipes[0].recipe_name == "된장찌개"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/unit/test_rag_service.py -v
```

Expected: FAIL (import error)

- [ ] **Step 3: Implement service**

Create `src/domains/rag/service.py`:

```python
import asyncio

from domains.ingredient.repository import IngredientRepository
from domains.rag.mapper import build_ingredient_query, map_document_to_recipe
from domains.rag.retriever import RecipeRetriever
from domains.rag.schemas import RecipeRecommendationResponse
from domains.user.model import User

TOP_K = 5


class RagService:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        retriever: RecipeRetriever,
    ):
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.retriever = retriever

    async def recommend_recipes(self) -> RecipeRecommendationResponse:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return RecipeRecommendationResponse(ingredients_used=[], recipes=[])

        query = build_ingredient_query(names)
        docs_with_scores = await asyncio.to_thread(
            self.retriever.search, query, TOP_K
        )

        recipes = []
        for doc, score in docs_with_scores:
            mapped = map_document_to_recipe(doc, score)
            if mapped is not None:
                recipes.append(mapped)

        return RecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_rag_service.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/domains/rag/service.py tests/unit/test_rag_service.py
git commit -m "$(cat <<'EOF'
Feat: RagService 식재료 기반 레시피 추천 로직

EOF
)"
```

---

### Task 5: Endpoint + DI

**Files:**
- Create: `src/api/v1/endpoints/rag.py`
- Modify: `src/api/deps.py`
- Modify: `src/api/api.py` (rag 라우터 include — 이미 있으면 유지)

**Interfaces:**
- Consumes: `RagService.recommend_recipes`
- Produces: `GET /api/v1/recipes/recommendations` → `RecipeRecommendationResponse`
- Produces: `get_rag_service(...) -> RagService`

- [ ] **Step 1: Add DI in deps.py**

`src/api/deps.py`에 추가:

```python
from domains.rag.retriever import RecipeRetriever, get_recipe_retriever
from domains.rag.service import RagService


def get_rag_retriever() -> RecipeRetriever:
    return get_recipe_retriever()


def get_rag_service(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
    retriever: RecipeRetriever = Depends(get_rag_retriever),
) -> RagService:
    return RagService(
        user=user,
        ingredient_repo=ingredient_repo,
        retriever=retriever,
    )
```

기존 import/`get_current_user`/`get_ingredient_repo`와 충돌 없이 추가한다.

- [ ] **Step 2: Create endpoint**

Create `src/api/v1/endpoints/rag.py`:

```python
from fastapi import APIRouter, Depends, status

from api.deps import get_rag_service
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.rag.schemas import RecipeRecommendationResponse
from domains.rag.service import RagService

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get(
    "/recommendations",
    status_code=status.HTTP_200_OK,
    response_model=RecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def recommend_recipes(
    service: RagService = Depends(get_rag_service),
) -> RecipeRecommendationResponse:
    return await service.recommend_recipes()
```

- [ ] **Step 3: Ensure api.py includes rag router**

`src/api/api.py`가 다음을 포함해야 한다:

```python
from api.v1.endpoints.rag import router as rag_router
# ...
api_router.include_router(rag_router)
```

- [ ] **Step 4: Smoke import**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run python -c "from main import app; print([r.path for r in app.routes if 'recommend' in getattr(r,'path','')])"
```

Expected: `['/api/v1/recipes/recommendations']` (또는 유사)

- [ ] **Step 5: Commit**

```bash
git add src/api/v1/endpoints/rag.py src/api/deps.py src/api/api.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 추천 GET 엔드포인트 추가

EOF
)"
```

---

### Task 6: API tests

**Files:**
- Create: `tests/api/test_rag_api.py`
- Modify: `tests/conftest.py` (필요 시 rag retriever override helper — 아래 테스트에서 직접 override)

**Interfaces:**
- Consumes: HTTP client + `app.dependency_overrides[get_rag_retriever]`

- [ ] **Step 1: Write API tests**

Create `tests/api/test_rag_api.py`:

```python
from unittest.mock import MagicMock

from httpx import AsyncClient
from langchain_core.documents import Document

from api.deps import get_rag_retriever
from core.exception.codes import ErrorCode
from main import app


async def test_recommendations_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/recipes/recommendations")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_recommendations_empty_when_no_ingredients(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock_retriever = MagicMock()
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ingredients_used"] == []
        assert body["recipes"] == []
        mock_retriever.search.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_returns_mapped_recipes(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["계란", "양파"]},
    )

    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [
        (
            Document(
                page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 양파, 밥",
                metadata={
                    "board_name": "한식",
                    "author_name": "kim",
                    "recipe_difficulty": "초급",
                    "time": "15분",
                },
            ),
            0.25,
        )
    ]
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body["ingredients_used"]) == {"계란", "양파"}
        assert len(body["recipes"]) == 1
        assert body["recipes"][0]["recipe_name"] == "계란볶음밥"
        assert body["recipes"][0]["score"] == 0.25
        mock_retriever.search.assert_called_once()
        called_query = mock_retriever.search.call_args.args[0]
        assert "계란" in called_query and "양파" in called_query
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)
```

- [ ] **Step 2: Run API + unit suite**

```bash
uv run pytest tests/api/test_rag_api.py tests/unit/test_rag_mapper.py tests/unit/test_rag_retriever.py tests/unit/test_rag_service.py -v
```

Expected: all PASS

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: all PASS (기존 테스트 회귀 없음)

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_rag_api.py
git commit -m "$(cat <<'EOF'
Test: 레시피 추천 API 테스트 추가

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 요구 | Task |
|-----------|------|
| GET `/api/v1/recipes/recommendations` + JWT | 5, 6 |
| top-5, score 포함 | 4 (`TOP_K=5`), 2 (schema) |
| 빈 식재료 early return | 4, 6 |
| `text-embedding-3-small` + `recipe_vectors` | 3 |
| sync PGVector + `to_thread` | 3, 4 |
| ExternalServiceException / DatabaseException | 3 |
| 파싱 실패 스킵 | 2, 4 |
| 프론트 제외 | 전 task (프론트 파일 없음) |
| `database_rag_sync_url` | 1 |

## Execution Handoff

Plan complete. Choose execution mode when ready.
