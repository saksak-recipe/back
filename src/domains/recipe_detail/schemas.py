from pydantic import BaseModel, Field


class RecipeIngredient(BaseModel):
    name: str
    amount: str = ""


class RecipeStep(BaseModel):
    order: int
    description: str
    tip: str | None = None
    image_url: str | None = None


class RecipeDetailResponse(BaseModel):
    board_name: str
    author_name: str
    recipe_name: str
    source_url: str
    main_image_url: str | None = None
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    cached: bool = False
