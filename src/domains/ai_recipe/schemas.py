from pydantic import BaseModel, Field


class AiRecipeCandidate(BaseModel):
    """AI가 제안하는 레시피 후보."""

    recipe_name: str
    recipe_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""


class AiRecipeCandidateList(BaseModel):
    recipes: list[AiRecipeCandidate] = Field(min_length=5, max_length=5)


class AiRecipeIngredient(BaseModel):
    name: str
    amount: str = ""


class AiRecipeStep(BaseModel):
    order: int
    description: str


class AiRecipeDetailPayload(BaseModel):
    ingredients: list[AiRecipeIngredient]
    steps: list[AiRecipeStep]
    tips: list[str] = Field(default_factory=list)


class AiRecipeRecommendation(BaseModel):
    recipe_id: str
    recipe_name: str
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""
    source: str = "ai"


class AiRecipeRecommendationResponse(BaseModel):
    ingredients_used: list[str]
    recipes: list[AiRecipeRecommendation]


class AiRecipeCacheRecord(BaseModel):
    recipe_id: str
    recipe_name: str
    recipe_ingredients: list[str] = Field(default_factory=list)
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""
    # 상세 확장 전 None
    ingredients: list[AiRecipeIngredient] | None = None
    steps: list[AiRecipeStep] | None = None
    tips: list[str] | None = None

    def has_detail(self) -> bool:
        return self.ingredients is not None and self.steps is not None


class AiRecipeDetailResponse(BaseModel):
    recipe_id: str
    recipe_name: str
    source: str = "ai"
    ingredients: list[AiRecipeIngredient] = Field(default_factory=list)
    steps: list[AiRecipeStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    cached: bool = False
