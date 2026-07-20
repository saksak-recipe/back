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
            self.retriever.search, query, k=TOP_K
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
