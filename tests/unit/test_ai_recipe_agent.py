from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from domains.ai_recipe.agent import AgentFailedError, AiRecipeAgent
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeCandidateList,
    AiRecipeDetailPayload,
    AiRecipeIngredient,
    AiRecipeStep,
)


def _five_recipes():
    return [
        AiRecipeCandidate(
            recipe_name=f"요리{i}",
            recipe_ingredients=["계란", "밥"],
            recipe_difficulty="초급",
            time="10분",
        )
        for i in range(5)
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


def test_run_list_structured_returns_five_with_urgency_hint():
    payload = MagicMock()
    payload.recipes = _five_recipes()
    structured = MagicMock()
    structured.invoke.return_value = payload
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    candidates = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(
        ["계란"], urgent_names=["계란"]
    )

    assert len(candidates) == 5
    assert candidates[0].recipe_name == "요리0"
    llm.with_structured_output.assert_called_once_with(AiRecipeCandidateList)
    structured.invoke.assert_called_once()
    messages = structured.invoke.call_args.args[0]
    human = next(message for message in messages if isinstance(message, HumanMessage))
    assert "우선 소진" in human.content
    assert "계란" in human.content


def test_run_list_raises_when_structured_result_has_wrong_count():
    payload = MagicMock()
    payload.recipes = _five_recipes()[:4]
    structured = MagicMock()
    structured.invoke.return_value = payload
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    with pytest.raises(AgentFailedError, match="expected 5 recipes"):
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])


def test_run_detail_uses_structured_output_once():
    payload = AiRecipeDetailPayload(
        ingredients=[AiRecipeIngredient(name="계란", amount="2개")],
        steps=[AiRecipeStep(order=1, description="볶는다")],
        tips=["약불"],
    )
    structured = MagicMock()
    structured.invoke.return_value = payload
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    detail = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
        ["계란"], _summary()
    )

    assert detail["tips"] == ["약불"]
    llm.with_structured_output.assert_called_once_with(AiRecipeDetailPayload)
    structured.invoke.assert_called_once()


def test_run_list_wraps_llm_error_as_cause():
    structured = MagicMock()
    upstream_error = RuntimeError("openai unavailable")
    structured.invoke.side_effect = upstream_error
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    with pytest.raises(AgentFailedError) as exc_info:
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(["계란"])

    assert exc_info.value.__cause__ is upstream_error


def test_run_detail_wraps_llm_error_as_cause():
    structured = MagicMock()
    upstream_error = RuntimeError("openai unavailable")
    structured.invoke.side_effect = upstream_error
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    with pytest.raises(AgentFailedError) as exc_info:
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_detail(
            ["계란"], _summary()
        )

    assert exc_info.value.__cause__ is upstream_error
