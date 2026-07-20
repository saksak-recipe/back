from core.exception.exceptions import NotFoundException
from domains.recipe_detail.cache import RecipeDetailCache, cache_key
from domains.recipe_detail.crawler import RecipeCrawler
from domains.recipe_detail.matcher import pick_best_candidate
from domains.recipe_detail.schemas import RecipeDetailResponse


class RecipeDetailService:
    def __init__(self, crawler: RecipeCrawler, cache: RecipeDetailCache) -> None:
        self._crawler = crawler
        self._cache = cache

    async def get_detail(
        self,
        board_name: str,
        author_name: str,
    ) -> RecipeDetailResponse:
        key = cache_key(board_name, author_name)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        normalized_board_name = board_name.strip()
        candidates = await self._crawler.search(normalized_board_name)
        best = pick_best_candidate(candidates, normalized_board_name, author_name)
        if best is None:
            raise NotFoundException(detail="해당 레시피를 찾지 못했어요")

        raw = await self._crawler.fetch_detail(best.recipe_id)
        response = raw.model_copy(
            update={
                "board_name": board_name,
                "author_name": author_name,
                "cached": False,
            }
        )
        self._cache.set(key, response)
        return response
