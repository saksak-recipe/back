import asyncio
import random

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
    ):
        self.user = user
        self.scope_loader = scope_loader
        self.retriever = retriever

    async def recommend_recipes(
        self, scope: RecipeScope = RecipeScope.personal
    ) -> RecipeRecommendationResponse:
        scoped = await self.scope_loader.load(scope)
        ingredients = scoped.ingredients
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return RecipeRecommendationResponse(ingredients_used=[], recipes=[])

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
            candidates.sort(
                key=lambda recipe: (
                    -count_urgent_owned(recipe.owned_ingredients, urgent),
                    recipe.score,
                ),
            )
            recipes = candidates[:TOP_K]
        else:
            if len(candidates) <= TOP_K:
                recipes = candidates
            else:
                recipes = random.sample(candidates, TOP_K)

        return RecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )
