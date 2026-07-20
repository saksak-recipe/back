from pydantic import BaseModel, Field


class AiRecipeCandidate(BaseModel):
    """LLM structured output 목록 후보."""

    recipe_name: str
    recipe_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""


class AiRecipeCandidateList(BaseModel):
    """목록 생성용 structured output 래퍼."""

    recipes: list[AiRecipeCandidate] = Field(default_factory=list)


class AiRecipeIngredient(BaseModel):
    name: str
    amount: str = ""


class AiRecipeStep(BaseModel):
    order: int
    description: str


class AiRecipeDetailPayload(BaseModel):
    """상세 생성용 structured output."""

    ingredients: list[AiRecipeIngredient] = Field(default_factory=list)
    steps: list[AiRecipeStep] = Field(default_factory=list)
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
