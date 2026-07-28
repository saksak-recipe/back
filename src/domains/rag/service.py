import asyncio
import random

from core.quota import DailyQuotaStore, KIND_RAG, RAG_DAILY_LIMIT
from domains.ingredient.scope import IngredientScopeLoader, RecipeScope
from domains.ingredient_matching.urgency import count_urgent_owned, urgent_names
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
        scope_loader: IngredientScopeLoader,
        retriever: RecipeRetriever,
        daily_quota_store: DailyQuotaStore,
    ):
        self.user = user
        self.scope_loader = scope_loader
        self.retriever = retriever
        self.daily_quota_store = daily_quota_store

    async def recommend_recipes(
        self, scope: RecipeScope = RecipeScope.personal
    ) -> RecipeRecommendationResponse:
        scoped = await self.scope_loader.load(scope)
        ingredients = scoped.ingredients
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return RecipeRecommendationResponse(
                ingredients_used=[], recipes=[], quota=None
            )

        urgent = urgent_names(ingredients)
        query = build_ingredient_query(names, urgent_names=urgent)
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

        if urgent:
            recipes = self._sample_preferring_urgent(candidates, urgent)
        else:
            recipes = self._sample_top_k(candidates)

        quota = await self.daily_quota_store.consume(
            KIND_RAG, str(self.user.id), RAG_DAILY_LIMIT
        )
        return RecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
            quota=quota,
        )

    @staticmethod
    def _sample_top_k(
        candidates: list[RecipeRecommendation],
    ) -> list[RecipeRecommendation]:
        if len(candidates) <= TOP_K:
            return candidates
        return random.sample(candidates, TOP_K)

    @staticmethod
    def _sample_preferring_urgent(
        candidates: list[RecipeRecommendation],
        urgent: list[str],
    ) -> list[RecipeRecommendation]:
        """urgent 사용 개수가 많은 티어를 우선하되, 티어 안에서는 sample로 다양성을 확보한다."""
        by_count: dict[int, list[RecipeRecommendation]] = {}
        for recipe in candidates:
            count = count_urgent_owned(recipe.owned_ingredients, urgent)
            by_count.setdefault(count, []).append(recipe)

        recipes: list[RecipeRecommendation] = []
        for count in sorted(by_count.keys(), reverse=True):
            if len(recipes) >= TOP_K:
                break
            pool = by_count[count]
            need = TOP_K - len(recipes)
            if len(pool) <= need:
                recipes.extend(pool)
            else:
                recipes.extend(random.sample(pool, need))
        return recipes
