from pydantic import BaseModel, Field

from core.quota import QuotaInfo


class RecipeRecommendation(BaseModel):
    recipe_name: str
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    board_name: str = ""
    author_name: str = ""
    recipe_difficulty: str = ""
    time: str = ""
    score: float = Field(
        description="PGVector 거리. 값이 작을수록 유사도가 높습니다."
    )


class RecipeRecommendationResponse(BaseModel):
    ingredients_used: list[str]
    recipes: list[RecipeRecommendation]
    quota: QuotaInfo | None = None
