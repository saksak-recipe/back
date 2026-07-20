import asyncio
import random

from domains.ingredient.repository import IngredientRepository
from domains.rag.mapper import (
    build_ingredient_query,
    is_recipe_name_in_ingredients,
    map_document_to_recipe,
)
from domains.rag.retriever import RecipeRetriever
from domains.rag.schemas import RecipeRecommendation, RecipeRecommendationResponse
from domains.user.model import User

TOP_K = 5
# 벡터 검색 후보
SEARCH_CANDIDATE_K = 40
# 필터 후 상위 풀에서 랜덤 추출
CANDIDATE_POOL_K = 15


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
            self.retriever.search, query, k=SEARCH_CANDIDATE_K
        )

        candidates: list[RecipeRecommendation] = []
        seen: set[tuple[str, str, str]] = set()
        for doc, score in docs_with_scores:
            mapped = map_document_to_recipe(doc, score, owned_names=names)
            if mapped is None:
                continue
            # 보유 식재료와 같은 이름의 레시피(예: 김가루)는 제외 — 재료 유사도만 남김
            if is_recipe_name_in_ingredients(mapped.recipe_name, names):
                continue
            key = (mapped.recipe_name, mapped.board_name, mapped.author_name)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(mapped)
            if len(candidates) >= CANDIDATE_POOL_K:
                break

        if len(candidates) <= TOP_K:
            recipes = candidates
        else:
            recipes = random.sample(candidates, TOP_K)

        return RecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )
