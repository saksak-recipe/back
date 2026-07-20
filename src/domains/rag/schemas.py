from pydantic import BaseModel, Field


class RecipeRecommendation(BaseModel):
    recipe_name: str
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
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
