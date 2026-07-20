from pydantic import BaseModel, Field


class RecipeRecommendation(BaseModel):
    recipe_name: str
    parsed_ingredients: str
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
