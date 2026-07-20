# Recipe Detail 10000recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `board_name` + `author_name`으로 만개의 레시피를 검색·매칭해 재료·조리순서·팁·사진을 반환하는 상세 API와, 앱의 추천 목록·상세 화면을 만든다.

**Architecture:** 백엔드 `RecipeDetailService`가 인메모리 TTL(24h) 캐시를 보고, miss 시 `RecipeCrawler`가 검색→매칭→상세 파싱(`ld+json` 우선)한다. 앱은 기존 recommendations + 신규 detail API를 TanStack Query로 호출한다.

**Tech Stack:** FastAPI, httpx, BeautifulSoup4, pytest; Expo Router, TanStack Query, Axios, expo-image

**Spec:** `docs/superpowers/specs/2026-07-20-recipe-detail-10000recipe-design.md`

## Global Constraints

- 레시피 식별: `board_name` + `author_name` 검색 (RCP_SNO 재적재 금지)
- 크롤은 백엔드만; 앱에서 만개의 레시피 직접 fetch 금지
- 매칭: 최고 1건 자동 선택; 채택 조건 불충족 시 404 (`NotFoundException`)
- 외부 타임아웃/파싱 실패: 502 (`ExternalServiceException`)
- 캐시: 인메모리 TTL 24시간; Redis/DB 캐시 금지
- 요청 타임아웃: 10초; User-Agent 명시; 동시 크롤 세마포어
- 기존 `GET /recipes/recommendations` 응답 스키마 변경 금지
- 커밋 메시지 스타일: `Feat:` / `Test:` / `Docs:` / `Fix:` (기존 저장소)
- 앱 카피: 404 → “해당 레시피를 찾지 못했어요”; 502/네트워크 → “레시피를 불러오지 못했어요. 다시 시도해 주세요”

## File Structure

### Backend (`/Users/jeong-yeonghun/Desktop/saksak/back`)

| Path | Responsibility |
|------|----------------|
| `src/domains/recipe_detail/schemas.py` | 상세 응답 DTO |
| `src/domains/recipe_detail/normalize.py` | 문자열 정규화 |
| `src/domains/recipe_detail/matcher.py` | 검색 후보 점수·채택 |
| `src/domains/recipe_detail/cache.py` | TTL 인메모리 캐시 |
| `src/domains/recipe_detail/crawler.py` | HTTP + HTML/`ld+json` 파싱 |
| `src/domains/recipe_detail/service.py` | 캐시 오케스트레이션 |
| `src/api/v1/endpoints/rag.py` | `GET /recipes/detail` 추가 (동일 prefix) |
| `src/api/deps.py` | `get_recipe_detail_service` |
| `tests/fixtures/10000recipe_search.html` | 검색 픽스처 |
| `tests/fixtures/10000recipe_detail.html` | 상세 픽스처 |
| `tests/unit/test_recipe_detail_*.py` | 단위 테스트 |
| `tests/api/test_recipe_detail_api.py` | API 테스트 |
| `pyproject.toml` / `uv.lock` | `beautifulsoup4`, `httpx`(런타임) |

### Frontend (`/Users/jeong-yeonghun/Desktop/saksak/app`)

| Path | Responsibility |
|------|----------------|
| `src/types/api.ts` | 추천·상세 타입 |
| `src/api/recipes.ts` | API 클라이언트 |
| `src/app/(main)/recipes/index.tsx` | 추천 목록 |
| `src/app/(main)/recipes/detail.tsx` | 상세 화면 |
| `src/app/(main)/_layout.tsx` | Stack 스크린 등록 |
| `src/app/(main)/index.tsx` | 레시피 진입 버튼 |
| `src/components/RecipeCard.tsx` | 목록 카드 |
| `package.json` | `expo-image` 추가 |

---

### Task 1: Schemas + normalize + matcher (TDD)

**Files:**
- Create: `src/domains/recipe_detail/__init__.py` (빈 파일)
- Create: `src/domains/recipe_detail/schemas.py`
- Create: `src/domains/recipe_detail/normalize.py`
- Create: `src/domains/recipe_detail/matcher.py`
- Create: `tests/unit/test_recipe_detail_matcher.py`

**Interfaces:**
- Produces:
  - `RecipeIngredient(name: str, amount: str = "")`
  - `RecipeStep(order: int, description: str, tip: str | None = None, image_url: str | None = None)`
  - `RecipeDetailResponse(board_name, author_name, recipe_name, source_url, main_image_url: str | None, ingredients: list[RecipeIngredient], steps: list[RecipeStep], tips: list[str], cached: bool)`
  - `SearchCandidate(recipe_id: str, title: str, author: str)`
  - `normalize_text(value: str) -> str`
  - `pick_best_candidate(candidates: list[SearchCandidate], board_name: str, author_name: str) -> SearchCandidate | None`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_recipe_detail_matcher.py`:

```python
from domains.recipe_detail.matcher import SearchCandidate, pick_best_candidate
from domains.recipe_detail.normalize import normalize_text


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("  GP하루한끼  ") == "gp하루한끼"
    assert normalize_text("A  B") == "a b"


def test_pick_best_prefers_author_and_title_match():
    candidates = [
        SearchCandidate("1", "다른 요리", "다른작성자"),
        SearchCandidate(
            "6891574",
            "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
            "GP하루한끼",
        ),
        SearchCandidate("2", "닭꼬치", "GP하루한끼"),
    ]
    best = pick_best_candidate(
        candidates,
        board_name="아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
        author_name="GP하루한끼",
    )
    assert best is not None
    assert best.recipe_id == "6891574"


def test_pick_best_returns_none_without_author_or_title_overlap():
    candidates = [
        SearchCandidate("1", "완전히 다른 제목", "다른사람"),
    ]
    assert (
        pick_best_candidate(candidates, "닭꼬치 레시피", "GP하루한끼") is None
    )
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_recipe_detail_matcher.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Implement schemas, normalize, matcher**

`schemas.py`:

```python
from pydantic import BaseModel, Field


class RecipeIngredient(BaseModel):
    name: str
    amount: str = ""


class RecipeStep(BaseModel):
    order: int
    description: str
    tip: str | None = None
    image_url: str | None = None


class RecipeDetailResponse(BaseModel):
    board_name: str
    author_name: str
    recipe_name: str
    source_url: str
    main_image_url: str | None = None
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    cached: bool = False
```

`normalize.py`:

```python
import re


def normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip())
    return collapsed.casefold()
```

`matcher.py`:

```python
from dataclasses import dataclass

from domains.recipe_detail.normalize import normalize_text


@dataclass(frozen=True)
class SearchCandidate:
    recipe_id: str
    title: str
    author: str


def _score(candidate: SearchCandidate, board_name: str, author_name: str) -> int | None:
    title_n = normalize_text(candidate.title)
    author_n = normalize_text(candidate.author)
    board_n = normalize_text(board_name)
    want_author = normalize_text(author_name)

    author_match = author_n == want_author and want_author != ""
    title_exact = title_n == board_n and board_n != ""
    title_contains = board_n != "" and (board_n in title_n or title_n in board_n)

    # 채택 조건: 작성자 일치 OR 제목 겹침
    if not (author_match or title_contains or title_exact):
        return None

    score = 0
    if author_match:
        score += 100
    if title_exact:
        score += 50
    elif title_contains:
        score += 25
    return score


def pick_best_candidate(
    candidates: list[SearchCandidate],
    board_name: str,
    author_name: str,
) -> SearchCandidate | None:
    ranked: list[tuple[int, SearchCandidate]] = []
    for c in candidates:
        s = _score(c, board_name, author_name)
        if s is not None:
            ranked.append((s, c))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_recipe_detail_matcher.py -v
```

- [ ] **Step 5: Commit (back)**

```bash
git add src/domains/recipe_detail tests/unit/test_recipe_detail_matcher.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 매칭·스키마 추가

EOF
)"
```

---

### Task 2: TTL cache (TDD)

**Files:**
- Create: `src/domains/recipe_detail/cache.py`
- Create: `tests/unit/test_recipe_detail_cache.py`

**Interfaces:**
- Produces:
  - `RecipeDetailCache(ttl_seconds: int = 86400)`
  - `cache_key(board_name: str, author_name: str) -> str`
  - `RecipeDetailCache.get(key: str) -> RecipeDetailResponse | None`
  - `RecipeDetailCache.set(key: str, value: RecipeDetailResponse) -> None`

- [ ] **Step 1: Write failing tests**

```python
import time

from domains.recipe_detail.cache import RecipeDetailCache, cache_key
from domains.recipe_detail.schemas import RecipeDetailResponse


def _sample(**kwargs) -> RecipeDetailResponse:
    base = dict(
        board_name="제목",
        author_name="작성자",
        recipe_name="요리",
        source_url="https://www.10000recipe.com/recipe/1",
        cached=False,
    )
    base.update(kwargs)
    return RecipeDetailResponse(**base)


def test_cache_key_normalizes():
    assert cache_key(" A ", "B") == cache_key("a", "b")


def test_cache_hit_and_miss():
    cache = RecipeDetailCache(ttl_seconds=60)
    key = cache_key("제목", "작성자")
    assert cache.get(key) is None
    cache.set(key, _sample())
    hit = cache.get(key)
    assert hit is not None
    assert hit.recipe_name == "요리"


def test_cache_expires():
    cache = RecipeDetailCache(ttl_seconds=1)
    key = cache_key("제목", "작성자")
    cache.set(key, _sample())
    time.sleep(1.1)
    assert cache.get(key) is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_recipe_detail_cache.py -v
```

- [ ] **Step 3: Implement cache**

```python
import hashlib
import time
from dataclasses import dataclass

from domains.recipe_detail.normalize import normalize_text
from domains.recipe_detail.schemas import RecipeDetailResponse


def cache_key(board_name: str, author_name: str) -> str:
    raw = f"{normalize_text(board_name)}|{normalize_text(author_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    value: RecipeDetailResponse
    expires_at: float


class RecipeDetailCache:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> RecipeDetailResponse | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value.model_copy(update={"cached": True})

    def set(self, key: str, value: RecipeDetailResponse) -> None:
        stored = value.model_copy(update={"cached": False})
        self._store[key] = _Entry(
            value=stored,
            expires_at=time.monotonic() + self._ttl,
        )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_recipe_detail_cache.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/recipe_detail/cache.py tests/unit/test_recipe_detail_cache.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 TTL 인메모리 캐시 추가

EOF
)"
```

---

### Task 3: Crawler parse helpers + fixtures (TDD)

**Files:**
- Create: `tests/fixtures/10000recipe_search.html`
- Create: `tests/fixtures/10000recipe_detail.html`
- Create: `src/domains/recipe_detail/crawler.py` (parse 함수 먼저; HTTP는 Task 4에서 연결)
- Create: `tests/unit/test_recipe_detail_crawler_parse.py`
- Modify: `pyproject.toml` — `uv add beautifulsoup4 httpx`

**Interfaces:**
- Produces:
  - `parse_search_html(html: str) -> list[SearchCandidate]`
  - `parse_detail_html(html: str, recipe_id: str) -> RecipeDetailResponse`  
    (`board_name`/`author_name`/`cached`는 호출측에서 채울 수 있게, 파서는 `recipe_name`, `source_url`, `main_image_url`, `ingredients`, `steps`, `tips` 중심; `board_name`/`author_name`은 빈 문자열 기본)

- [ ] **Step 1: Add dependencies**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv add beautifulsoup4 httpx
```

- [ ] **Step 2: Create fixtures**

`tests/fixtures/10000recipe_search.html` (최소 구조):

```html
<html><body>
<ul class="common_sp_list_ul">
  <li class="common_sp_list_li">
    <a class="common_sp_link" href="/recipe/6891574"></a>
    <div class="common_sp_caption_tit line2">아이들 영양 간식으로 좋은 닭꼬치 &amp; 콘치즈</div>
    <div class="common_sp_caption_rv_name"><b>GP하루한끼</b></div>
  </li>
  <li class="common_sp_list_li">
    <a class="common_sp_link" href="/recipe/111"></a>
    <div class="common_sp_caption_tit line2">다른 요리</div>
    <div class="common_sp_caption_rv_name"><b>다른사람</b></div>
  </li>
</ul>
</body></html>
```

`tests/fixtures/10000recipe_detail.html`:

```html
<html><head>
<script type="application/ld+json">
{
  "@type": "Recipe",
  "name": "닭꼬치",
  "author": {"name": "GP하루한끼"},
  "image": ["https://example.com/main.jpg"],
  "recipeIngredient": ["닭가슴살 200g", "대파 1대"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "재료를 준비한다.", "image": "https://example.com/s1.jpg"},
    {"@type": "HowToStep", "text": "굽는다."}
  ]
}
</script>
</head><body>
<div class="view_step">
  <div class="media view_step_cont tip_box">
    <div id="stepdesc1">재료를 준비한다.</div>
    <p class="tip">기름을 충분히 두르세요</p>
  </div>
</div>
</body></html>
```

- [ ] **Step 3: Write failing parse tests**

```python
from pathlib import Path

from domains.recipe_detail.crawler import parse_detail_html, parse_search_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_search_html_extracts_candidates():
    html = (FIXTURES / "10000recipe_search.html").read_text(encoding="utf-8")
    items = parse_search_html(html)
    assert len(items) == 2
    assert items[0].recipe_id == "6891574"
    assert "닭꼬치" in items[0].title
    assert items[0].author == "GP하루한끼"


def test_parse_detail_html_from_ld_json():
    html = (FIXTURES / "10000recipe_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_html(html, recipe_id="6891574")
    assert detail.recipe_name == "닭꼬치"
    assert detail.source_url == "https://www.10000recipe.com/recipe/6891574"
    assert detail.main_image_url == "https://example.com/main.jpg"
    assert detail.ingredients[0].name == "닭가슴살"
    assert detail.ingredients[0].amount == "200g"
    assert detail.steps[0].description == "재료를 준비한다."
    assert detail.steps[0].image_url == "https://example.com/s1.jpg"
    assert any("기름" in t for t in detail.tips) or (
        detail.steps[0].tip is not None and "기름" in detail.steps[0].tip
    )
```

- [ ] **Step 4: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_recipe_detail_crawler_parse.py -v
```

- [ ] **Step 5: Implement parse functions in `crawler.py`**

핵심 규칙:
- 검색: `li.common_sp_list_li`마다 `a.common_sp_link[href]`, `.common_sp_caption_tit`, `.common_sp_caption_rv_name b` (없으면 빈 author)
- 상세: `script[type=application/ld+json]`에서 `@type==Recipe` (또는 `@graph` 내 Recipe) 우선
- 재료 문자열 `"닭가슴살 200g"` → 마지막 토큰이 양/단위면 `amount`, 나머지는 `name` (단순 split: 첫 토큰 name, 나머지 amount)
- step tip: HTML `.view_step .tip`을 order에 매칭 가능하면 `RecipeStep.tip`, 전역이면 `tips`
- `USER_AGENT` 상수와 `BASE = "https://www.10000recipe.com"` 상수 정의 (HTTP는 Task 4)

구현 스케치:

```python
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from domains.recipe_detail.matcher import SearchCandidate
from domains.recipe_detail.schemas import (
    RecipeDetailResponse,
    RecipeIngredient,
    RecipeStep,
)

BASE_URL = "https://www.10000recipe.com"
USER_AGENT = (
    "saksak-recipe-bot/1.0 (+https://github.com/local; personal non-commercial use)"
)


def parse_search_html(html: str) -> list[SearchCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchCandidate] = []
    for li in soup.select("li.common_sp_list_li"):
        link = li.select_one("a.common_sp_link")
        if not link or not link.get("href"):
            continue
        recipe_id = link["href"].rstrip("/").split("/")[-1]
        title_el = li.select_one(".common_sp_caption_tit")
        author_el = li.select_one(".common_sp_caption_rv_name b")
        results.append(
            SearchCandidate(
                recipe_id=recipe_id,
                title=title_el.get_text(strip=True) if title_el else "",
                author=author_el.get_text(strip=True) if author_el else "",
            )
        )
    return results


def _split_ingredient(raw: str) -> RecipeIngredient:
    parts = raw.strip().split()
    if len(parts) >= 2:
        return RecipeIngredient(name=parts[0], amount=" ".join(parts[1:]))
    return RecipeIngredient(name=raw.strip(), amount="")


def _load_recipe_ld(soup: BeautifulSoup) -> dict | None:
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "@graph" in data:
            candidates = data["@graph"]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Recipe":
                return item
    return None


def parse_detail_html(html: str, recipe_id: str) -> RecipeDetailResponse:
    soup = BeautifulSoup(html, "html.parser")
    ld = _load_recipe_ld(soup) or {}
    name = ld.get("name") or ""
    image = ld.get("image")
    if isinstance(image, list) and image:
        main_image = image[0] if isinstance(image[0], str) else image[0].get("url")
    elif isinstance(image, str):
        main_image = image
    else:
        main_image = None

    ingredients = [_split_ingredient(x) for x in ld.get("recipeIngredient") or []]

    steps: list[RecipeStep] = []
    for i, step in enumerate(ld.get("recipeInstructions") or [], start=1):
        if isinstance(step, dict):
            img = step.get("image")
            if isinstance(img, list) and img:
                img = img[0]
            steps.append(
                RecipeStep(
                    order=i,
                    description=step.get("text") or "",
                    image_url=img if isinstance(img, str) else None,
                )
            )
        elif isinstance(step, str):
            steps.append(RecipeStep(order=i, description=step))

    tips: list[str] = []
    for tip_el in soup.select(".view_step .tip, .view_step p.tip"):
        text = tip_el.get_text(strip=True)
        if text:
            tips.append(text)
    if tips and steps:
        steps[0] = steps[0].model_copy(update={"tip": tips[0]})

    return RecipeDetailResponse(
        board_name="",
        author_name="",
        recipe_name=name,
        source_url=f"{BASE_URL}/recipe/{recipe_id}",
        main_image_url=main_image,
        ingredients=ingredients,
        steps=steps,
        tips=tips,
        cached=False,
    )
```

- [ ] **Step 6: Run — expect PASS**

```bash
uv run pytest tests/unit/test_recipe_detail_crawler_parse.py -v
```

팁 assertion이 깨지면 fixture/파서를 맞춰 수정한다 (tips 리스트 또는 step.tip 중 하나만 있어도 통과하도록 테스트 유지).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/domains/recipe_detail/crawler.py \
  tests/fixtures tests/unit/test_recipe_detail_crawler_parse.py
git commit -m "$(cat <<'EOF'
Feat: 만개의 레시피 HTML/ld+json 파서 추가

EOF
)"
```

---

### Task 4: Crawler HTTP + RecipeDetailService (TDD)

**Files:**
- Modify: `src/domains/recipe_detail/crawler.py`
- Create: `src/domains/recipe_detail/service.py`
- Create: `tests/unit/test_recipe_detail_service.py`

**Interfaces:**
- Produces:
  - `class RecipeCrawler` with:
    - `async def search(self, query: str) -> list[SearchCandidate]`
    - `async def fetch_detail(self, recipe_id: str) -> RecipeDetailResponse`
  - `class RecipeDetailService` with:
    - `async def get_detail(self, board_name: str, author_name: str) -> RecipeDetailResponse`
  - Exceptions: 매칭 실패 → `NotFoundException(detail="해당 레시피를 찾지 못했어요")`; HTTP/파싱 → `ExternalServiceException`

- [ ] **Step 1: Write failing service tests (mock crawler)**

```python
from unittest.mock import AsyncMock

import pytest

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.recipe_detail.cache import RecipeDetailCache
from domains.recipe_detail.matcher import SearchCandidate
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService


@pytest.fixture
def crawler():
    return AsyncMock()


@pytest.fixture
def service(crawler):
    return RecipeDetailService(
        crawler=crawler,
        cache=RecipeDetailCache(ttl_seconds=60),
    )


async def test_get_detail_success_and_cache(service, crawler):
    crawler.search.return_value = [
        SearchCandidate("6891574", "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈", "GP하루한끼")
    ]
    crawler.fetch_detail.return_value = RecipeDetailResponse(
        board_name="",
        author_name="",
        recipe_name="닭꼬치",
        source_url="https://www.10000recipe.com/recipe/6891574",
        cached=False,
    )
    first = await service.get_detail(
        "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
        "GP하루한끼",
    )
    assert first.recipe_name == "닭꼬치"
    assert first.board_name.startswith("아이들")
    assert first.author_name == "GP하루한끼"
    assert first.cached is False
    crawler.search.assert_awaited_once()

    second = await service.get_detail(
        "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
        "GP하루한끼",
    )
    assert second.cached is True
    assert crawler.search.await_count == 1


async def test_get_detail_not_found(service, crawler):
    crawler.search.return_value = [
        SearchCandidate("1", "완전 다른 제목", "다른사람"),
    ]
    with pytest.raises(NotFoundException):
        await service.get_detail("닭꼬치", "GP하루한끼")


async def test_get_detail_external_error(service, crawler):
    crawler.search.side_effect = ExternalServiceException("timeout")
    with pytest.raises(ExternalServiceException):
        await service.get_detail("닭꼬치", "GP하루한끼")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_recipe_detail_service.py -v
```

- [ ] **Step 3: Implement HTTP crawler + service**

`RecipeCrawler` 요구사항:
- `httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})`
- search URL: `f"{BASE_URL}/recipe/list.html"`, params `{"q": query}`
- detail URL: `f"{BASE_URL}/recipe/{recipe_id}"`
- 클래스 레벨 `asyncio.Semaphore(3)`로 동시 요청 제한
- non-200 / timeout / 예외 → `ExternalServiceException`
- 검색어는 `board_name`을 그대로 쓰되 앞뒤 trim

`RecipeDetailService.get_detail`:
1. `key = cache_key(...)`; hit이면 return
2. `candidates = await crawler.search(board_name.strip())`
3. `best = pick_best_candidate(...)`; None이면 `NotFoundException`
4. `raw = await crawler.fetch_detail(best.recipe_id)`
5. `response = raw.model_copy(update={board_name, author_name, cached: False})`
6. `cache.set`; return

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_recipe_detail_service.py tests/unit/test_recipe_detail_matcher.py tests/unit/test_recipe_detail_cache.py tests/unit/test_recipe_detail_crawler_parse.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/recipe_detail/crawler.py src/domains/recipe_detail/service.py \
  tests/unit/test_recipe_detail_service.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 크롤러 HTTP 및 서비스 추가

EOF
)"
```

---

### Task 5: API endpoint + DI (TDD)

**Files:**
- Modify: `src/api/deps.py`
- Modify: `src/api/v1/endpoints/rag.py`
- Create: `tests/api/test_recipe_detail_api.py`

**Interfaces:**
- Produces: `GET /api/v1/recipes/detail?board_name=&author_name=`
- Consumes: `RecipeDetailService.get_detail`
- DI: `get_recipe_detail_service` → 싱글톤 캐시 공유를 위해 모듈 레벨 `_cache = RecipeDetailCache()` + `RecipeCrawler()` 인스턴스 재사용

- [ ] **Step 1: Write failing API tests**

```python
from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.deps import get_recipe_detail_service
from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.recipe_detail.schemas import RecipeDetailResponse
from main import app


async def test_detail_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/recipes/detail",
        params={"board_name": "a", "author_name": "b"},
    )
    assert response.status_code == 401


async def test_detail_success(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.return_value = RecipeDetailResponse(
        board_name="제목",
        author_name="작성자",
        recipe_name="요리",
        source_url="https://www.10000recipe.com/recipe/1",
        cached=False,
    )
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "제목", "author_name": "작성자"},
        )
        assert response.status_code == 200
        assert response.json()["recipe_name"] == "요리"
        mock.get_detail.assert_awaited_once_with("제목", "작성자")
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_detail_not_found(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.side_effect = NotFoundException(
        detail="해당 레시피를 찾지 못했어요"
    )
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "x", "author_name": "y"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NOT_FOUND
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_detail_bad_gateway(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.side_effect = ExternalServiceException()
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "x", "author_name": "y"},
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/api/test_recipe_detail_api.py -v
```

- [ ] **Step 3: Wire endpoint + deps**

`deps.py`에 추가:

```python
from domains.recipe_detail.cache import RecipeDetailCache
from domains.recipe_detail.crawler import RecipeCrawler
from domains.recipe_detail.service import RecipeDetailService

_recipe_detail_cache = RecipeDetailCache(ttl_seconds=86400)
_recipe_crawler = RecipeCrawler()


def get_recipe_detail_service() -> RecipeDetailService:
    return RecipeDetailService(crawler=_recipe_crawler, cache=_recipe_detail_cache)
```

참고: 엔드포인트는 JWT가 필요한 recommendations와 동일하게, service DI만으로도 auth가 걸리게 하려면 `get_recipe_detail_service`가 `user: User = Depends(get_current_user)`를 받도록 한다 (서비스는 user 미사용이어도 인증 강제).

```python
def get_recipe_detail_service(
    user: User = Depends(get_current_user),
) -> RecipeDetailService:
    return RecipeDetailService(crawler=_recipe_crawler, cache=_recipe_detail_cache)
```

`rag.py`에 라우트 추가:

```python
from api.deps import get_rag_service, get_recipe_detail_service
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    NotFoundException,
    UnAuthorizedException,
)
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService

@router.get(
    "/detail",
    status_code=status.HTTP_200_OK,
    response_model=RecipeDetailResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
    ),
)
async def recipe_detail(
    board_name: str,
    author_name: str,
    service: RecipeDetailService = Depends(get_recipe_detail_service),
) -> RecipeDetailResponse:
    return await service.get_detail(board_name, author_name)
```

- [ ] **Step 4: Run all related tests**

```bash
uv run pytest tests/api/test_recipe_detail_api.py tests/unit/test_recipe_detail_*.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/deps.py src/api/v1/endpoints/rag.py tests/api/test_recipe_detail_api.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 GET 엔드포인트 추가

EOF
)"
```

---

### Task 6: App types + API client

**Files (app repo):**
- Modify: `src/types/api.ts`
- Create: `src/api/recipes.ts`

**Interfaces:**
- Produces:
  - `getRecipeRecommendations(): Promise<RecipeRecommendationResponse>`
  - `getRecipeDetail(boardName: string, authorName: string): Promise<RecipeDetail>`

- [ ] **Step 1: Add types to `src/types/api.ts`**

```typescript
export type RecipeRecommendation = {
  recipe_name: string;
  parsed_ingredients: string;
  board_name: string;
  author_name: string;
  recipe_difficulty: string;
  time: string;
  score: number;
};

export type RecipeRecommendationResponse = {
  ingredients_used: string[];
  recipes: RecipeRecommendation[];
};

export type RecipeIngredient = {
  name: string;
  amount: string;
};

export type RecipeStep = {
  order: number;
  description: string;
  tip: string | null;
  image_url: string | null;
};

export type RecipeDetail = {
  board_name: string;
  author_name: string;
  recipe_name: string;
  source_url: string;
  main_image_url: string | null;
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
  tips: string[];
  cached: boolean;
};
```

- [ ] **Step 2: Create `src/api/recipes.ts`**

```typescript
import { apiClient } from '@/api/client';
import type {
  RecipeDetail,
  RecipeRecommendationResponse,
} from '@/types/api';

export async function getRecipeRecommendations(): Promise<RecipeRecommendationResponse> {
  const { data } = await apiClient.get<RecipeRecommendationResponse>(
    '/recipes/recommendations',
  );
  return data;
}

export async function getRecipeDetail(
  boardName: string,
  authorName: string,
): Promise<RecipeDetail> {
  const { data } = await apiClient.get<RecipeDetail>('/recipes/detail', {
    params: { board_name: boardName, author_name: authorName },
  });
  return data;
}
```

- [ ] **Step 3: Commit (app)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
git add src/types/api.ts src/api/recipes.ts
git commit -m "$(cat <<'EOF'
Feat: 레시피 추천·상세 API 클라이언트 추가

EOF
)"
```

---

### Task 7: App recipe list + navigation

**Files:**
- Create: `src/components/RecipeCard.tsx`
- Create: `src/app/(main)/recipes/index.tsx`
- Modify: `src/app/(main)/_layout.tsx`
- Modify: `src/app/(main)/index.tsx` (레시피 보기 버튼)

- [ ] **Step 1: `RecipeCard`**

기존 `IngredientItem`/`colors`/`clayShadow` 스타일에 맞춰 카드 컴포넌트 작성:
- props: `recipe: RecipeRecommendation`, `onPress: () => void`
- 표시: `recipe_name`, `parsed_ingredients`(1줄 truncate), `recipe_difficulty`, `time`

- [ ] **Step 2: `recipes/index.tsx`**

```typescript
// 핵심 골격
const query = useQuery({
  queryKey: ['recipes', 'recommendations'],
  queryFn: getRecipeRecommendations,
});

// FlatList data={query.data?.recipes ?? []}
// onPress → router.push({
//   pathname: '/(main)/recipes/detail',
//   params: { board_name, author_name },
// })
// 로딩: ActivityIndicator
// 에러: Text + 재시도 버튼 (query.refetch)
// 빈 목록: 식재료가 없거나 추천 없음 안내
```

- [ ] **Step 3: Layout + fridge entry**

`_layout.tsx`에:

```tsx
<Stack.Screen name="recipes/index" options={{ title: '레시피 추천' }} />
<Stack.Screen name="recipes/detail" options={{ title: '레시피 상세' }} />
```

`(main)/index.tsx`에 `router.push('/(main)/recipes')` 버튼 추가 (예: “레시피 추천”).

- [ ] **Step 4: 수동 스모크**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
npx tsc --noEmit
```

Expected: no errors. Expo에서 냉장고 → 레시피 추천 진입 확인.

- [ ] **Step 5: Commit**

```bash
git add src/components/RecipeCard.tsx src/app/(main)/recipes/index.tsx \
  src/app/(main)/_layout.tsx src/app/(main)/index.tsx
git commit -m "$(cat <<'EOF'
Feat: 레시피 추천 목록 화면 추가

EOF
)"
```

---

### Task 8: App recipe detail screen

**Files:**
- Create: `src/app/(main)/recipes/detail.tsx`
- Modify: `package.json` — `npx expo install expo-image`

- [ ] **Step 1: Install expo-image**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
npx expo install expo-image
```

- [ ] **Step 2: Implement detail screen**

```typescript
import { useLocalSearchParams } from 'expo-router';
import { Image } from 'expo-image';
import { useQuery } from '@tanstack/react-query';
import { getRecipeDetail } from '@/api/recipes';
import { getErrorMessage } from '@/api/client';
import { isAxiosError } from 'axios';

// params: board_name, author_name (string | string[])
const boardName = Array.isArray(board_name) ? board_name[0] : board_name;
const authorName = Array.isArray(author_name) ? author_name[0] : author_name;

const detailQuery = useQuery({
  queryKey: ['recipes', 'detail', boardName, authorName],
  queryFn: () => getRecipeDetail(boardName!, authorName!),
  enabled: Boolean(boardName && authorName),
});
```

UI 구성 (ScrollView):
1. `main_image_url` (있으면 Image)
2. `recipe_name`, `author_name`
3. 재료 목록 (`name` + `amount`)
4. 조리 순서 (`order`, `description`, step `image_url`, step `tip`)
5. 전역 `tips`

에러 UX:
- status 404 → “해당 레시피를 찾지 못했어요”
- 그 외/네트워크 → “레시피를 불러오지 못했어요. 다시 시도해 주세요” + 재시도
- `cached`는 화면에 표시하지 않음

404 판별:

```typescript
function detailErrorMessage(error: unknown): string {
  if (isAxiosError(error) && error.response?.status === 404) {
    return '해당 레시피를 찾지 못했어요';
  }
  return '레시피를 불러오지 못했어요. 다시 시도해 주세요';
}
```

- [ ] **Step 3: Typecheck**

```bash
npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json src/app/(main)/recipes/detail.tsx
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 화면 추가

EOF
)"
```

---

### Task 9: End-to-end smoke (optional live)

**Files:** none (verification only)

- [ ] **Step 1: 백엔드 테스트 전체**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/api/test_recipe_detail_api.py tests/unit/test_recipe_detail_*.py tests/api/test_rag_api.py -v
```

Expected: PASS

- [ ] **Step 2: (선택) 실사이트 스모크**

백엔드 실행 후 JWT로:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  --get "$API/api/v1/recipes/detail" \
  --data-urlencode "board_name=아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈" \
  --data-urlencode "author_name=GP하루한끼"
```

Expected: 200 + ingredients/steps. 사이트 구조 변경 시 픽스처·셀렉터만 수정.

- [ ] **Step 3: Docs 상태 갱신 (back)**

스펙 파일 상단 `상태: Approved` 유지. 플랜 체크박스는 구현 시 갱신.

완료 커밋이 필요하면:

```bash
# 변경 없으면 커밋 생략
```

---

## Self-Review Checklist

| Spec 항목 | Task |
|-----------|------|
| board_name+author 검색 | Task 3–4 |
| 백엔드 크롤 | Task 4 |
| 1건 자동 매칭 / 404 | Task 1, 4, 5 |
| TTL 24h 인메모리 | Task 2, 4 |
| 재료·순서·팁·사진 | Task 3, 8 |
| GET /recipes/detail | Task 5 |
| 앱 목록+상세 | Task 6–8 |
| 에러 카피 | Task 5, 8 |
| recommendations 스키마 불변 | Task 5 (미수정) / Task 9 regression |

No TBD placeholders. Types consistent across tasks (`RecipeDetailResponse` / app `RecipeDetail`).
