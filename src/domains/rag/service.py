import asyncio

from domains.ingredient.repository import IngredientRepository
from domains.rag.mapper import (
    build_ingredient_query,
    is_recipe_name_in_ingredients,
    map_document_to_recipe,
)
from domains.rag.retriever import RecipeRetriever
from domains.rag.schemas import RecipeRecommendationResponse
from domains.user.model import User

TOP_K = 5
# 레시피명=식재료명 충돌·중복을 걸러도 TOP_K를 채우기 위해 여유 있게 조회
SEARCH_CANDIDATE_K = 50


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

        recipes = []
        seen: set[tuple[str, str]] = set()
        for doc, score in docs_with_scores:
            mapped = map_document_to_recipe(doc, score)
            if mapped is None:
                continue
            # 보유 식재료와 같은 이름의 레시피(예: 김가루)는 제외 — 재료 유사도만 남김
            if is_recipe_name_in_ingredients(mapped.recipe_name, names):
                continue
            key = (mapped.recipe_name, mapped.parsed_ingredients)
            if key in seen:
                continue
            seen.add(key)
            recipes.append(mapped)
            if len(recipes) >= TOP_K:
                break

        return RecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )
