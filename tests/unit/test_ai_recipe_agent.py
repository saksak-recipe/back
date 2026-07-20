from unittest.mock import MagicMock

import pytest

from domains.ai_recipe.agent import (
    AgentFailedError,
    AiRecipeAgent,
    TOP_K,
    chat_model_kwargs,
)
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeCandidateList,
    AiRecipeDetailPayload,
    AiRecipeIngredient,
    AiRecipeStep,
)


def test_chat_model_kwargs_sets_low_reasoning_for_gpt5():
    assert chat_model_kwargs("gpt-5-nano")["reasoning_effort"] == "low"
    assert chat_model_kwargs("gpt-5-nano")["timeout"] == 35
    assert "reasoning_effort" not in chat_model_kwargs("gpt-4o-mini")


def _five_candidates() -> list[AiRecipeCandidate]:
    return [
        AiRecipeCandidate(
            recipe_name=f"요리{i}",
            recipe_ingredients=["계란", "밥"],
            recipe_difficulty="초급",
            time="10분",
        )
        for i in range(TOP_K)
    ]


def _summary() -> AiRecipeCacheRecord:
    return AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )


def test_run_list_returns_candidates_via_structured_output():
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = AiRecipeCandidateList(recipes=_five_candidates())

    candidates = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])

    assert len(candidates) == 5
    assert candidates[0].recipe_name == "요리0"
    llm.with_structured_output.assert_called_once()
    structured.invoke.assert_called_once()


def test_run_list_raises_when_wrong_count():
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = AiRecipeCandidateList(
        recipes=_five_candidates()[:2]
    )

    with pytest.raises(AgentFailedError):
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])


def test_run_list_raises_when_no_candidates():
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = AiRecipeCandidateList(recipes=[])

    with pytest.raises(AgentFailedError):
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])


def test_run_detail_expands_via_structured_output():
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    structured.invoke.return_value = AiRecipeDetailPayload(
        ingredients=[AiRecipeIngredient(name="계란", amount="2개")],
        steps=[AiRecipeStep(order=1, description="볶는다")],
        tips=["약불"],
    )

    detail = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
        ["계란"], _summary()
    )

    assert detail["tips"] == ["약불"]
    assert detail["ingredients"][0].name == "계란"
    llm.with_structured_output.assert_called_once()
    structured.invoke.assert_called_once()


def test_run_wraps_llm_error_as_cause():
    llm = MagicMock()
    structured = MagicMock()
    llm.with_structured_output.return_value = structured
    upstream_error = RuntimeError("openai unavailable")
    structured.invoke.side_effect = upstream_error

    with pytest.raises(AgentFailedError) as exc_info:
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
            ["계란"], _summary()
        )

    assert exc_info.value.__cause__ is upstream_error
