from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.recipe_detail.cache import RecipeDetailCache
from domains.recipe_detail.matcher import SearchCandidate
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService


@pytest.fixture
def crawler() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def service(crawler: AsyncMock):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    svc = RecipeDetailService(
        crawler=crawler,
        cache=RecipeDetailCache(redis, ttl_seconds=60),
    )
    yield svc
    await redis.aclose()


async def test_get_detail_success_and_cache(
    service: RecipeDetailService, crawler: AsyncMock
) -> None:
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


async def test_get_detail_not_found(
    service: RecipeDetailService, crawler: AsyncMock
) -> None:
    crawler.search.return_value = [
        SearchCandidate("1", "완전 다른 제목", "다른사람"),
    ]

    with pytest.raises(NotFoundException) as exception:
        await service.get_detail("닭꼬치", "GP하루한끼")

    assert exception.value.detail == "해당 레시피를 찾지 못했어요"


async def test_get_detail_propagates_external_error(
    service: RecipeDetailService, crawler: AsyncMock
) -> None:
    crawler.search.side_effect = ExternalServiceException("timeout")

    with pytest.raises(ExternalServiceException):
        await service.get_detail("닭꼬치", "GP하루한끼")
