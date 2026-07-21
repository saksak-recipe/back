import pytest
from pydantic import ValidationError

from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeCandidateList,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)


def test_recommendation_response_roundtrip():
    body = AiRecipeRecommendationResponse(
        ingredients_used=["계란"],
        recipes=[
            AiRecipeRecommendation(
                recipe_id="11111111-1111-1111-1111-111111111111",
                recipe_name="계란볶음밥",
                owned_ingredients=["계란"],
                missing_ingredients=["밥"],
                recipe_difficulty="초급",
                time="15분",
            )
        ],
    )
    assert body.recipes[0].source == "ai"
    raw = body.model_dump_json()
    assert AiRecipeRecommendationResponse.model_validate_json(raw) == body


def test_cache_record_optional_detail():
    record = AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )
    assert record.ingredients is None
    assert record.steps is None
    assert record.tips is None


def test_candidate_list_requires_exactly_five_recipes():
    recipe = AiRecipeCandidate(recipe_name="계란찜")

    with pytest.raises(ValidationError):
        AiRecipeCandidateList(recipes=[recipe] * 4)

    assert len(AiRecipeCandidateList(recipes=[recipe] * 5).recipes) == 5

    with pytest.raises(ValidationError):
        AiRecipeCandidateList(recipes=[recipe] * 6)
